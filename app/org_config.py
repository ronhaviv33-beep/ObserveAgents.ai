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
    # NOTE: the effective default for demo_mode is computed dynamically by
    # _get_default() from the global APP_ENV/DEMO_MODE switch — production orgs
    # default to False (real/empty data), the demo service defaults to True.
    "demo_mode": False,
    # "full" (default): store complete prompt + response text in telemetry.
    # "findings_only": for PII-flagged records, replace prompt + response with a
    # redaction notice and keep only the findings metadata. Reduces PII at-rest exposure.
    "pii_redaction_mode": "full",
    # pii_detection_enabled: when False (default), PII scanning runs but results are
    # not used in risk scoring or surfaced as primary UI signals. Enable per-org for
    # customers that want sensitive-content runtime safety signals.
    "pii_detection_enabled": False,
    # Customer-defined OTel attribute aliases {custom_key: canonical_key},
    # validated against app/otel_attribute_mapping.ALLOWED_TARGETS and applied
    # as a pre-extraction pass during OTLP ingestion.
    "otel_attribute_mapping": {},
    # Per-org overrides for telemetry risk scoring (merged over
    # app/risk_processor.RISK_DEFAULTS). Empty dict = use defaults.
    "risk_thresholds": {},
}


def _get_default(key):
    """Resolve the default for a config key. demo_mode follows the global switch."""
    if key == "demo_mode":
        from app.config import is_demo_mode
        return is_demo_mode()
    return DEFAULTS.get(key)


def get_org_config_multi(db: Session, org_id: int, keys: list) -> dict:
    """Fetch multiple org config keys in a single query. Returns dict of key → value."""
    from app.models import OrgConfig
    rows = db.query(OrgConfig).filter(
        OrgConfig.organization_id == org_id,
        OrgConfig.key.in_(keys),
    ).all()
    result = {k: _get_default(k) for k in keys}
    for row in rows:
        try:
            result[row.key] = json.loads(row.value)
        except Exception:
            result[row.key] = row.value
    return result


def get_org_config(db: Session, org_id: int, key: str):
    from app.models import OrgConfig
    row = db.query(OrgConfig).filter(
        OrgConfig.organization_id == org_id,
        OrgConfig.key == key,
    ).first()
    if row is None:
        return _get_default(key)
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
