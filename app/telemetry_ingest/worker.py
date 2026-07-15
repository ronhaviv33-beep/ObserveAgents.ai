"""
Background ingest worker: drains the telemetry_events_raw queue.

Design (mirrors the app/pricing_registry.py in-process daemon thread — the
established background-work pattern in this codebase; no external queue):

  - The API route inserts pending rows and calls kick(); the worker thread
    wakes immediately (threading.Event) or on its poll interval.
  - drain_once(db) is the synchronous core: claim a batch -> normalize ->
    risk-score -> insert TelemetryEvent -> mark processed -> recompute the
    touched daily metric buckets. Tests call it directly.
  - At-least-once with idempotent processing: a crash mid-batch leaves rows
    in status=processing; stale-claim recovery flips them back to pending on
    the next cycle, and the unique (org_id, event_id) constraint on
    telemetry_events makes re-processing a no-op.

Env switches:
  TELEMETRY_WORKER_ENABLED=false  -> never start the thread
  TELEMETRY_WORKER_MODE=inline    -> no thread; the API route drains
                                     synchronously after each batch (tests)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import TelemetryEvent, TelemetryEventRaw
from app import risk_processor
from app.telemetry_ingest import metrics as metrics_agg
from app.telemetry_ingest import normalizer

_log = logging.getLogger("ai_asset_mgmt.telemetry_worker")

POLL_INTERVAL_SECONDS = 2.0
CLAIM_BATCH_SIZE = 200
MAX_ATTEMPTS = 3
STALE_PROCESSING_SECONDS = 300

_worker_thread: threading.Thread | None = None
_thread_lock = threading.Lock()
_wake = threading.Event()


def _inline_mode() -> bool:
    return os.getenv("TELEMETRY_WORKER_MODE", "").lower() == "inline"


def _worker_enabled() -> bool:
    return os.getenv("TELEMETRY_WORKER_ENABLED", "true").lower() != "false" and not _inline_mode()


def kick(db: Session | None = None) -> None:
    """Signal that new work is queued. In inline mode (tests), drain
    synchronously on the caller's session; otherwise wake the thread."""
    if _inline_mode():
        if db is not None:
            drain_all(db)
        return
    _wake.set()


def _recover_stale_claims(db: Session) -> int:
    """Rows stuck in `processing` past the timeout were abandoned by a dead
    process — put them back in the queue (crash safety)."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_PROCESSING_SECONDS)
    stale = db.query(TelemetryEventRaw).filter(
        TelemetryEventRaw.status == "processing",
        TelemetryEventRaw.claimed_at < cutoff,
    ).all()
    for row in stale:
        row.status = "pending"
    if stale:
        db.commit()
        _log.info("telemetry worker: recovered %d stale claims", len(stale))
    return len(stale)


def _process_row(db: Session, row: TelemetryEventRaw,
                 risk_configs: dict[int, dict]) -> tuple[int, str, datetime] | None:
    """Normalize + risk-score + persist one queued event.
    Returns the touched (org_id, agent_id, timestamp) on success, None on failure."""
    raw = json.loads(row.raw_payload)
    normalized = normalizer.normalize(db, row.organization_id, raw, received_at=row.received_at)
    upstream_action = normalized.pop("upstream_policy_action", None)

    org_id = row.organization_id
    if org_id not in risk_configs:
        risk_configs[org_id] = {
            "config": risk_processor.load_risk_config(db, org_id),
            "rules": risk_processor.load_detection_rules(db, org_id),
        }
    risk = risk_processor.evaluate_event(
        db, org_id,
        {**normalized, "upstream_policy_action": upstream_action},
        config=risk_configs[org_id]["config"],
        rules=risk_configs[org_id]["rules"],
    )

    event = TelemetryEvent(
        organization_id=org_id,
        event_id=row.event_id,
        raw_id=row.id,
        api_key_id=row.api_key_id,
        risk_score=risk.score,
        risk_reasons=json.dumps(risk.reasons) if risk.reasons else None,
        policy_action=risk.policy_action,
        **normalized,
    )
    try:
        with db.begin_nested():
            db.add(event)
    except IntegrityError:
        # Already normalized by a previous (crashed/replayed) run — the
        # unique (org_id, event_id) constraint makes reprocessing a no-op.
        pass
    return org_id, normalized["agent_id"], normalized["timestamp"]


def drain_once(db: Session) -> int:
    """Claim and process one batch of pending queue rows. Returns the number
    of rows claimed (0 = queue empty)."""
    _recover_stale_claims(db)

    rows = db.query(TelemetryEventRaw).filter(
        TelemetryEventRaw.status == "pending",
    ).order_by(TelemetryEventRaw.id).limit(CLAIM_BATCH_SIZE).all()
    if not rows:
        return 0

    now = datetime.now(timezone.utc)
    for row in rows:
        row.status = "processing"
        row.claimed_at = now
        row.attempts = (row.attempts or 0) + 1
    db.commit()

    touched: set[metrics_agg.Bucket] = set()
    risk_configs: dict[int, dict] = {}
    for row in rows:
        try:
            result = _process_row(db, row, risk_configs)
            row.status = "processed"
            row.processed_at = datetime.now(timezone.utc)
            row.error = None
            if result is not None:
                org_id, agent_id, ts = result
                touched.add((org_id, agent_id, metrics_agg.event_day(ts)))
        except Exception as exc:
            db.rollback()
            # Re-fetch state lost by the rollback and record the failure.
            row = db.query(TelemetryEventRaw).filter(TelemetryEventRaw.id == row.id).first()
            if row is None:
                continue
            row.attempts = max(row.attempts or 0, 1)
            if row.attempts >= MAX_ATTEMPTS:
                row.status = "failed"
                row.error = str(exc)[:512]
                _log.warning("telemetry event %s permanently failed: %s", row.event_id, exc)
            else:
                row.status = "pending"
                row.error = str(exc)[:512]
        db.commit()

    if touched:
        metrics_agg.recompute_buckets(db, touched)
        db.commit()
    return len(rows)


def drain_all(db: Session, max_batches: int = 100) -> int:
    """Drain until the queue is empty (bounded). Used by inline mode/tests."""
    total = 0
    for _ in range(max_batches):
        n = drain_once(db)
        total += n
        if n == 0:
            break
    return total


def _loop() -> None:
    from app.database import SessionLocal

    while True:
        _wake.wait(timeout=POLL_INTERVAL_SECONDS)
        _wake.clear()
        try:
            db = SessionLocal()
            try:
                while drain_once(db) > 0:
                    pass
            finally:
                db.close()
        except Exception:
            # The worker thread must never die.
            _log.warning("telemetry worker cycle failed", exc_info=True)


def start_worker() -> None:
    """Start the daemon polling thread (idempotent). No-op when disabled or
    in inline mode."""
    global _worker_thread
    if not _worker_enabled():
        return
    with _thread_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(target=_loop, name="telemetry-worker", daemon=True)
        _worker_thread.start()
        _log.info("telemetry ingest worker started (poll every %.0fs)", POLL_INTERVAL_SECONDS)
