"""
Asset taxonomy and discovery helpers for the LLM gateway.

Extracted from app/routes/proxy.py — _known_assets must remain module-level
so the in-memory cache is shared across all callers within a process.
"""
from sqlalchemy.orm import Session

# In-memory cache: known (org_id, asset_key) pairs already in asset_registry
_known_assets: set[tuple[int, str]] = set()


# ── Asset taxonomy constants ──────────────────────────────────────────────────

_WORKFLOW_UA   = {"n8n", "make.com", "zapier", "langgraph-workflow", "temporal"}
_COPILOT_UA    = {"copilot", "github-copilot", "salesforce-einstein", "ms-copilot"}
_SERVICE_NAMES = {"-service", "-api", "translation-", "classification-", "summariz"}


def _infer_asset_type(agent_name: str, user_agent: str) -> str:
    """Classify asset type from available signals."""
    ua  = (user_agent  or "").lower()
    nm  = (agent_name  or "").lower()
    if any(x in ua for x in _WORKFLOW_UA) or any(x in nm for x in {"workflow", "pipeline", "orchestrat"}):
        return "workflow"
    if any(x in ua for x in _COPILOT_UA) or "copilot" in nm:
        return "copilot"
    if any(x in nm for x in _SERVICE_NAMES) or any(x in nm for x in {"-svc", "translate", "classif", "summar"}):
        return "service"
    if any(x in nm for x in {"chatbot", "chat-", "-chat", "assistant", "helpdesk"}):
        return "application"
    return "agent"


def _infer_capabilities(headers: dict) -> str:
    """Infer capabilities from request headers. Returns JSON array string."""
    import json as _json
    caps = {"inference"}  # every LLM call has inference capability
    h = {k.lower(): v.lower() for k, v in headers.items()}
    if h.get("x-mcp-tool") or h.get("x-mcp-server"):
        caps.add("tool_execution")
        caps.add("external_api")
    if h.get("x-agent-workflow") or h.get("x-workflow-provider"):
        caps.add("tool_execution")
    if any(x in str(h) for x in ["retriev", "vector", "rag", "search"]):
        caps.add("retrieval")
    return _json.dumps(sorted(caps))


def _discover_asset(
    db: Session, org_id: int, asset_key: str, agent_id_raw: str,
    team: str | None = None, environment: str | None = None,
    owner: str | None = None, source_hint: str | None = None,
    confidence_score: float = 0.95,
    evidence_data: dict | None = None,
    request_headers: dict | None = None,
) -> None:
    """Idempotent: insert a verified unassigned asset_registry row on first sight of an agent."""
    if (org_id, asset_key) in _known_assets:
        return
    import json as _json
    from app.models import AssetRegistry as _AssetRegistry

    _DSOURCE_MAP = {
        "sdk_runtime":     "sdk_runtime",
        "explicit_header": "gateway_telemetry",
        "api_key_scope":   "gateway_telemetry",
    }
    disc_source = _DSOURCE_MAP.get(source_hint or "", "gateway_runtime")

    try:
        existing = db.query(_AssetRegistry).filter(
            _AssetRegistry.organization_id == org_id,
            _AssetRegistry.asset_key == asset_key,
        ).first()
        if not existing:
            _ua = (request_headers or {}).get("user-agent", "") if request_headers else ""
            db.add(_AssetRegistry(
                organization_id=org_id,
                asset_key=asset_key,
                agent_id_raw=agent_id_raw,
                agent_name=agent_id_raw,
                team=team,
                environment=environment,
                owner=owner,
                status="unassigned",
                source=source_hint or "gateway_runtime",
                discovery_status="verified",
                discovery_source=disc_source,
                discovery_reason="Agent auto-discovered from runtime gateway traffic",
                evidence=_json.dumps(evidence_data or {}),
                confidence_score=round(confidence_score * 100, 1),
                asset_type=_infer_asset_type(agent_id_raw, _ua),
                capabilities=_infer_capabilities(request_headers or {}),
            ))
            db.commit()
        elif existing.discovery_source == "gateway_runtime" and disc_source != "gateway_runtime":
            # Agent was first seen without SDK headers; upgrade to the better classification now
            existing.discovery_source = disc_source
            if source_hint:
                existing.source = source_hint
            db.commit()
        _known_assets.add((org_id, asset_key))
    except Exception:
        db.rollback()
