"""
Telemetry classification — judges how well a span's attributes resolve into
the signals the intelligence layer needs.

OTel is the pipe, semantic conventions are the language, ObserveAgents is the
intelligence layer. Real customer telemetry is rarely perfect, so instead of
silently best-guessing, every ingested span is classified:

  fully_classified      identity resolved AND every signal expected for this
                        span kind resolved (any tier)
  partially_classified  identity resolved but at least one expected signal
                        is missing
  unclassified          identity itself could not be resolved (fallback hash)

with a confidence grade:

  high    fully classified, every resolved signal came from a standard
          SemConv key, and the environment is known
  medium  resolved, but through fallback variants / org-mapped keys, or the
          environment is missing on an otherwise complete span
  low     unclassified identity, or a GenAI span with no model, or an MCP
          span with no server name

Pure module: no DB access, no ORM imports. It imports app/genai_semconv.py
(the extraction layer) and is consumed by app/otel_normalizer.py, which
persists the result on OtelSpan and rolls it up per OtelAsset. Values are
never read from content attributes — only key names and the already-extracted
scalar signals are considered, and candidate_keys carries key NAMES only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.genai_semconv import (
    TIER_MAPPED,
    TIER_STANDARD,
    extract_environment_tiered,
    extract_mcp_method_tiered,
    extract_model_tiered,
    extract_provider_tiered,
    extract_tool_name_tiered,
    has_genai_signal,
    is_mcp_span,
)

# ── Public constants ──────────────────────────────────────────────────────────
STATUS_FULL = "fully_classified"
STATUS_PARTIAL = "partially_classified"
STATUS_UNCLASSIFIED = "unclassified"

CONF_HIGH = "high"
CONF_MEDIUM = "medium"
CONF_LOW = "low"

# Identity tiers assigned by the normalizer's _resolve_identity.
IDENTITY_DECLARED = "declared"   # gen_ai.agent.* / agent.name attributes
IDENTITY_SERVICE = "service"     # service.name resource attribute
IDENTITY_FALLBACK = "fallback"   # stable hash — nobody told us who this is

# Missing-signal codes (stored in OtelSpan.classification_missing).
MISSING_IDENTITY = "identity"
MISSING_ENVIRONMENT = "environment"
MISSING_GENAI_MODEL = "genai_model"
MISSING_GENAI_PROVIDER = "genai_provider"
MISSING_TOOL_NAME = "tool_name"
MISSING_MCP_SERVER = "mcp_server"

# Asset-rollup weights: a fully classified span is worth 1.0, partial 0.6,
# unclassified 0.2 — the asset confidence_score is the weighted percentage.
_WEIGHTS = {"full": 1.0, "partial": 0.6, "unclassified": 0.2}

# Attribute-key fragments that suggest a custom key the org may want to map
# to a canonical SemConv key. Matched against key names only, and only for
# keys outside the known namespaces.
_CANDIDATE_FRAGMENTS = (
    "model", "provider", "llm", "agent", "tool", "token",
    "prompt", "completion", "environment", "team", "owner", "mcp",
)
_KNOWN_PREFIXES = (
    "gen_ai.", "llm.", "mcp.", "db.", "http.", "url.", "rpc.", "server.",
    "service.", "deployment.", "k8s.", "cloud.", "container.", "host.",
    "process.", "telemetry.", "network.", "peer.", "jsonrpc.", "workflow.",
    "session.", "user.", "enduser.", "exception.", "error.", "otel.",
    "code.", "thread.", "faas.", "messaging.", "aws.", "gcp.", "azure.",
)
_KNOWN_BARE_KEYS = frozenset({
    "team", "owner", "environment", "env", "method", "model.name",
    "tool_name", "function_name", "prompt_tokens", "completion_tokens",
    "input_tokens", "output_tokens", "ttft_ms",
})
_CANDIDATE_KEY_LIMIT = 10  # per span; the asset rollup caps again at 40


@dataclass
class SpanClassification:
    status: str
    confidence: str
    missing: list[str] = field(default_factory=list)
    tiers: dict[str, str] = field(default_factory=dict)
    candidate_keys: list[str] = field(default_factory=list)

    @property
    def counts_key(self) -> str:
        """Bucket name used in the per-asset rollup counters."""
        if self.status == STATUS_FULL:
            return "full"
        if self.status == STATUS_PARTIAL:
            return "partial"
        return "unclassified"


def detect_candidate_keys(
    attrs: dict, resource_attrs: dict, mapped_keys: frozenset[str] = frozenset()
) -> list[str]:
    """Custom-looking attribute key NAMES that may deserve an org mapping.

    A candidate is a key outside every known namespace/bare-key list whose
    name contains a signal-ish fragment (model/tool/token/...). Values are
    never inspected. Keys already handled by the org mapping are skipped.
    """
    out: list[str] = []
    for source in (attrs, resource_attrs):
        for key in source:
            if len(out) >= _CANDIDATE_KEY_LIMIT:
                return out
            if not isinstance(key, str) or key in mapped_keys or key in out:
                continue
            if key in _KNOWN_BARE_KEYS or key.startswith(_KNOWN_PREFIXES):
                continue
            lowered = key.lower()
            if any(frag in lowered for frag in _CANDIDATE_FRAGMENTS):
                out.append(key)
    return out


def _tier_of(tier: str | None, resolved_key_mapped: bool) -> str | None:
    if tier is None:
        return None
    return TIER_MAPPED if resolved_key_mapped else tier


def classify_span(
    attrs: dict,
    resource_attrs: dict,
    *,
    identity_tier: str,
    mapped_keys: frozenset[str] = frozenset(),
) -> SpanClassification:
    """Classify one span. Pure and O(number of attributes).

    identity_tier comes from the normalizer's identity resolution
    (declared / service / fallback). mapped_keys is the set of canonical
    keys that were populated by the org attribute mapping for this span —
    signals resolved through them are downgraded to TIER_MAPPED (medium
    confidence): the value is trusted, but it isn't native SemConv emission.
    """
    missing: list[str] = []
    tiers: dict[str, str] = {}

    # ── Identity ──────────────────────────────────────────────────────────────
    if identity_tier == IDENTITY_FALLBACK:
        missing.append(MISSING_IDENTITY)
    else:
        tiers["identity"] = (
            TIER_STANDARD if identity_tier in (IDENTITY_DECLARED, IDENTITY_SERVICE)
            else identity_tier
        )
        if "service.name" in mapped_keys or "gen_ai.agent.name" in mapped_keys:
            tiers["identity"] = TIER_MAPPED

    # ── Environment (always expected) ─────────────────────────────────────────
    env, env_tier = extract_environment_tiered(resource_attrs, attrs)
    if env:
        env_mapped = "deployment.environment" in mapped_keys
        tiers["environment"] = _tier_of(env_tier, env_mapped) or env_tier
    else:
        missing.append(MISSING_ENVIRONMENT)

    # ── Tool / MCP spans (checked first — mirrors the normalizer's branch
    #    order: an execute_tool span carries gen_ai.* keys but is tool
    #    activity, so model/provider are not expected on it) ─────────────────
    mcp = is_mcp_span(attrs)
    tool_expected = bool(
        mcp
        or extract_tool_name_tiered(attrs)[0]
        or attrs.get("gen_ai.operation.name") == "execute_tool"
    )

    # ── GenAI signals (expected only on non-tool GenAI spans) ─────────────────
    genai, _ = has_genai_signal(attrs)
    genai_no_model = False
    if genai and not tool_expected:
        model, model_tier = extract_model_tiered(attrs)
        if model:
            model_mapped = bool(
                {"gen_ai.request.model", "gen_ai.response.model"} & mapped_keys
            )
            tiers["genai_model"] = _tier_of(model_tier, model_mapped) or model_tier
        else:
            missing.append(MISSING_GENAI_MODEL)
            genai_no_model = True
        provider, provider_tier = extract_provider_tiered(attrs)
        if provider:
            provider_mapped = "gen_ai.provider.name" in mapped_keys
            tiers["genai_provider"] = (
                _tier_of(provider_tier, provider_mapped) or provider_tier
            )
        else:
            missing.append(MISSING_GENAI_PROVIDER)

    mcp_no_server = False
    if tool_expected:
        tool, tool_tier = extract_tool_name_tiered(attrs)
        if tool:
            tool_mapped = bool(
                {"gen_ai.tool.name", "mcp.tool.name"} & mapped_keys
            )
            tiers["tool_name"] = _tier_of(tool_tier, tool_mapped) or tool_tier
        else:
            missing.append(MISSING_TOOL_NAME)
    if mcp:
        server = attrs.get("mcp.server") or attrs.get("mcp.server.name")
        if server:
            server_mapped = "mcp.server.name" in mapped_keys
            tiers["mcp_server"] = _tier_of(TIER_STANDARD, server_mapped)
        else:
            missing.append(MISSING_MCP_SERVER)
            mcp_no_server = True
        method_tier = extract_mcp_method_tiered(attrs)[1]
        if method_tier:
            method_mapped = "mcp.method.name" in mapped_keys
            tiers["mcp_method"] = _tier_of(method_tier, method_mapped) or method_tier

    # ── Owner / team (informational — never blocks status) ───────────────────
    owner = (
        resource_attrs.get("service.owner")
        or resource_attrs.get("team")
        or resource_attrs.get("owner")
        or resource_attrs.get("service.team")
    )
    if owner:
        owner_mapped = bool({"team", "owner", "service.owner", "service.team"} & mapped_keys)
        tiers["owner_team"] = TIER_MAPPED if owner_mapped else TIER_STANDARD

    # ── Status ────────────────────────────────────────────────────────────────
    if identity_tier == IDENTITY_FALLBACK:
        status = STATUS_UNCLASSIFIED
    elif missing:
        status = STATUS_PARTIAL
    else:
        status = STATUS_FULL

    # ── Confidence ────────────────────────────────────────────────────────────
    if status == STATUS_UNCLASSIFIED or genai_no_model or mcp_no_server:
        confidence = CONF_LOW
    elif status == STATUS_FULL and all(t == TIER_STANDARD for t in tiers.values()):
        confidence = CONF_HIGH
    else:
        confidence = CONF_MEDIUM

    candidate_keys: list[str] = []
    if missing:
        candidate_keys = detect_candidate_keys(attrs, resource_attrs, mapped_keys)

    return SpanClassification(
        status=status,
        confidence=confidence,
        missing=missing,
        tiers=tiers,
        candidate_keys=candidate_keys,
    )


def merge_classification_counts(
    existing_json: str | None, new_counts: dict[str, int]
) -> tuple[str, str, float]:
    """Merge a batch's span-status counters into an asset's cumulative ones.

    Returns (counts_json, asset_classification_status, asset_confidence_score).
    Counters only ever grow, so the result is order-independent across batches.
    """
    counts = {"full": 0, "partial": 0, "unclassified": 0}
    if existing_json:
        try:
            stored = json.loads(existing_json)
            for key in counts:
                counts[key] = int(stored.get(key, 0) or 0)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    for key in counts:
        counts[key] += int(new_counts.get(key, 0) or 0)

    total = sum(counts.values())
    if total == 0:
        return json.dumps(counts), STATUS_UNCLASSIFIED, 0.0

    if counts["partial"] == 0 and counts["unclassified"] == 0:
        status = STATUS_FULL
    elif counts["full"] == 0 and counts["partial"] == 0:
        status = STATUS_UNCLASSIFIED
    else:
        status = STATUS_PARTIAL

    score = sum(_WEIGHTS[k] * v for k, v in counts.items()) / total * 100.0
    return json.dumps(counts), status, round(score, 1)
