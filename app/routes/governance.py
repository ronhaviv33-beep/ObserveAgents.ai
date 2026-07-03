from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    BudgetRuleCreate, BudgetRuleOut, BudgetStatusItem,
    PolicyRuleCreate, PolicyRuleOut,
    ScanRequest, ScanResponse, ScanFinding,
)
from app.auth import (
    get_current_user, require_page_access,
    resolve_team_scope, is_deny_sentinel, require_tenancy_hardened,
)
from app import budget as bud
from app import policy as pol
from app import telemetry as tel
from app.scanner import scan
from app.org_config import get_org_config as _get_org_config

router = APIRouter()

# ── Security ──────────────────────────────────────────────────────────────────

@router.post("/security/scan", response_model=ScanResponse, tags=["POST — Ask / Create"])
def security_scan(req: ScanRequest, _=Depends(get_current_user)):
    result = scan(req.text)
    return ScanResponse(
        is_sensitive=result.is_sensitive,
        findings=[ScanFinding(type=f.type, severity=f.severity, sample=f.sample)
                  for f in result.findings],
    )


@router.get("/security/alerts", tags=["GET — Read / Monitor"])
def security_alerts(db: Session = Depends(get_db), current_user=Depends(get_current_user), _: None = Depends(require_tenancy_hardened)):
    ts = resolve_team_scope(current_user, db)
    if is_deny_sentinel(ts):
        return []
    _dm = bool(_get_org_config(db, current_user.organization_id, "demo_mode"))
    return tel.get_security_alerts(db, organization_id=current_user.organization_id, team_scope=ts, demo_mode=_dm)


# ── Budgets ───────────────────────────────────────────────────────────────────

@router.post("/budgets", response_model=BudgetRuleOut, status_code=201, tags=["POST — Ask / Create"])
def create_budget(rule: BudgetRuleCreate, db: Session = Depends(get_db), actor=Depends(require_page_access("settings"))):
    # Gated on the settings page (admin-only) rather than the budgets page:
    # the budgets page is readable by all roles, but rules stay admin-managed.
    ts = resolve_team_scope(actor, db)
    if is_deny_sentinel(ts):
        raise HTTPException(status_code=403, detail="No team assigned — cannot create budget rules")
    effective_team = ts if ts is not None else rule.team
    if ts is not None and rule.team != ts:
        raise HTTPException(status_code=403, detail=f"Team-scoped role may only create rules for team '{ts}'")
    return bud.create_rule(db, organization_id=actor.organization_id, team=effective_team,
                           agent=rule.agent, limit_usd=rule.limit_usd, period=rule.period, action=rule.action)


@router.get("/budgets", response_model=list[BudgetRuleOut], tags=["GET — Read / Monitor"])
def list_budgets(db: Session = Depends(get_db), actor=Depends(get_current_user)):
    ts = resolve_team_scope(actor, db)
    if is_deny_sentinel(ts):
        return []
    return bud.get_rules(db, organization_id=actor.organization_id, team_scope=ts)


@router.delete("/budgets/{rule_id}", status_code=204, tags=["DELETE — Remove"])
def delete_budget(rule_id: int, db: Session = Depends(get_db), actor=Depends(require_page_access("settings"))):
    ts = resolve_team_scope(actor, db)
    if is_deny_sentinel(ts):
        raise HTTPException(status_code=404, detail="Budget rule not found")
    if not bud.delete_rule(db, rule_id, organization_id=actor.organization_id, team_scope=ts):
        raise HTTPException(status_code=404, detail="Budget rule not found")


@router.get("/budgets/status", response_model=list[BudgetStatusItem], tags=["GET — Read / Monitor"])
def budget_status(db: Session = Depends(get_db), actor=Depends(get_current_user)):
    ts = resolve_team_scope(actor, db)
    if is_deny_sentinel(ts):
        return []
    return bud.get_status(db, organization_id=actor.organization_id, team_scope=ts)


# ── Policies ──────────────────────────────────────────────────────────────────

@router.post("/policies", response_model=PolicyRuleOut, status_code=201, tags=["POST — Ask / Create"])
def create_policy(rule: PolicyRuleCreate, db: Session = Depends(get_db), actor=Depends(require_page_access("settings"))):
    ts = resolve_team_scope(actor, db)
    if is_deny_sentinel(ts):
        raise HTTPException(status_code=403, detail="No team assigned — cannot create policy rules")
    if ts is not None and rule.team != ts:
        raise HTTPException(status_code=403, detail=f"Team-scoped role may only create rules for team '{ts}'")
    return pol.create_rule(db, organization_id=actor.organization_id, team=rule.team, rule_type=rule.rule_type, value=rule.value)


@router.get("/policies", response_model=list[PolicyRuleOut], tags=["GET — Read / Monitor"])
def list_policies(db: Session = Depends(get_db), actor=Depends(get_current_user)):
    ts = resolve_team_scope(actor, db)
    if is_deny_sentinel(ts):
        return []
    return pol.get_rules(db, organization_id=actor.organization_id, team_scope=ts)


@router.delete("/policies/{rule_id}", status_code=204, tags=["DELETE — Remove"])
def delete_policy(rule_id: int, db: Session = Depends(get_db), actor=Depends(require_page_access("settings"))):
    ts = resolve_team_scope(actor, db)
    if is_deny_sentinel(ts):
        raise HTTPException(status_code=404, detail="Policy rule not found")
    if not pol.delete_rule(db, rule_id, organization_id=actor.organization_id, team_scope=ts):
        raise HTTPException(status_code=404, detail="Policy rule not found")
