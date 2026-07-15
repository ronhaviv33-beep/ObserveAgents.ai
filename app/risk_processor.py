"""
Real-time risk processor for normalized telemetry events.

Evaluates a flat, ordered list of small readable rules against one normalized
event and returns a numeric risk score (0-100), human-readable reasons, and a
policy action (allow | warn | block). Runs inside the ingest worker — never
inline in the API request — and is the foundation for the future Detection
Rule Zone.

Thresholds are configurable per org via the OrgConfig key "risk_thresholds"
(a JSON object merged over RISK_DEFAULTS).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app import policy
from app.org_config import get_org_config
from app.pricing_registry import get_active_pricing, _infer_provider
from app.models import _normalize_model

_log = logging.getLogger("ai_asset_mgmt.risk_processor")

RISK_DEFAULTS: dict = {
    "cost_usd_threshold": 1.0,      # per-event cost above this is flagged
    "latency_ms_threshold": 30000,  # per-event latency above this is flagged
    "warn_score": 50,               # score >= warn_score -> policy_action=warn
    "high_risk_score": 70,          # score >= this counts as a high-risk event
    "risky_tools": [
        "shell", "exec", "terminal", "subprocess", "eval",
        "code_interpreter", "file_delete", "sql_execute",
    ],
}

_KNOWN_PROVIDERS = {"openai", "anthropic", "google", "local", "azure", "aws", "bedrock", "mistral", "cohere"}

# Aliases accepted before an environment is called "unknown".
_ENV_ALIASES = {
    "prod": "production", "production": "production",
    "stage": "staging", "staging": "staging",
    "dev": "development", "development": "development",
    "test": "development", "testing": "development", "local": "development",
}


# Read-side catalog of the real-time risk rules above. Each entry maps the
# stable prefix/substring of a risk_reason string back to a rule identity so
# findings can report WHICH rule fired without re-evaluating anything.
# Order matters: first match wins. Purely descriptive — never used in scoring.
RULE_CATALOG: list[dict] = [
    {"rule_id": "upstream_block",      "rule_name": "Upstream policy block",              "match": "Upstream policy blocked",        "weight": 25, "category": "security"},
    {"rule_id": "status_error",        "rule_name": "Event reported an error",            "match": "Event reported an error",        "weight": 25, "category": "operations"},
    {"rule_id": "missing_owner",       "rule_name": "Agent has no owner",                 "match": "no registered owner",            "weight": 10, "category": "governance"},
    {"rule_id": "missing_team",        "rule_name": "Agent has no team",                  "match": "no team assignment",             "weight": 10, "category": "governance"},
    {"rule_id": "unknown_environment", "rule_name": "Unknown environment",                "match": "environment",                    "weight": 15, "category": "governance"},
    {"rule_id": "unknown_provider",    "rule_name": "Unknown provider",                   "match": "provider",                       "weight": 10, "category": "security"},
    {"rule_id": "unknown_model",       "rule_name": "Model not in pricing registry",      "match": "not in pricing registry",        "weight": 15, "category": "cost"},
    {"rule_id": "cost_threshold",      "rule_name": "Cost exceeds threshold",             "match": "exceeds $",                      "weight": 20, "category": "cost"},
    {"rule_id": "latency_threshold",   "rule_name": "Latency unusually high",             "match": "ms threshold",                   "weight": 15, "category": "operations"},
    {"rule_id": "risky_tool",          "rule_name": "Risky tool usage",                   "match": "risky-tool list",                "weight": 25, "category": "security"},
    {"rule_id": "non_approved_model",  "rule_name": "Non-approved model in production",   "match": "blocked for team",               "weight": 30, "category": "security"},
    {"rule_id": "non_approved_model",  "rule_name": "Non-approved model in production",   "match": "not on the approved list",       "weight": 30, "category": "security"},
    {"rule_id": "non_approved_model",  "rule_name": "Non-approved model in production",   "match": "not approved for production",    "weight": 30, "category": "security"},
]


def match_rule(reason: str | None) -> tuple[str | None, str | None]:
    """Map one risk_reason string to (rule_id, rule_name). Substring-based on
    the stable phrases each rule emits; returns (None, None) when a reason
    can't be attributed safely (never guesses)."""
    if not reason:
        return None, None
    lowered = reason.lower()
    for entry in RULE_CATALOG:
        if entry["match"].lower() in lowered:
            return entry["rule_id"], entry["rule_name"]
    return None, None


