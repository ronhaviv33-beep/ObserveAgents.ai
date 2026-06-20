"""
Live Pricing Registry — versioned, DB-backed model pricing.

Design principles:
  - Never UPDATE a pricing row; always INSERT a new version
  - organization_id=NULL → global (built-in/synced); non-NULL → org override
  - Sync compares DB against built-in COST_PER_1M; creates new versions on drift
  - Fallback pricing prevents cost-calculation breakage if registry is missing
  - Background thread runs sync every SYNC_INTERVAL_SECONDS
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    ModelPricing, PricingChangeLog,
    COST_PER_1M, PRICING_LAST_UPDATED, _DEFAULT_PRICING, _normalize_model,
)

_log = logging.getLogger("ai_asset_mgmt.pricing_registry")

SYNC_INTERVAL_SECONDS = 3600  # 1 hour
STALE_WARNING_HOURS   = 24
STALE_CRITICAL_HOURS  = 48
FALLBACK_INPUT_CPM    = 2.50
FALLBACK_OUTPUT_CPM   = 10.00

# ── Provider classification ───────────────────────────────────────────────────

_PROVIDER_PREFIXES: list[tuple[str, str]] = [
    ("claude",  "anthropic"),
    ("gpt",     "openai"),
    ("o1",      "openai"),
    ("o3",      "openai"),
    ("o4",      "openai"),
    ("gemini",  "google"),
    ("llama",   "local"),
]


def _infer_provider(model: str) -> str:
    m = _normalize_model(model or "").lower()
    for prefix, provider in _PROVIDER_PREFIXES:
        if m.startswith(prefix) or prefix in m:
            return provider
    return "unknown"


def _builtin_model_list() -> list[tuple[str, str, float, float]]:
    """Return (provider, model, input_cpm, output_cpm) from COST_PER_1M."""
    rows = []
    for model, pricing in COST_PER_1M.items():
        rows.append((_infer_provider(model), model, pricing["prompt"], pricing["completion"]))
    return rows


# ── Thread-safe sync state ────────────────────────────────────────────────────

_sync_lock = threading.Lock()
_sync_state: dict = {
    "last_sync_at": None,
    "next_sync_at": None,
    "is_running":   False,
    "results":      {},   # provider → {status, models_updated, prices_changed, error}
}

_bg_thread: Optional[threading.Thread] = None


def get_sync_status() -> dict:
    with _sync_lock:
        return dict(_sync_state)


# ── Core registry operations ──────────────────────────────────────────────────

def get_active_pricing(
    db: Session,
    model_name: str,
    organization_id: Optional[int] = None,
    as_of: Optional[datetime] = None,
) -> Optional[ModelPricing]:
    """
    Return the active pricing for a model.

    Priority:
    1. Org-specific override (if organization_id provided)
    2. Global built-in / synced pricing

    If as_of is set, returns the version that was active at that datetime
    (enables historically-accurate cost calculation).
    """
    now = as_of or datetime.now(timezone.utc)

    def _query(org_id):
        q = db.query(ModelPricing).filter(
            ModelPricing.model_name == model_name,
            ModelPricing.organization_id == org_id,
            ModelPricing.effective_from <= now,
        ).filter(
            (ModelPricing.effective_to == None) | (ModelPricing.effective_to >= now)  # noqa: E711
        )
        if as_of is None:
            q = q.filter(ModelPricing.is_active == True)  # noqa: E712
        return q.order_by(ModelPricing.version.desc()).first()

    # Try org-specific override first
    if organization_id is not None:
        rec = _query(organization_id)
        if rec:
            return rec

    # Fall back to global pricing
    return _query(None)


def _fallback_pricing() -> ModelPricing:
    """Conservative fallback when no registry entry exists."""
    return ModelPricing(
        provider="fallback",
        model_name="unknown",
        input_cost_per_million_tokens=FALLBACK_INPUT_CPM,
        output_cost_per_million_tokens=FALLBACK_OUTPUT_CPM,
        version=0,
        source="fallback",
        is_active=False,
        created_by="system",
    )


def calculate_cost(
    db: Session,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    organization_id: Optional[int] = None,
    as_of: Optional[datetime] = None,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> tuple[float, dict]:
    """
    Calculate request cost using the versioned pricing registry.

    Returns: (cost_usd, metadata_dict)
    metadata includes pricing_version, source, is_fallback, pricing_age_hours.
    """
    # Normalize model name (strip date suffixes like -2024-07-18)
    norm = _normalize_model(model)
    pricing = get_active_pricing(db, model, organization_id, as_of)
    if pricing is None:
        pricing = get_active_pricing(db, norm, organization_id, as_of)
    is_fallback = pricing is None
    if is_fallback:
        pricing = _fallback_pricing()

    input_cost  = (prompt_tokens / 1_000_000) * pricing.input_cost_per_million_tokens
    output_cost = (completion_tokens / 1_000_000) * pricing.output_cost_per_million_tokens
    cache_r     = (cache_read_tokens  / 1_000_000) * (pricing.cache_read_cost_per_million_tokens  or 0)
    cache_w     = (cache_write_tokens / 1_000_000) * (pricing.cache_write_cost_per_million_tokens or 0)
    total       = round(input_cost + output_cost + cache_r + cache_w, 8)

    now_utc = datetime.now(timezone.utc)
    last_checked = pricing.last_checked_at
    if last_checked and last_checked.tzinfo is None:
        last_checked = last_checked.replace(tzinfo=timezone.utc)
    age_hours = ((now_utc - last_checked).total_seconds() / 3600) if last_checked else None

    return total, {
        "pricing_version":  pricing.version,
        "pricing_source":   pricing.source,
        "is_fallback":      is_fallback,
        "pricing_age_hours": round(age_hours, 1) if age_hours is not None else None,
        "effective_from":   pricing.effective_from.isoformat() if pricing.effective_from else None,
    }


def _deactivate(db: Session, current: ModelPricing, now: datetime) -> None:
    """Mark an existing active record as superseded."""
    current.is_active    = False
    current.effective_to = now


def _log_change(
    db: Session,
    provider: str,
    model_name: str,
    old: Optional[ModelPricing],
    new_version: int,
    new_input: float,
    new_output: float,
    reason: str,
    created_by: str = "system",
    org_id: Optional[int] = None,
) -> None:
    db.add(PricingChangeLog(
        organization_id = org_id,
        provider        = provider,
        model_name      = model_name,
        old_version     = old.version if old else None,
        new_version     = new_version,
        change_reason   = reason,
        input_price_old  = old.input_cost_per_million_tokens if old else None,
        input_price_new  = new_input,
        output_price_old = old.output_cost_per_million_tokens if old else None,
        output_price_new = new_output,
        created_by       = created_by,
    ))


# ── Seeding ───────────────────────────────────────────────────────────────────

def seed_defaults(db: Session) -> int:
    """
    Seed the model_pricing table from COST_PER_1M if records don't exist yet.
    Idempotent — safe to call on every startup.
    Returns the number of new records created.
    """
    created = 0
    now = datetime.now(timezone.utc)

    for provider, model, input_cpm, output_cpm in _builtin_model_list():
        existing = get_active_pricing(db, model)
        if existing is not None:
            continue  # already seeded — sync() handles updates

        new_rec = ModelPricing(
            organization_id              = None,
            provider                     = provider,
            model_name                   = model,
            input_cost_per_million_tokens  = input_cpm,
            output_cost_per_million_tokens = output_cpm,
            version                      = 1,
            effective_from               = now,
            is_active                    = True,
            source                       = "builtin",
            last_checked_at              = now,
            sync_status                  = "ok",
            created_by                   = "system",
        )
        db.add(new_rec)
        db.flush()
        _log_change(db, provider, model, None, 1, input_cpm, output_cpm, "initial_seed")
        created += 1

    if created:
        db.commit()
        _log.info("Pricing registry: seeded %d models", created)
    return created


# ── Sync ──────────────────────────────────────────────────────────────────────

def run_sync(db: Session) -> dict:
    """
    Compare DB pricing against built-in COST_PER_1M.
    Creates new versions when prices have drifted (e.g., after a code update).
    Updates last_checked_at on unchanged records.
    Returns a results dict per provider.
    """
    now     = datetime.now(timezone.utc)
    results = {}

    for provider, model, builtin_input, builtin_output in _builtin_model_list():
        if provider not in results:
            results[provider] = {"status": "ok", "models_updated": 0, "prices_changed": 0, "error": None}

        try:
            current = get_active_pricing(db, model)

            if current is None:
                # New model not yet seeded
                db.add(ModelPricing(
                    organization_id              = None,
                    provider                     = provider,
                    model_name                   = model,
                    input_cost_per_million_tokens  = builtin_input,
                    output_cost_per_million_tokens = builtin_output,
                    version                      = 1,
                    effective_from               = now,
                    is_active                    = True,
                    source                       = "sync",
                    last_checked_at              = now,
                    sync_status                  = "ok",
                    created_by                   = "system",
                ))
                db.flush()
                _log_change(db, provider, model, None, 1, builtin_input, builtin_output, "initial_seed")
                results[provider]["models_updated"] += 1
                results[provider]["prices_changed"]  += 1

            elif (abs(current.input_cost_per_million_tokens  - builtin_input)  > 1e-6 or
                  abs(current.output_cost_per_million_tokens - builtin_output) > 1e-6):
                # Price changed — create new version
                new_v = current.version + 1
                _deactivate(db, current, now)
                db.flush()
                db.add(ModelPricing(
                    organization_id              = None,
                    provider                     = provider,
                    model_name                   = model,
                    input_cost_per_million_tokens  = builtin_input,
                    output_cost_per_million_tokens = builtin_output,
                    version                      = new_v,
                    effective_from               = now,
                    is_active                    = True,
                    source                       = "sync",
                    last_checked_at              = now,
                    sync_status                  = "ok",
                    created_by                   = "system",
                ))
                db.flush()
                _log_change(db, provider, model, current, new_v, builtin_input, builtin_output, "sync_detected")
                results[provider]["models_updated"] += 1
                results[provider]["prices_changed"]  += 1
                _log.info("Pricing updated: %s %s v%d → v%d", provider, model, current.version, new_v)

            else:
                # Price unchanged — just refresh timestamp
                current.last_checked_at = now
                current.sync_status     = "ok"
                current.sync_error      = None
                results[provider]["models_updated"] += 1

        except Exception as exc:
            results[provider]["status"] = "failed"
            results[provider]["error"]  = str(exc)
            _log.warning("Sync failed for %s/%s: %s", provider, model, exc)

    db.commit()
    return results


def _do_background_sync() -> None:
    """Run one sync cycle in the background thread, create its own session."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        results = run_sync(db)
        now = datetime.now(timezone.utc)
        with _sync_lock:
            _sync_state["last_sync_at"]  = now.isoformat()
            _sync_state["next_sync_at"]  = (now + timedelta(seconds=SYNC_INTERVAL_SECONDS)).isoformat()
            _sync_state["results"]       = results
            _sync_state["is_running"]    = False
        _log.info("Background pricing sync complete")
    except Exception as exc:
        _log.error("Background pricing sync error: %s", exc)
        with _sync_lock:
            _sync_state["is_running"] = False
    finally:
        db.close()


