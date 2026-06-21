"""Per-org key-value config store, shared between main.py and route modules."""
import json
import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session

_VALID_GUARD_MODES = {"observe", "alert", "enforce"}


def platform_default_mode() -> str:
    raw = os.getenv("GUARD_MODE", "").lower().strip()
    if raw in _VALID_GUARD_MODES:
        return raw
    legacy = os.getenv("GATEWAY_FAIL_MODE", "closed").lower().strip()
    return "observe" if legacy == "open" else "enforce"


PLATFORM_MODE: str = platform_default_mode()

DEFAULTS: dict = {
    "environments": ["production", "staging", "development"],
    "demo_mode": True,
    # "full" (default): store complete prompt + response text in telemetry.
    # "findings_only": for PII-flagged records, replace prompt + response with a
    # redaction notice and keep only the findings metadata. Reduces PII at-rest exposure.
    "pii_redaction_mode": "full",
}


def get_org_config(db: Session, org_id: int, key: str):
    from app.models import OrgConfig
    row = db.query(OrgConfig).filter(
        OrgConfig.organization_id == org_id,
        OrgConfig.key == key,
    ).first()
    if row is None:
        return DEFAULTS.get(key)
    try:
        return json.loads(row.value)
    except Exception:
        return row.value


def set_org_config(db: Session, org_id: int, key: str, value) -> None:
    from app.models import OrgConfig
    row = db.query(OrgConfig).filter(
        OrgConfig.organization_id == org_id,
        OrgConfig.key == key,
    ).first()
    encoded = json.dumps(value)
    if row:
        row.value = encoded
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(OrgConfig(organization_id=org_id, key=key, value=encoded))
    db.commit()
