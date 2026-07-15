"""
Detection rule management — admin-only mutations, org-scoped reads.

GET  /detection-rules            any authenticated user (read-only view)
GET  /detection-rules/templates  any authenticated user
POST /detection-rules            admin only — custom rule from approved template
PATCH /detection-rules/{id}      admin only — enabled/severity/config/name/description
DELETE /detection-rules/{id}     admin only — custom rules only (built-ins disable-only)

Built-in rules are synthesized from risk_processor.RULE_CATALOG and merged
with any per-org override rows — no mass seeding. PATCHing a built-in creates
its override row on demand. Backend enforces authorization; the frontend
merely hides controls.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, require_admin
from app.models import DetectionRule
from app.risk_processor import RULE_CATALOG
from app.detection_rule_templates import TEMPLATES, VALID_SEVERITIES, validate_config, normalize_config

_log = logging.getLogger("ai_asset_mgmt.detection_rules")

router = APIRouter(tags=["Detection Rules"])

# Built-ins whose thresholds map to a template config (editable params).
_BUILTIN_TEMPLATE = {"cost_threshold": "cost_threshold", "latency_threshold": "latency_threshold",
                     "risky_tool": "tool_condition"}
# Default severity for built-ins, from their catalog weight.
_WEIGHT_SEVERITY = {10: "low", 15: "medium", 20: "medium", 25: "high", 30: "high"}


def _org_id(user) -> int:
    return user.organization_id if hasattr(user, "organization_id") else user.get("organization_id")


def _email(user) -> str | None:
    return getattr(user, "email", None) if not isinstance(user, dict) else user.get("email")


def _row_dict(r: DetectionRule) -> dict:
    cfg = {}
    if r.config_json:
        try:
            cfg = json.loads(r.config_json) or {}
        except Exception:
            cfg = {}
    return {
        "id": r.id, "rule_key": r.rule_key, "name": r.name, "description": r.description,
        "category": r.category, "severity": r.severity, "enabled": r.enabled,
        "source": r.source, "template_type": r.template_type, "config": cfg,
        "created_by": r.created_by, "updated_by": r.updated_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _builtin_defaults() -> list[dict]:
    """Synthesize the built-in rule list from RULE_CATALOG (deduped by rule_id)."""
    seen, out = set(), []
    for entry in RULE_CATALOG:
        if entry["rule_id"] in seen or entry["rule_id"] == "upstream_block":
            continue  # upstream_block is a fact about the event, not tunable
        seen.add(entry["rule_id"])
        out.append({
            "id": None, "rule_key": entry["rule_id"], "name": entry["rule_name"],
            "description": None, "category": entry["category"],
            "severity": _WEIGHT_SEVERITY.get(entry["weight"], "medium"),
            "enabled": True, "source": "built_in",
            "template_type": _BUILTIN_TEMPLATE.get(entry["rule_id"], ""),
            "config": {}, "created_by": None, "updated_by": None,
            "created_at": None, "updated_at": None,
        })
    return out


class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    template_type: str
    severity: str = "medium"
    enabled: bool = True
    config: dict


class RulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    severity: str | None = None
    enabled: bool | None = None
    config: dict | None = None


@router.get("/detection-rules")
async def list_detection_rules(user=Depends(get_current_user), db: Session = Depends(get_db)):
    org_id = _org_id(user)
    rows = db.query(DetectionRule).filter(DetectionRule.organization_id == org_id).all()
    by_key = {r.rule_key: r for r in rows}

    merged = []
    for b in _builtin_defaults():
        override = by_key.pop(b["rule_key"], None)
        merged.append(_row_dict(override) if override is not None else b)
    # Remaining rows are custom rules
    merged.extend(_row_dict(r) for r in by_key.values())
    is_admin = (getattr(user, "role", None) or (user.get("role") if isinstance(user, dict) else None)) == "admin" \
        or bool(getattr(user, "is_platform_admin", False))
    return {"rules": merged, "can_manage": is_admin}


@router.get("/detection-rules/templates")
async def list_templates(user=Depends(get_current_user)):
    return {"templates": [
        {"template_type": k, "label": t["label"], "category": t["category"], "params": t["params"]}
        for k, t in TEMPLATES.items()
    ]}


@router.post("/detection-rules", status_code=201)
async def create_detection_rule(
    body: RuleCreate,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    org_id = _org_id(user)
    if body.severity not in VALID_SEVERITIES:
        raise HTTPException(status_code=422, detail="severity must be low, medium, or high")
    err = validate_config(body.template_type, body.config)
    if err:
        raise HTTPException(status_code=422, detail=err)

    rule_key = f"custom_{__import__('uuid').uuid4().hex[:12]}"
    row = DetectionRule(
        organization_id=org_id, rule_key=rule_key, name=body.name.strip(),
        description=(body.description or "").strip() or None,
        category=TEMPLATES[body.template_type]["category"],
        severity=body.severity, enabled=body.enabled, source="custom",
        template_type=body.template_type,
        config_json=json.dumps(normalize_config(body.template_type, body.config)),
        created_by=_email(user), updated_by=_email(user),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_dict(row)


@router.patch("/detection-rules/{rule_id}")
async def update_detection_rule(
    rule_id: str,
    body: RulePatch,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """rule_id: numeric row id, or a built-in rule_key (creates the override
    row on demand so built-ins need no pre-seeding)."""
    org_id = _org_id(user)
    row = None
    if rule_id.isdigit():
        row = db.query(DetectionRule).filter(
            DetectionRule.organization_id == org_id, DetectionRule.id == int(rule_id)).first()
    if row is None:
        builtin = next((b for b in _builtin_defaults() if b["rule_key"] == rule_id), None)
        if builtin is None:
            raise HTTPException(status_code=404, detail="Rule not found")
        row = db.query(DetectionRule).filter(
            DetectionRule.organization_id == org_id, DetectionRule.rule_key == rule_id).first()
        if row is None:
            row = DetectionRule(
                organization_id=org_id, rule_key=builtin["rule_key"], name=builtin["name"],
                category=builtin["category"], severity=builtin["severity"], enabled=True,
                source="built_in", template_type=builtin["template_type"],
                created_by=_email(user),
            )
            db.add(row)

    if body.severity is not None:
        if body.severity not in VALID_SEVERITIES:
            raise HTTPException(status_code=422, detail="severity must be low, medium, or high")
        row.severity = body.severity
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.name is not None and row.source == "custom":
        row.name = body.name.strip()
    if body.description is not None and row.source == "custom":
        row.description = body.description.strip() or None
    if body.config is not None:
        if not row.template_type:
            raise HTTPException(status_code=422, detail="This rule has no editable parameters")
        err = validate_config(row.template_type, body.config)
        if err:
            raise HTTPException(status_code=422, detail=err)
        row.config_json = json.dumps(normalize_config(row.template_type, body.config))
    row.updated_by = _email(user)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _row_dict(row)


@router.delete("/detection-rules/{rule_id}")
async def delete_detection_rule(
    rule_id: int,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Custom rules only. Built-ins are disable-only (PATCH enabled=false) so
    the org's rule surface can always be restored to defaults."""
    org_id = _org_id(user)
    row = db.query(DetectionRule).filter(
        DetectionRule.organization_id == org_id, DetectionRule.id == rule_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if row.source != "custom":
        raise HTTPException(status_code=400, detail="Built-in rules cannot be deleted — disable them instead")
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": rule_id}
