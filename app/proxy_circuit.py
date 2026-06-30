"""
Circuit breaker for the LLM enforcement gateway.

Extracted from app/routes/proxy.py — module-level state must remain
module-level (not a class) so all importers share the same dict object.
"""
import os
import time

_LLM_TIMEOUT     = float(os.getenv("GATEWAY_LLM_TIMEOUT_SECS", "30"))
_ENFORCE_TIMEOUT = float(os.getenv("GATEWAY_ENFORCE_TIMEOUT_SECS", "5"))
_CB_THRESHOLD    = 5
_CB_WINDOW       = 60
_circuit = {"failures": 0, "tripped_at": None, "first_failure_at": None}


def _circuit_state() -> str:
    if _circuit["tripped_at"] is None:
        return "closed"
    if time.time() - _circuit["tripped_at"] > _CB_WINDOW:
        _circuit["tripped_at"] = None
        _circuit["failures"] = 0
        _circuit["first_failure_at"] = None
        return "closed"
    return "open"


def _circuit_record_failure():
    now = time.time()
    if _circuit["first_failure_at"] is None or now - _circuit["first_failure_at"] > _CB_WINDOW:
        _circuit["first_failure_at"] = now
        _circuit["failures"] = 0
    _circuit["failures"] += 1
    if _circuit["failures"] >= _CB_THRESHOLD:
        _circuit["tripped_at"] = now


def _circuit_record_success():
    if _circuit["tripped_at"] is None:
        _circuit["failures"] = 0
        _circuit["first_failure_at"] = None
