"""Central runtime configuration for ObserveAgents.

Two concerns live here:

1. Runtime mode (APP_ENV / DEMO_MODE) — the single source of truth deciding
   whether demo behavior (no-login, synthetic data, read-only) is active. Read
   lazily via functions so tests and per-process env changes are always reflected.
   Production is NEVER demo, even if DEMO_MODE=true is set by mistake.

2. Public URLs + CORS origins — canonical hostnames surfaced to the frontend and
   used for CORS allow-listing. The Render fallback URL is always allowed so
   existing traffic through ai-asset-app.onrender.com keeps working.

Modes:
  APP_ENV=production   → real customer environment.  Demo is NEVER enabled here.
  APP_ENV=demo         → public demo service (demo.observeagents.ai).  Demo on.
  APP_ENV=development  → local dev.  Demo off unless DEMO_MODE=true is explicit.
"""
from __future__ import annotations

import os

_VALID_ENVS = ("production", "demo", "development")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _clean(value: str, fallback: str) -> str:
    raw = (value or "").strip().rstrip("/")
    return raw or fallback


# ── Runtime mode (APP_ENV / DEMO_MODE) ────────────────────────────────────────

def app_env() -> str:
    """One of: production | demo | development.  Defaults to production."""
    val = _env("APP_ENV", "production").lower()
    return val if val in _VALID_ENVS else "production"


def is_production() -> bool:
    return app_env() == "production"


def is_development() -> bool:
    return app_env() == "development"


def is_demo_mode() -> bool:
    """Whether demo behavior (no-login, synthetic data, read-only) is active.

    Production can never be demo — this is the primary safety guarantee so that a
    stray DEMO_MODE=true on the production service can't unlock the demo behavior.
    Outside production, demo is on when DEMO_MODE=true OR APP_ENV=demo.
    """
    if is_production():
        return False
    if _env("DEMO_MODE", "false").lower() == "true":
        return True
    return app_env() == "demo"


# ── Public URLs ───────────────────────────────────────────────────────────────
# Primary production app lives at the apex domain (observeagents.ai), NOT app.*.
PUBLIC_APP_URL      = _clean(os.getenv("PUBLIC_APP_URL"),      "https://observeagents.ai")
PUBLIC_GATEWAY_URL  = _clean(os.getenv("PUBLIC_GATEWAY_URL"),  "https://gateway.observeagents.ai")
PUBLIC_DEMO_URL     = _clean(os.getenv("PUBLIC_DEMO_URL"),     "https://demo.observeagents.ai")
PUBLIC_API_URL      = _clean(os.getenv("PUBLIC_API_URL"),      "https://api.observeagents.ai")
PUBLIC_MARKETING_URL = _clean(os.getenv("PUBLIC_MARKETING_URL"), "https://observeagents.ai")
RENDER_FALLBACK_URL = _clean(os.getenv("RENDER_FALLBACK_URL"), "https://ai-asset-app.onrender.com")

# The canonical public origins that should always be allowed by CORS, in
# addition to any explicit FRONTEND_ORIGIN entries and local dev origins.
# app.observeagents.ai is kept allow-listed (its cert was issued) even though
# the apex domain is now canonical for customer-facing copy.
PUBLIC_ORIGINS = [
    PUBLIC_APP_URL,
    "https://observeagents.ai",
    "https://app.observeagents.ai",
    PUBLIC_GATEWAY_URL,
    PUBLIC_DEMO_URL,
    PUBLIC_API_URL,
    RENDER_FALLBACK_URL,
]

LOCAL_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def public_config() -> dict:
    """Public, unauthenticated config consumed by the frontend at boot (no secrets)."""
    return {
        "app_env": app_env(),
        "demo_mode": is_demo_mode(),
        "public_app_url": PUBLIC_APP_URL,
        "public_gateway_url": PUBLIC_GATEWAY_URL,
        "public_marketing_url": PUBLIC_MARKETING_URL,
    }
