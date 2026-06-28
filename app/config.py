"""Central environment/runtime-mode helper.

Single source of truth for APP_ENV / DEMO_MODE and the public URLs surfaced to the
frontend.  Everything is read lazily (functions, not module constants) so tests and
per-process env changes are always reflected.

Modes:
  APP_ENV=production   → real customer environment.  Demo is NEVER enabled here,
                         even if DEMO_MODE=true is set by mistake.
  APP_ENV=demo         → public demo service (demo.observeagents.ai).  Demo on.
  APP_ENV=development  → local dev.  Demo off unless DEMO_MODE=true is explicit.
"""
import os

_VALID_ENVS = ("production", "demo", "development")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


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


def public_config() -> dict:
    """Public, unauthenticated config consumed by the frontend at boot."""
    return {
        "app_env": app_env(),
        "demo_mode": is_demo_mode(),
        "public_app_url": _env("PUBLIC_APP_URL"),
        "public_gateway_url": _env("PUBLIC_GATEWAY_URL"),
        "public_marketing_url": _env("PUBLIC_MARKETING_URL"),
    }
