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


def evaluate_event(db: Session, org_id: int, event: dict, config: dict | None = None) -> RiskResult:
    """Evaluate risk rules against one normalized event dict.

    `event` uses the normalized TelemetryEvent field names (owner, team,
    environment, provider, model, cost_usd, latency_ms, status, tool_name,
    policy_action-from-payload under "upstream_policy_action").
    Returns RiskResult(score 0-100, reasons, policy_action).
    """
    cfg = config or load_risk_config(db, org_id)
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
    if status == "error":
        hit(25, "Event reported an error")

    # 2. Upstream policy already blocked this action.
    if status == "blocked" or (event.get("upstream_policy_action") or "").lower() == "block":
        hit(25, "Upstream policy blocked this action")
        blocked = True

    # 3-4. Missing ownership metadata.
    if not (event.get("owner") or "").strip():
        hit(10, "Agent has no registered owner")
    if not (team or "").strip():
        hit(10, "Agent has no team assignment")

    # 5. Unknown environment.
    if environment and canonical_env is None:
        hit(15, f"Unknown environment '{environment}'")
    elif not environment:
        hit(10, "No environment declared")

    # 6. Unknown provider.
    resolved_provider = (provider or "").strip().lower()
    if resolved_provider and resolved_provider not in _KNOWN_PROVIDERS:
        hit(10, f"Unrecognized provider '{provider}'")
    elif not resolved_provider and model:
        inferred = _infer_provider(model)
        if inferred == "unknown":
            hit(10, "Provider could not be determined")

    # 7. Unknown model (not in the pricing registry).
    if model:
        try:
            pricing = get_active_pricing(db, model, org_id) or get_active_pricing(db, _normalize_model(model), org_id)
        except Exception:
            pricing = None
        if pricing is None:
            hit(15, f"Model '{model}' not in pricing registry")

    # 8. Cost exceeds threshold.
    cost = event.get("cost_usd")
    if cost is not None and cost > cfg["cost_usd_threshold"]:
        hit(20, f"Cost ${cost:.2f} exceeds ${cfg['cost_usd_threshold']:.2f} threshold")

    # 9. Unusually high latency.
    latency = event.get("latency_ms")
    if latency is not None and latency > cfg["latency_ms_threshold"]:
        hit(15, f"Latency {latency:.0f}ms exceeds {cfg['latency_ms_threshold']:.0f}ms threshold")

    # 10. Risky tool usage.
    tool = (event.get("tool_name") or "").strip().lower()
    risky_tools = {t.lower() for t in cfg.get("risky_tools", [])}
    if tool and tool in risky_tools:
        hit(25, f"Tool '{event.get('tool_name')}' is on the risky-tool list")

    # 11. Production agent using a non-approved model (existing policy engine).
    if canonical_env == "production" and model:
        try:
            verdict = policy.check_model(db, org_id, team or "*", model)
        except Exception:
            verdict = {"allowed": True, "reason": None}
        if not verdict.get("allowed", True):
            hit(30, verdict.get("reason") or f"Model '{model}' is not approved for production")
            blocked = True

    score = min(score, 100)
    if blocked:
        score = max(score, 80)
        action = "block"
    elif score >= cfg["warn_score"]:
        action = "warn"
    else:
        action = "allow"

    return RiskResult(score=score, reasons=reasons, policy_action=action)
