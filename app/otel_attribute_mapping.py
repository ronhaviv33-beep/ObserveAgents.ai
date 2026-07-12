"""
Org-level OTel attribute mapping — customer-defined aliases from custom
attribute keys to canonical SemConv keys.

Customers whose instrumentation emits custom keys (mycompany.llm.model,
tool_used, acme.env, ...) can map them to the canonical keys the intelligence
layer consumes, per organization, without code changes:

    {"mycompany.llm.model": "gen_ai.request.model",
     "tool_used":           "gen_ai.tool.name"}

Storage: one OrgConfig row (key = ORG_CONFIG_KEY, value = the mapping dict).
API: GET/PUT /settings/otel-attribute-mapping (app/routes/settings.py).
Applied by app/otel_normalizer.normalize_spans as a pre-extraction pass —
fetched once per ingest request, never per span.

Precedence: a canonical key already present on the span always wins (mapping
only fills absent canonicals) > org mapping > built-in fallback variants
(app/genai_semconv.py tiers). Signals resolved through a mapped key are
classified TIER_MAPPED → medium confidence.

Privacy: ALLOWED_TARGETS contains no message/prompt/tool-content keys, so the
aliasing pass (which runs before scrub_attributes) can never copy content
into storage. Mapped values are subject to the same scrub pipeline as
everything else.

Future UI note: the settings page can render allowed_targets as a per-row
dropdown and pre-populate the custom-key column from the candidate attribute
keys reported by GET /intelligence/telemetry-quality — both endpoints are
already shaped for that.
"""
from __future__ import annotations

ORG_CONFIG_KEY = "otel_attribute_mapping"
MAX_ENTRIES = 50
MAX_KEY_LENGTH = 128

# Canonical keys a custom attribute may be mapped TO. Metadata/enum keys only —
# never message, prompt, or tool-argument content.
ALLOWED_TARGETS = frozenset({
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.provider.name",
    "gen_ai.operation.name",
    "gen_ai.tool.name",
    "gen_ai.agent.name",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "deployment.environment",
    "service.name",
    "service.namespace",
    "team",
    "owner",
    "service.owner",
    "service.team",
    "mcp.server.name",
    "mcp.method.name",
    "mcp.tool.name",
    "error.type",
    "session.id",
    "db.system",
})

# Targets that are resource-level metadata — the mapped value is written to
# resource_attrs so identity/environment/ownership resolution sees it.
_RESOURCE_LEVEL_TARGETS = frozenset({
    "service.name", "service.namespace", "deployment.environment",
    "team", "owner", "service.owner", "service.team",
})

# Custom keys may not sit inside the canonical namespaces — remapping a
# canonical key would shadow real SemConv emission and can create loops.
_RESERVED_SOURCE_PREFIXES = ("gen_ai.", "mcp.")


def validate_attribute_mapping(mapping: object) -> list[str]:
    """Validate a proposed mapping. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []
    if not isinstance(mapping, dict):
        return ["mapping must be a JSON object of {custom_key: canonical_key}"]
    if len(mapping) > MAX_ENTRIES:
        errors.append(f"mapping has {len(mapping)} entries; maximum is {MAX_ENTRIES}")
    for key, target in mapping.items():
        if not isinstance(key, str) or not key.strip():
            errors.append(f"custom key {key!r} must be a non-empty string")
            continue
        if len(key) > MAX_KEY_LENGTH:
            errors.append(f"custom key {key!r} exceeds {MAX_KEY_LENGTH} characters")
            continue
        if key in ALLOWED_TARGETS or key.startswith(_RESERVED_SOURCE_PREFIXES):
            errors.append(
                f"custom key {key!r} is a canonical attribute — canonical keys "
                "cannot be remapped"
            )
            continue
        if not isinstance(target, str) or target not in ALLOWED_TARGETS:
            errors.append(
                f"target {target!r} for {key!r} is not an allowed canonical key"
            )
    return errors


def apply_attribute_mapping(
    attrs: dict, resource_attrs: dict, mapping: dict
) -> frozenset[str]:
    """Copy custom-key values onto canonical keys (in place, pre-extraction).

    A canonical key already present (on the level it belongs to) is never
    overwritten — native SemConv emission always wins. The custom key is
    looked up in both span and resource attributes; resource-level targets
    land in resource_attrs, everything else in span attrs. Returns the set
    of canonical keys populated via mapping (feeds TIER_MAPPED classification).
    """
    if not mapping:
        return frozenset()
    mapped: set[str] = set()
    for custom_key, target in mapping.items():
        if target in _RESOURCE_LEVEL_TARGETS:
            dest = resource_attrs
        else:
            dest = attrs
        if target in dest:
            continue  # native canonical value present — never overwrite
        value = attrs.get(custom_key)
        if value is None:
            value = resource_attrs.get(custom_key)
        if value is None:
            continue
        dest[target] = value
        mapped.add(target)
    return frozenset(mapped)


def apply_mapping_to_batch(spans: list[dict], mapping: dict) -> list[frozenset[str]]:
    """Apply the org mapping to every parsed span (in place, pre-extraction).

    Returns one frozenset of mapped canonical keys per span, index-aligned
    with `spans`. The OTLP parser shares one resource_attributes dict across
    all spans of a resourceSpans block, so resource-level targets mapped once
    are credited to every span sharing that dict — their classification must
    see the signal as mapped, not native.
    """
    if not mapping:
        return [frozenset()] * len(spans)
    resource_mapped: dict[int, set[str]] = {}
    out: list[frozenset[str]] = []
    for span in spans:
        attrs = span.get("attributes") or {}
        resource_attrs = span.get("resource_attributes") or {}
        span["attributes"] = attrs
        span["resource_attributes"] = resource_attrs
        mapped = set(apply_attribute_mapping(attrs, resource_attrs, mapping))
        shared = resource_mapped.setdefault(id(resource_attrs), set())
        shared |= {k for k in mapped if k in _RESOURCE_LEVEL_TARGETS}
        out.append(frozenset(mapped | shared))
    return out


def load_org_attribute_mapping(db, org_id: int) -> dict:
    """Fetch and defensively validate the org's mapping. Invalid or missing
    config → {} (ingestion must never fail on a bad mapping)."""
    from app.org_config import get_org_config

    try:
        mapping = get_org_config(db, org_id, ORG_CONFIG_KEY)
    except Exception:
        return {}
    if not isinstance(mapping, dict) or not mapping:
        return {}
    if validate_attribute_mapping(mapping):
        return {}
    return mapping