def _sync_loop() -> None:
    """Long-running daemon thread: sync → sleep → repeat."""
    while True:
        time.sleep(SYNC_INTERVAL_SECONDS)
        with _sync_lock:
            if _sync_state["is_running"]:
                continue
            _sync_state["is_running"] = True
        _do_background_sync()


def start_background_sync() -> None:
    """Start the background pricing sync thread (call once on app startup)."""
    global _bg_thread
    if _bg_thread is not None and _bg_thread.is_alive():
        return
    _bg_thread = threading.Thread(target=_sync_loop, name="pricing-sync", daemon=True)
    _bg_thread.start()
    # Set next_sync_at
    with _sync_lock:
        _sync_state["next_sync_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=SYNC_INTERVAL_SECONDS)
        ).isoformat()
    _log.info("Pricing sync background thread started (interval=%ds)", SYNC_INTERVAL_SECONDS)


def trigger_sync_async() -> None:
    """Trigger an immediate sync in a one-shot background thread."""
    with _sync_lock:
        if _sync_state["is_running"]:
            return
        _sync_state["is_running"] = True
    t = threading.Thread(target=_do_background_sync, name="pricing-sync-oneshot", daemon=True)
    t.start()


# ── Admin override ────────────────────────────────────────────────────────────

def apply_override(
    db: Session,
    organization_id: int,
    provider: str,
    model_name: str,
    input_cost: float,
    output_cost: float,
    created_by: str,
    cache_read_cost: Optional[float] = None,
    cache_write_cost: Optional[float] = None,
    reason: str = "",
) -> ModelPricing:
    """
    Apply an org-specific pricing override.
    Deactivates the current org override (or global) for this model and creates a new version.
    """
    now = datetime.now(timezone.utc)

    # Find existing org-specific record
    current = (
        db.query(ModelPricing).filter(
            ModelPricing.model_name     == model_name,
            ModelPricing.organization_id == organization_id,
            ModelPricing.is_active      == True,  # noqa: E712
        ).order_by(ModelPricing.version.desc()).first()
    )

    new_version = (current.version + 1) if current else 1

    if current:
        _deactivate(db, current, now)
        db.flush()

    new_rec = ModelPricing(
        organization_id                  = organization_id,
        provider                         = provider,
        model_name                       = model_name,
        input_cost_per_million_tokens    = input_cost,
        output_cost_per_million_tokens   = output_cost,
        cache_read_cost_per_million_tokens  = cache_read_cost,
        cache_write_cost_per_million_tokens = cache_write_cost,
        version                          = new_version,
        effective_from                   = now,
        is_active                        = True,
        source                           = "admin_override",
        last_checked_at                  = now,
        sync_status                      = "override",
        created_by                       = created_by,
        override_reason                  = reason,
    )
    db.add(new_rec)
    db.flush()
    _log_change(db, provider, model_name, current, new_version,
                input_cost, output_cost, "admin_override", created_by, organization_id)
    db.commit()
    return new_rec


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_all_pricing(
    db: Session,
    organization_id: Optional[int] = None,
    provider: Optional[str] = None,
    active_only: bool = True,
    include_history: bool = False,
) -> list[dict]:
    """
    List pricing records.
    Merges global records with any org-specific overrides for the given org.
    """
    q = db.query(ModelPricing)
    if active_only:
        q = q.filter(ModelPricing.is_active == True)  # noqa: E712
    if provider:
        q = q.filter(ModelPricing.provider == provider)

    # Get global records + org overrides
    if organization_id is not None:
        q = q.filter(
            (ModelPricing.organization_id == None) |  # noqa: E711
            (ModelPricing.organization_id == organization_id)
        )
    else:
        q = q.filter(ModelPricing.organization_id == None)  # noqa: E711

    if not include_history:
        q = q.order_by(ModelPricing.provider, ModelPricing.model_name)
    else:
        q = q.order_by(ModelPricing.provider, ModelPricing.model_name, ModelPricing.version.desc())

    now = datetime.now(timezone.utc)
    results = []
    for r in q.all():
        lc = r.last_checked_at
        if lc and lc.tzinfo is None:
            lc = lc.replace(tzinfo=timezone.utc)
        age_h = round((now - lc).total_seconds() / 3600, 1) if lc else None

        ef = r.effective_from
        if ef and ef.tzinfo is None:
            ef = ef.replace(tzinfo=timezone.utc)

        results.append({
            "id":               r.id,
            "organization_id":  r.organization_id,
            "provider":         r.provider,
            "model_name":       r.model_name,
            "input_cost_per_million":  r.input_cost_per_million_tokens,
            "output_cost_per_million": r.output_cost_per_million_tokens,
            "cache_read_cost_per_million":  r.cache_read_cost_per_million_tokens,
            "cache_write_cost_per_million": r.cache_write_cost_per_million_tokens,
            "version":          r.version,
            "is_active":        r.is_active,
            "effective_from":   ef.isoformat() if ef else None,
            "effective_to":     r.effective_to.isoformat() if r.effective_to else None,
            "source":           r.source,
            "source_url":       r.source_url,
            "last_checked_at":  lc.isoformat() if lc else None,
            "age_hours":        age_h,
            "sync_status":      r.sync_status,
            "sync_error":       r.sync_error,
            "created_by":       r.created_by,
            "override_reason":  r.override_reason,
            "is_override":      r.organization_id is not None,
        })
    return results