@dataclass
class RiskResult:
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    policy_action: str = "allow"  # allow | warn | block


def risk_level(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    if score >= 20:
        return "low"
    return "none"


def load_risk_config(db: Session, org_id: int) -> dict:
    """RISK_DEFAULTS merged with the org's `risk_thresholds` OrgConfig key."""
    cfg = dict(RISK_DEFAULTS)
    try:
        override = get_org_config(db, org_id, "risk_thresholds")
        if isinstance(override, dict):
            cfg.update(override)
    except Exception:
        _log.warning("risk_thresholds load failed for org %s — using defaults", org_id, exc_info=True)
    return cfg


def _canonical_env(environment: str | None) -> str | None:
    if not environment:
        return None
    return _ENV_ALIASES.get(environment.strip().lower())


def load_detection_rules(db: Session, org_id: int) -> dict:
    """Load the org's admin-managed rule rows: per-built-in overrides keyed by
    rule_key, plus enabled custom rules. Empty dicts when the org has no rows
    — evaluate_event then behaves exactly as before rule management existed."""
    from app.models import DetectionRule
    import json as _json

    overrides: dict[str, dict] = {}
    custom: list[dict] = []
    try:
        rows = db.query(DetectionRule).filter(DetectionRule.organization_id == org_id).all()
    except Exception:
        _log.warning("detection_rules load failed for org %s — using defaults", org_id, exc_info=True)
        rows = []
    for r in rows:
        cfg = {}
        if r.config_json:
            try:
                cfg = _json.loads(r.config_json) or {}
            except Exception:
                cfg = {}
        entry = {"rule_key": r.rule_key, "name": r.name, "enabled": bool(r.enabled),
                 "severity": r.severity, "config": cfg, "template_type": r.template_type}
        if r.source == "built_in":
            overrides[r.rule_key] = entry
        elif r.enabled:
            custom.append(entry)
    return {"builtin": overrides, "custom": custom}


def evaluate_event(db: Session, org_id: int, event: dict, config: dict | None = None,
                   rules: dict | None = None) -> RiskResult:
    """Evaluate risk rules against one normalized event dict.

    `event` uses the normalized TelemetryEvent field names (owner, team,
    environment, provider, model, cost_usd, latency_ms, status, tool_name,
    policy_action-from-payload under "upstream_policy_action").
    Returns RiskResult(score 0-100, reasons, policy_action).
    """
    cfg = config or load_risk_config(db, org_id)
    managed = rules if rules is not None else load_detection_rules(db, org_id)
    from app.detection_rule_templates import SEVERITY_WEIGHT, evaluate_custom_rule
    overrides = managed.get("builtin", {})

    def _on(rule_key: str) -> bool:
        ov = overrides.get(rule_key)
        return True if ov is None else ov["enabled"]

    def _w(rule_key: str, default: int) -> int:
        ov = overrides.get(rule_key)
        if ov is None:
            return default
        return SEVERITY_WEIGHT.get(ov["severity"], default)

    def _ov_cfg(rule_key: str, key: str, default):
        ov = overrides.get(rule_key)
        if ov and isinstance(ov["config"].get(key), (int, float)) and not isinstance(ov["config"].get(key), bool):
            return float(ov["config"][key])
        if ov and isinstance(ov["config"].get(key), list):
            return ov["config"][key]
        return default

    score = 0
    reasons: list[str] = []
    blocked = False

    def hit(weight: int, reason: str) -> None:
        nonlocal score
        score += weight
        reasons.append(reason)

    status = (event.get("status") or "ok").lower()
    environment = event.get("environment")
    canonical_env = _canonical_env(environment)
    model = event.get("model")
    provider = event.get("provider")
    team = event.get("team")

    # 1. Event reported an error.
    if status == "error" and _on("status_error"):
        hit(_w("status_error", 25), "Event reported an error")

    # 2. Upstream policy already blocked this action. (Never disable-able:
    # an upstream block is a fact about the event, not a tunable heuristic.)
    if status == "blocked" or (event.get("upstream_policy_action") or "").lower() == "block":
        hit(25, "Upstream policy blocked this action")
        blocked = True

    # 3-4. Missing ownership metadata.
    if not (event.get("owner") or "").strip() and _on("missing_owner"):
        hit(_w("missing_owner", 10), "Agent has no registered owner")
    if not (team or "").strip() and _on("missing_team"):
        hit(_w("missing_team", 10), "Agent has no team assignment")

    # 5. Unknown environment.
    if _on("unknown_environment"):
        if environment and canonical_env is None:
            hit(_w("unknown_environment", 15), f"Unknown environment '{environment}'")
        elif not environment:
            hit(10, "No environment declared")

    # 6. Unknown provider.
    if _on("unknown_provider"):
        resolved_provider = (provider or "").strip().lower()
        if resolved_provider and resolved_provider not in _KNOWN_PROVIDERS:
            hit(_w("unknown_provider", 10), f"Unrecognized provider '{provider}'")
        elif not resolved_provider and model:
            inferred = _infer_provider(model)
            if inferred == "unknown":
                hit(_w("unknown_provider", 10), "Provider could not be determined")

    # 7. Unknown model (not in the pricing registry).
    if model and _on("unknown_model"):
        try:
            pricing = get_active_pricing(db, model, org_id) or get_active_pricing(db, _normalize_model(model), org_id)
        except Exception:
            pricing = None
        if pricing is None:
            hit(_w("unknown_model", 15), f"Model '{model}' not in pricing registry")

    # 8. Cost exceeds threshold.
    cost = event.get("cost_usd")
    cost_threshold = _ov_cfg("cost_threshold", "cost_usd", cfg["cost_usd_threshold"])
    if cost is not None and cost > cost_threshold and _on("cost_threshold"):
        hit(_w("cost_threshold", 20), f"Cost ${cost:.2f} exceeds ${cost_threshold:.2f} threshold")

    # 9. Unusually high latency.
    latency = event.get("latency_ms")
    latency_threshold = _ov_cfg("latency_threshold", "latency_ms", cfg["latency_ms_threshold"])
    if latency is not None and latency > latency_threshold and _on("latency_threshold"):
        hit(_w("latency_threshold", 15), f"Latency {latency:.0f}ms exceeds {latency_threshold:.0f}ms threshold")

    # 10. Risky tool usage.
    tool = (event.get("tool_name") or "").strip().lower()
    risky_tools = {t.lower() for t in _ov_cfg("risky_tool", "tools", cfg.get("risky_tools", []))}
    if tool and tool in risky_tools and _on("risky_tool"):
        hit(_w("risky_tool", 25), f"Tool '{event.get('tool_name')}' is on the risky-tool list")

    # 11. Production agent using a non-approved model (existing policy engine).
    if canonical_env == "production" and model and _on("non_approved_model"):
        try:
            verdict = policy.check_model(db, org_id, team or "*", model)
        except Exception:
            verdict = {"allowed": True, "reason": None}
        if not verdict.get("allowed", True):
            hit(30, verdict.get("reason") or f"Model '{model}' is not approved for production")
            blocked = True

    # 12. Custom rules — approved templates only, validated config, no code.
    for rule in managed.get("custom", []):
        import json as _json
        reason = evaluate_custom_rule(rule["template_type"], _json.dumps(rule["config"]), event)
        if reason:
            hit(SEVERITY_WEIGHT.get(rule["severity"], 15), f"[{rule['name']}] {reason}")

    score = min(score, 100)
    if blocked:
        score = max(score, 80)
        action = "block"
    elif score >= cfg["warn_score"]:
        action = "warn"
    else:
        action = "allow"

    return RiskResult(score=score, reasons=reasons, policy_action=action)
