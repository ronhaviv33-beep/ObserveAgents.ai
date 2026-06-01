from sqlalchemy.orm import Session
from app.models import PolicyRule


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def create_rule(db: Session, team: str, rule_type: str, value: str) -> PolicyRule:
    rule = PolicyRule(team=team, rule_type=rule_type, value=value)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def get_rules(db: Session) -> list[PolicyRule]:
    return db.query(PolicyRule).order_by(PolicyRule.created_at.desc()).all()


def delete_rule(db: Session, rule_id: int) -> bool:
    rule = db.query(PolicyRule).filter(PolicyRule.id == rule_id).first()
    if not rule:
        return False
    db.delete(rule)
    db.commit()
    return True


# ─── Enforcement ──────────────────────────────────────────────────────────────

def check_model(db: Session, team: str, model: str) -> dict:
    """
    Returns {"allowed": bool, "reason": str | None}

    Rule precedence (first match wins):
      1. block_model  for this team or "*"  → blocked
      2. allow_model  for this team or "*"  → allowed
      3. No rules at all                    → allowed
      4. allow_model rules exist but none match this model → blocked
    """
    rules = db.query(PolicyRule).filter(
        PolicyRule.team.in_([team, "*"])
    ).all()

    if not rules:
        return {"allowed": True, "reason": None}

    # Check explicit blocks first
    for r in rules:
        if r.rule_type == "block_model" and (r.value == model or r.value == "*"):
            return {
                "allowed": False,
                "reason": f"Model '{model}' is blocked for team '{team}' by policy rule #{r.id}.",
            }

    # Check allow list — if any allow_model rules exist, model must be in them
    allow_rules = [r for r in rules if r.rule_type == "allow_model"]
    if allow_rules:
        allowed_models = {r.value for r in allow_rules}
        if model not in allowed_models and "*" not in allowed_models:
            return {
                "allowed": False,
                "reason": (
                    f"Model '{model}' is not on the approved list for team '{team}'. "
                    f"Approved: {', '.join(sorted(allowed_models))}."
                ),
            }

    return {"allowed": True, "reason": None}