def get_model_history(
    db: Session,
    provider: str,
    model_name: str,
    organization_id: Optional[int] = None,
) -> list[dict]:
    """All versions for a specific model, newest first."""
    q = db.query(ModelPricing).filter(
        ModelPricing.provider   == provider,
        ModelPricing.model_name == model_name,
    )
    if organization_id is not None:
        q = q.filter(
            (ModelPricing.organization_id == None) |  # noqa: E711
            (ModelPricing.organization_id == organization_id)
        )
    else:
        q = q.filter(ModelPricing.organization_id == None)  # noqa: E711

    rows = q.order_by(ModelPricing.version.desc()).all()
    return [
        {
            "version":         r.version,
            "input_cost_per_million":  r.input_cost_per_million_tokens,
            "output_cost_per_million": r.output_cost_per_million_tokens,
            "is_active":       r.is_active,
            "effective_from":  r.effective_from.isoformat() if r.effective_from else None,
            "effective_to":    r.effective_to.isoformat()   if r.effective_to   else None,
            "source":          r.source,
            "sync_status":     r.sync_status,
            "created_by":      r.created_by,
            "override_reason": r.override_reason,
        }
        for r in rows
    ]


def get_pricing_status(db: Session, organization_id: Optional[int] = None) -> dict:
    """
    Summarize pricing freshness for dashboard warnings.
    Returns: {warnings: [...], by_provider: {...}}
    """
    now  = datetime.now(timezone.utc)
    recs = get_all_pricing(db, organization_id, active_only=True)

    by_provider: dict[str, dict] = {}
    for r in recs:
        p  = r["provider"]
        ah = r["age_hours"] or 0
        if p not in by_provider:
            by_provider[p] = {"model_count": 0, "max_age_hours": 0, "has_override": False, "sync_status": "ok"}
        by_provider[p]["model_count"] += 1
        by_provider[p]["max_age_hours"] = max(by_provider[p]["max_age_hours"], ah)
        if r["is_override"]:
            by_provider[p]["has_override"] = True
        if r["sync_status"] not in ("ok", "override"):
            by_provider[p]["sync_status"] = r["sync_status"]

    warnings = []
    for provider, info in by_provider.items():
        age = info["max_age_hours"]
        if age >= STALE_CRITICAL_HOURS:
            warnings.append({"level": "critical", "provider": provider,
                             "message": f"{provider.capitalize()} pricing is {age:.0f}h old — refresh recommended"})
        elif age >= STALE_WARNING_HOURS:
            warnings.append({"level": "warning", "provider": provider,
                             "message": f"{provider.capitalize()} pricing is {age:.0f}h old"})
        if info["has_override"]:
            warnings.append({"level": "info", "provider": provider,
                             "message": f"{provider.capitalize()}: org-specific pricing override active"})
        if info["sync_status"] == "failed":
            warnings.append({"level": "critical", "provider": provider,
                             "message": f"{provider.capitalize()}: last sync failed — using stale pricing"})

    total_models = sum(v["model_count"] for v in by_provider.values())

    sync = get_sync_status()
    return {
        "total_models":    total_models,
        "by_provider":     by_provider,
        "warnings":        warnings,
        "last_sync_at":    sync["last_sync_at"],
        "next_sync_at":    sync["next_sync_at"],
        "pricing_updated": PRICING_LAST_UPDATED,
    }
