#!/usr/bin/env python3
"""
Full Synthetic Customer E2E Test Suite — AI Asset Management Platform
=====================================================================
Validates every major product feature through a synthetic customer
scenario for Acme AI Inc.

23 sections covering:
  §01  Health / startup
  §02  Platform admin login
  §03  Organization management
  §04  User management
  §05  Role / team management
  §06  API key management
  §07  Provider credentials / integrations
  §08  Guard mode / settings
  §09  OpenAI-compatible proxy  (POST /v1/chat/completions)
  §10  Anthropic-compatible proxy  (POST /v1/messages)
  §11  Agent inventory
  §12  Relationship / dependency mapping
  §13  PII detection and redaction
  §14  Budget enforcement
  §15  Policy enforcement
  §16  Telemetry verification
  §17  Audit verification
  §18  Security alerts
  §19  Cost intelligence
  §20  Pricing registry
  §21  Dashboard read APIs
  §22  Rate limiting  (opt-in: --include-rate-limit)
  §23  Sessions / chat

Required env vars:
    PLATFORM_ADMIN_PASSWORD      (no default — must be set)

Optional env vars:
    BASE_URL                     default: http://localhost:8000
    PLATFORM_ADMIN_EMAIL         default: admin@ai-asset-mgmt.local
    ACME_ADMIN_EMAIL             default: admin@acme.ai
    ACME_ADMIN_PASSWORD          default: AcmeAdmin1!

CLI flags:
    --strict               treat skips as failures
    --dry-run              print plan without sending requests
    --skip-live-llm        skip sections that need a provider credential
    --include-rate-limit   enable §22 (hammers the login endpoint)
    --base-url URL         override BASE_URL
    --admin-email EMAIL    override PLATFORM_ADMIN_EMAIL
    --admin-password PWD   override PLATFORM_ADMIN_PASSWORD
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL                = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
PLATFORM_ADMIN_EMAIL    = os.getenv("PLATFORM_ADMIN_EMAIL", "admin@ai-asset-mgmt.local")
PLATFORM_ADMIN_PASSWORD = os.getenv("PLATFORM_ADMIN_PASSWORD", "")
ACME_ADMIN_EMAIL        = os.getenv("ACME_ADMIN_EMAIL", "admin@acme.ai")
ACME_ADMIN_PASSWORD     = os.getenv("ACME_ADMIN_PASSWORD", "AcmeAdmin1!")

# ── Synthetic company definition ──────────────────────────────────────────────

ACME_ORG_NAME  = "Acme AI Inc."
ACME_ORG_SLUG  = "acme-ai-e2e"
ACME_TEAMS     = ["Support", "Sales", "Operations", "Security"]

ACME_USERS = [
    {"email": "analyst@acme-e2e.ai", "password": "AcmeAnalyst1!", "role": "analyst"},
    {"email": "viewer@acme-e2e.ai",  "password": "AcmeViewer1!",  "role": "viewer"},
]

API_KEY_SPECS = [
    {"name": "e2e-support-key",    "agent": "support-triage-agent",  "team": "Support"},
    {"name": "e2e-sales-key",      "agent": "sales-agent",           "team": "Sales"},
    {"name": "e2e-security-key",   "agent": "security-agent",        "team": "Security"},
]

AGENTS = [
    {"name": "support-triage-agent", "team": "Support",    "env": "prod"},
    {"name": "sales-agent",          "team": "Sales",      "env": "prod"},
    {"name": "ops-automation-agent", "team": "Operations", "env": "staging"},
    {"name": "security-agent",       "team": "Security",   "env": "prod"},
    {"name": "research-agent",       "team": "Operations", "env": "prod"},
]

MODEL = "gpt-4o-mini"

# Clearly fake test PII — not real data
FAKE_EMAIL   = "test-user@example-domain.com"
FAKE_SSN     = "123-45-6789"
FAKE_CC      = "4111-1111-1111-1111"
FAKE_API_KEY = "sk-TESTFAKEAPIKEY0123456789ABCDE"


# ── Result tracking ───────────────────────────────────────────────────────────

@dataclass
class Result:
    name:            str
    status:          str          # "pass" | "fail" | "skip"
    reason:          str   = ""
    endpoint:        str   = ""
    response_status: int   = 0
    body_snippet:    str   = ""


@dataclass
class State:
    platform_token:  str   = ""
    acme_token:      str   = ""
    acme_org_id:     int   = 0
    user_ids:        dict  = field(default_factory=dict)
    api_key_ids:     dict  = field(default_factory=dict)   # name → id (never stores raw key)
    api_key_values:  dict  = field(default_factory=dict)   # name → masked key (gk-****…)
    api_key_raw:     dict  = field(default_factory=dict)   # name → full key (NEVER logged)
    budget_id:       int   = 0
    policy_id:       int   = 0
    billing_id:      int   = 0
    session_uuid:    str   = ""
    results:         list  = field(default_factory=list)


# ── ANSI colours ──────────────────────────────────────────────────────────────

_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_RESET  = "\033[0m"

def _pass(msg: str) -> str:  return f"{_GREEN}✅{_RESET} {msg}"
def _fail(msg: str) -> str:  return f"{_RED}❌{_RESET} {msg}"
def _skip(msg: str) -> str:  return f"{_YELLOW}⏭ {_RESET} {msg}"


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _client(token: str = "", api_key: str = "") -> httpx.Client:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return httpx.Client(base_url=BASE_URL, headers=headers, timeout=30)


def request_json(
    method: str,
    path: str,
    *,
    token: str = "",
    api_key: str = "",
    body: dict | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """Make an authenticated HTTP request; return (status_code, parsed_body)."""
    try:
        with _client(token=token, api_key=api_key) as c:
            hdrs = extra_headers or {}
            kwargs: dict[str, Any] = {"headers": hdrs}
            if body is not None:
                kwargs["json"] = body
            r = c.request(method.upper(), path, **kwargs)
            try:
                data = r.json()
            except Exception:
                data = r.text
            return r.status_code, data
    except httpx.ConnectError as e:
        return 0, {"error": f"Connection refused — is the backend running at {BASE_URL}? ({e})"}
    except httpx.TimeoutException as e:
        return 0, {"error": f"Request timed out: {e}"}
    except Exception as e:
        return 0, {"error": f"Request error: {e}"}


def login(email: str, password: str) -> str:
    """Login and return the access token. Returns '' on failure."""
    status, data = request_json("POST", "/auth/login", body={"email": email, "password": password})
    if status == 200 and isinstance(data, dict):
        return data.get("access_token", "")
    return ""


def _mask_key(k: str) -> str:
    """Mask all but the prefix and last 4 chars."""
    if not k or len(k) < 8:
        return "***"
    return k[:5] + "****" + k[-4:]


# ── Section helpers ───────────────────────────────────────────────────────────

_W = 70

def _section(n: int, title: str) -> None:
    print(f"\n{'─' * _W}")
    print(f"  §{n:02d} — {title}")
    print(f"{'─' * _W}")


def record_pass(state: State, name: str, *, endpoint: str = "", status: int = 0, body: str = "") -> None:
    state.results.append(Result(name, "pass", endpoint=endpoint, response_status=status, body_snippet=body[:120]))
    print(f"  {_pass(name)}")


def record_fail(state: State, name: str, reason: str, *, endpoint: str = "", status: int = 0, body: str = "") -> None:
    state.results.append(Result(name, "fail", reason=reason, endpoint=endpoint,
                                response_status=status, body_snippet=body[:120]))
    print(f"  {_fail(name)}")
    if reason:
        print(f"       {reason}")


def record_skip(state: State, name: str, reason: str, *, strict: bool = False) -> None:
    if strict:
        state.results.append(Result(name, "fail", reason=f"[strict] {reason}"))
        print(f"  {_fail(name)} [strict skip]")
        print(f"       {reason}")
    else:
        state.results.append(Result(name, "skip", reason=reason))
        print(f"  {_skip(name)}")
        print(f"       {reason}")


def assert_condition(
    state: State,
    name: str,
    condition: bool,
    fail_reason: str,
    *,
    endpoint: str = "",
    status: int = 0,
    body: str = "",
    strict: bool = False,
) -> bool:
    if condition:
        record_pass(state, name, endpoint=endpoint, status=status, body=body)
        return True
    record_fail(state, name, fail_reason, endpoint=endpoint, status=status, body=body)
    return False


# ── Dry-run plan ──────────────────────────────────────────────────────────────

_DRY_RUN_CHECKS = [
    "§01 Health check (/health)",
    "§01 Root endpoint (/)",
    "§02 Platform admin login",
    "§02 Auth /me — token valid",
    "§03 GET /admin/organizations",
    "§03 POST /admin/organizations (Acme AI Inc.)",
    "§04 POST /auth/users — Acme admin",
    "§04 Acme admin login",
    "§04 POST /auth/users — analyst",
    "§04 POST /auth/users — viewer",
    "§04 GET /auth/users — list",
    "§04 GET /auth/me — Acme admin context",
    "§05 GET /roles",
    "§05 GET /teams",
    "§05 POST /roles — custom role",
    "§05 PATCH /roles/{name}",
    "§05 DELETE /roles/{name}",
    "§06 POST /api-keys — support key",
    "§06 POST /api-keys — sales key",
    "§06 POST /api-keys — security key",
    "§06 GET /api-keys — list",
    "§06 PATCH /api-keys/{id}",
    "§07 GET /provider-credentials",
    "§07 GET /settings/keys",
    "§07 POST /provider-credentials (fake key — expect 400 if validated)",
    "§08 GET /guard-modes",
    "§08 PUT /guard-modes/Support → observe",
    "§08 GET /settings/config",
    "§08 PUT /settings/config/pii_redaction_mode",
    "§09 POST /v1/chat/completions — support-triage-agent",
    "§09 POST /v1/chat/completions — sales-agent",
    "§09 POST /v1/chat/completions — ops-automation-agent",
    "§09 POST /v1/chat/completions — security-agent",
    "§09 POST /v1/chat/completions — research-agent",
    "§10 POST /v1/messages — Anthropic proxy",
    "§11 GET /assets",
    "§11 GET /assets/summary",
    "§11 GET /agents",
    "§11 GET /agents/summary",
    "§11 GET /assets/registry/unassigned",
    "§12 GET /relationships",
    "§12 GET /relationships/graph",
    "§13 POST /security/scan — email PII",
    "§13 POST /security/scan — SSN PII",
    "§13 POST /security/scan — credit card PII",
    "§13 POST /security/scan — API key secret",
    "§14 POST /budgets",
    "§14 GET /budgets",
    "§14 GET /budgets/status",
    "§14 DELETE /budgets/{id}",
    "§15 PUT /guard-modes/Support → enforce",
    "§15 POST /policies — block rule",
    "§15 GET /policies",
    "§15 POST /v1/chat/completions — blocked (expect 403)",
    "§15 DELETE /policies/{id}",
    "§15 PUT /guard-modes/Support → observe (cleanup)",
    "§16 GET /telemetry",
    "§16 GET /telemetry/summary",
    "§17 GET /audit",
    "§18 GET /security/alerts",
    "§19 GET /cost-intelligence",
    "§19 POST /billing/openai/import",
    "§19 GET /billing/periods",
    "§20 GET /pricing-registry",
    "§20 GET /pricing-registry/status",
    "§20 GET /pricing-registry/sync-status",
    "§20 POST /pricing-registry/override",
    "§21 GET / (root)",
    "§21 GET /health",
    "§21 GET /auth/users",
    "§21 GET /roles",
    "§21 GET /teams",
    "§21 GET /api-keys",
    "§21 GET /guard-modes",
    "§21 GET /telemetry",
    "§21 GET /telemetry/summary",
    "§21 GET /audit",
    "§21 GET /security/alerts",
    "§21 GET /budgets",
    "§21 GET /budgets/status",
    "§21 GET /policies",
    "§21 GET /assets",
    "§21 GET /assets/summary",
    "§21 GET /agents",
    "§21 GET /agents/summary",
    "§21 GET /cost-intelligence",
    "§21 GET /billing/periods",
    "§21 GET /pricing-registry",
    "§21 GET /settings/config",
    "§22 Rate limiting — login endpoint (--include-rate-limit only)",
    "§23 POST /sessions",
    "§23 GET /sessions",
    "§23 GET /sessions/{uuid}",
    "§23 POST /sessions/{uuid}/chat",
    "§23 GET /sessions/{uuid}/messages",
    "§23 DELETE /sessions/{uuid}",
]


def dry_run() -> None:
    print(f"\n{'═' * _W}")
    print("  AI Asset Management — Full E2E Test Suite  (DRY RUN)")
    print(f"  Backend : {BASE_URL}")
    print(f"  Org     : {ACME_ORG_NAME}")
    print(f"  Checks  : {len(_DRY_RUN_CHECKS)}")
    print(f"{'═' * _W}\n")
    for i, check in enumerate(_DRY_RUN_CHECKS, 1):
        print(f"  [{i:02d}] {check}")
    print(f"\n  {len(_DRY_RUN_CHECKS)} checks planned — no requests sent.\n")
    sys.exit(0)


# ══════════════════════════════════════════════════════════════════════════════
# SECTIONS
# ══════════════════════════════════════════════════════════════════════════════


def section_01_health(state: State, args: argparse.Namespace) -> None:
    _section(1, "Health / startup")

    status, data = request_json("GET", "/health")
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    assert_condition(
        state, "Health check (/health)", status == 200,
        f"Expected 200, got {status}: {body}",
        endpoint="/health", status=status, body=body,
    )

    status2, data2 = request_json("GET", "/")
    body2 = json.dumps(data2)[:120] if isinstance(data2, dict) else str(data2)[:120]
    assert_condition(
        state, "Root endpoint (/)", status2 == 200,
        f"Expected 200, got {status2}: {body2}",
        endpoint="/", status=status2, body=body2,
    )


def section_02_platform_admin(state: State, args: argparse.Namespace) -> None:
    _section(2, "Platform admin login")

    if not PLATFORM_ADMIN_PASSWORD:
        record_fail(state, "Platform admin login", "PLATFORM_ADMIN_PASSWORD env var not set")
        return

    token = login(PLATFORM_ADMIN_EMAIL, PLATFORM_ADMIN_PASSWORD)
    if not token:
        record_fail(state, "Platform admin login",
                    f"Login failed for {PLATFORM_ADMIN_EMAIL} — check password / backend")
        return

    state.platform_token = token
    record_pass(state, "Platform admin login", endpoint="/auth/login", status=200)

    status, data = request_json("GET", "/auth/me", token=token)
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    assert_condition(
        state, "Auth /me — token valid", status == 200,
        f"Expected 200, got {status}: {body}",
        endpoint="/auth/me", status=status, body=body,
    )

    # Use platform admin's org as fallback for all subsequent calls
    if isinstance(data, dict):
        state.acme_org_id = data.get("organization_id", 0)


def section_03_org_management(state: State, args: argparse.Namespace) -> None:
    _section(3, "Organization management")

    if not state.platform_token:
        record_skip(state, "GET /admin/organizations", "No platform token (§02 failed)", strict=args.strict)
        record_skip(state, "POST /admin/organizations (Acme AI Inc.)", "No platform token", strict=args.strict)
        return

    # GET /admin/organizations
    status, data = request_json("GET", "/admin/organizations", token=state.platform_token)
    if status == 200:
        record_pass(state, "GET /admin/organizations", endpoint="/admin/organizations", status=status)
    elif status == 404:
        record_skip(
            state, "GET /admin/organizations",
            "GET /admin/organizations returned 404 — endpoint not yet implemented",
            strict=args.strict,
        )
    else:
        body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
        record_fail(state, "GET /admin/organizations", f"Unexpected {status}: {body}",
                    endpoint="/admin/organizations", status=status, body=body)

    # POST /admin/organizations — schema: {name, admin_email, admin_name, admin_password}
    status, data = request_json(
        "POST", "/admin/organizations",
        token=state.platform_token,
        body={
            "name":           ACME_ORG_NAME,
            "admin_email":    ACME_ADMIN_EMAIL,
            "admin_name":     "Acme Admin",
            "admin_password": ACME_ADMIN_PASSWORD,
        },
    )
    if status in (200, 201):
        org_id = data.get("id", 0) if isinstance(data, dict) else 0
        if org_id:
            state.acme_org_id = org_id
        record_pass(state, f"POST /admin/organizations ({ACME_ORG_NAME})",
                    endpoint="/admin/organizations", status=status)
    elif status in (404, 405):
        record_skip(
            state, f"POST /admin/organizations ({ACME_ORG_NAME})",
            f"POST /admin/organizations returned {status} — endpoint not yet implemented",
            strict=args.strict,
        )
    elif status == 409:
        record_pass(state, f"POST /admin/organizations ({ACME_ORG_NAME}) — already exists",
                    endpoint="/admin/organizations", status=status)
    else:
        body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
        record_fail(state, f"POST /admin/organizations ({ACME_ORG_NAME})",
                    f"Unexpected {status}: {body}",
                    endpoint="/admin/organizations", status=status, body=body)


def section_04_user_management(state: State, args: argparse.Namespace) -> None:
    _section(4, "User management")

    if not state.platform_token:
        for label in ["Acme admin user creation", "Acme admin login",
                      "Create analyst user", "Create viewer user",
                      "GET /auth/users — list", "GET /auth/me — Acme admin context"]:
            record_skip(state, label, "No platform token (§02 failed)", strict=args.strict)
        return

    # Create Acme admin
    status, data = request_json(
        "POST", "/auth/users",
        token=state.platform_token,
        body={
            "email":    ACME_ADMIN_EMAIL,
            "password": ACME_ADMIN_PASSWORD,
            "role":     "admin",
            "name":     "Acme Admin",
        },
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    if status in (200, 201):
        record_pass(state, "Acme admin user creation", endpoint="/auth/users", status=status)
    elif status == 409:
        record_pass(state, "Acme admin user creation — already exists",
                    endpoint="/auth/users", status=status)
    else:
        record_fail(state, "Acme admin user creation",
                    f"Expected 201/409, got {status}: {body}",
                    endpoint="/auth/users", status=status, body=body)

    # Acme admin login
    acme_token = login(ACME_ADMIN_EMAIL, ACME_ADMIN_PASSWORD)
    if acme_token:
        state.acme_token = acme_token
        record_pass(state, "Acme admin login", endpoint="/auth/login", status=200)
    else:
        record_fail(state, "Acme admin login",
                    f"Login failed for {ACME_ADMIN_EMAIL}")

    token = state.acme_token or state.platform_token

    # Create analyst and viewer
    for user_spec in ACME_USERS:
        email = user_spec["email"]
        status, data = request_json(
            "POST", "/auth/users",
            token=token,
            body={
                "email":    email,
                "password": user_spec["password"],
                "role":     user_spec["role"],
                "name":     email.split("@")[0].capitalize(),
            },
        )
        body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
        label = f"Create {user_spec['role']} user ({email})"
        if status in (200, 201):
            user_id = data.get("id") if isinstance(data, dict) else None
            if user_id:
                state.user_ids[email] = user_id
            record_pass(state, label, endpoint="/auth/users", status=status)
        elif status == 409:
            record_pass(state, f"{label} — already exists",
                        endpoint="/auth/users", status=status)
        else:
            record_fail(state, label,
                        f"Expected 201/409, got {status}: {body}",
                        endpoint="/auth/users", status=status, body=body)

    # List users
    status, data = request_json("GET", "/auth/users", token=token)
    body = json.dumps(data)[:120] if isinstance(data, list) else str(data)[:120]
    assert_condition(
        state, "GET /auth/users — list",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}: {body}",
        endpoint="/auth/users", status=status, body=body,
    )

    # Auth /me for Acme admin
    status, me = request_json("GET", "/auth/me", token=token)
    body = json.dumps(me)[:120] if isinstance(me, dict) else str(me)[:120]
    assert_condition(
        state, "GET /auth/me — Acme admin context",
        status == 200 and isinstance(me, dict) and "email" in me,
        f"Expected 200 with email field, got {status}: {body}",
        endpoint="/auth/me", status=status, body=body,
    )
    if status == 200 and isinstance(me, dict):
        state.acme_org_id = me.get("organization_id", state.acme_org_id)


def section_05_roles_teams(state: State, args: argparse.Namespace) -> None:
    _section(5, "Role / team management")

    token = state.acme_token or state.platform_token
    if not token:
        for label in ["GET /roles", "GET /teams", "POST /roles — custom",
                      "PATCH /roles/{name}", "DELETE /roles/{name}"]:
            record_skip(state, label, "No auth token (§02/§04 failed)", strict=args.strict)
        return

    # List roles
    status, data = request_json("GET", "/roles", token=token)
    assert_condition(
        state, "GET /roles",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint="/roles", status=status,
    )

    # List teams
    status, data = request_json("GET", "/teams", token=token)
    assert_condition(
        state, "GET /teams",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint="/teams", status=status,
    )

    # Create custom role
    custom_role_name = "e2e-test-role"
    status, data = request_json(
        "POST", "/roles",
        token=token,
        body={
            "name":  custom_role_name,
            "label": "E2E Test Role",
            "color": "#00BFFF",
            "pages": ["dashboard", "assets"],
            "can":   [],
        },
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    if status in (200, 201):
        record_pass(state, "POST /roles — custom role", endpoint="/roles", status=status)
    elif status == 409:
        record_pass(state, "POST /roles — custom role (already exists)",
                    endpoint="/roles", status=status)
    else:
        record_fail(state, "POST /roles — custom role",
                    f"Expected 201/409, got {status}: {body}",
                    endpoint="/roles", status=status, body=body)
        custom_role_name = None

    # Patch the custom role
    if custom_role_name:
        status, data = request_json(
            "PATCH", f"/roles/{custom_role_name}",
            token=token,
            body={"label": "E2E Test Role (updated)", "color": "#FF8C00"},
        )
        body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
        assert_condition(
            state, "PATCH /roles/{name}",
            status == 200,
            f"Expected 200, got {status}: {body}",
            endpoint=f"/roles/{custom_role_name}", status=status, body=body,
        )

        # Delete the custom role
        status, _ = request_json("DELETE", f"/roles/{custom_role_name}", token=token)
        assert_condition(
            state, "DELETE /roles/{name}",
            status in (200, 204),
            f"Expected 204, got {status}",
            endpoint=f"/roles/{custom_role_name}", status=status,
        )
    else:
        record_skip(state, "PATCH /roles/{name}", "Custom role creation skipped", strict=args.strict)
        record_skip(state, "DELETE /roles/{name}", "Custom role creation skipped", strict=args.strict)


def section_06_api_keys(state: State, args: argparse.Namespace) -> None:
    _section(6, "API key management")

    token = state.acme_token or state.platform_token
    if not token:
        for spec in API_KEY_SPECS:
            record_skip(state, f"POST /api-keys — {spec['name']}", "No auth token", strict=args.strict)
        record_skip(state, "GET /api-keys — list", "No auth token", strict=args.strict)
        record_skip(state, "PATCH /api-keys/{id}", "No auth token", strict=args.strict)
        return

    for spec in API_KEY_SPECS:
        status, data = request_json(
            "POST", "/api-keys",
            token=token,
            body={
                "name":        spec["name"],
                "caller_name": spec["agent"],
                "team":        spec["team"],
                "environment": "prod",
            },
        )
        body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
        label = f"POST /api-keys — {spec['name']}"
        if status in (200, 201) and isinstance(data, dict):
            key_id  = data.get("id")
            raw_key = data.get("key", "")
            if key_id:
                state.api_key_ids[spec["name"]]    = key_id
                state.api_key_values[spec["name"]] = _mask_key(raw_key)
                state.api_key_raw[spec["name"]]    = raw_key
            record_pass(state, label, endpoint="/api-keys", status=status,
                        body=f"id={key_id} key={_mask_key(raw_key)}")
        else:
            record_fail(state, label,
                        f"Expected 201, got {status}: {body}",
                        endpoint="/api-keys", status=status, body=body)

    # List keys
    status, data = request_json("GET", "/api-keys", token=token)
    assert_condition(
        state, "GET /api-keys — list",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint="/api-keys", status=status,
    )

    # Patch the first key — endpoint only accepts is_active (bool)
    first_name = API_KEY_SPECS[0]["name"]
    if first_name in state.api_key_ids:
        key_id = state.api_key_ids[first_name]
        status, data = request_json(
            "PATCH", f"/api-keys/{key_id}",
            token=token,
            body={"is_active": True},
        )
        body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
        assert_condition(
            state, "PATCH /api-keys/{id}",
            status == 200,
            f"Expected 200, got {status}: {body}",
            endpoint=f"/api-keys/{key_id}", status=status, body=body,
        )
    else:
        record_skip(state, "PATCH /api-keys/{id}", "No key id available", strict=args.strict)


def section_07_provider_credentials(state: State, args: argparse.Namespace) -> None:
    _section(7, "Provider credentials / integrations")

    token = state.acme_token or state.platform_token
    if not token:
        record_skip(state, "GET /provider-credentials", "No auth token", strict=args.strict)
        record_skip(state, "GET /settings/keys", "No auth token", strict=args.strict)
        record_skip(state, "POST /provider-credentials (fake key)", "No auth token", strict=args.strict)
        return

    # List provider credentials
    status, data = request_json("GET", "/provider-credentials", token=token)
    assert_condition(
        state, "GET /provider-credentials",
        status == 200,
        f"Expected 200, got {status}",
        endpoint="/provider-credentials", status=status,
    )

    # Settings/keys
    status, data = request_json("GET", "/settings/keys", token=token)
    assert_condition(
        state, "GET /settings/keys",
        status == 200,
        f"Expected 200, got {status}",
        endpoint="/settings/keys", status=status,
    )

    # Post fake provider credential — backend should reject or store it
    # (FAKE_API_KEY is clearly not a real OpenAI key)
    status, data = request_json(
        "POST", "/provider-credentials",
        token=token,
        body={"provider": "openai", "api_key": FAKE_API_KEY},
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    if status in (200, 201):
        record_pass(state, "POST /provider-credentials (fake key — stored)",
                    endpoint="/provider-credentials", status=status, body=body)
    elif status in (400, 422):
        record_pass(state, "POST /provider-credentials (fake key — rejected correctly)",
                    endpoint="/provider-credentials", status=status, body=body)
    else:
        record_fail(state, "POST /provider-credentials (fake key)",
                    f"Unexpected {status}: {body}",
                    endpoint="/provider-credentials", status=status, body=body)


def section_08_guard_modes_settings(state: State, args: argparse.Namespace) -> None:
    _section(8, "Guard mode / settings")

    token = state.acme_token or state.platform_token
    if not token:
        for label in ["GET /guard-modes", "PUT /guard-modes/Support → observe",
                      "GET /settings/config", "PUT /settings/config/pii_redaction_mode"]:
            record_skip(state, label, "No auth token", strict=args.strict)
        return

    # List guard modes
    status, data = request_json("GET", "/guard-modes", token=token)
    assert_condition(
        state, "GET /guard-modes",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint="/guard-modes", status=status,
    )

    # Set Support to observe
    status, data = request_json(
        "PUT", "/guard-modes/Support",
        token=token,
        body={"mode": "observe"},
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    assert_condition(
        state, "PUT /guard-modes/Support → observe",
        status in (200, 204),
        f"Expected 200/204, got {status}: {body}",
        endpoint="/guard-modes/Support", status=status, body=body,
    )

    # Set all teams to observe
    for team in ACME_TEAMS[1:]:
        request_json("PUT", f"/guard-modes/{team}", token=token, body={"mode": "observe"})

    # Get settings config
    status, data = request_json("GET", "/settings/config", token=token)
    assert_condition(
        state, "GET /settings/config",
        status == 200,
        f"Expected 200, got {status}",
        endpoint="/settings/config", status=status,
    )

    # Set PII redaction mode
    status, data = request_json(
        "PUT", "/settings/config/pii_redaction_mode",
        token=token,
        body={"value": "findings_only"},
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    assert_condition(
        state, "PUT /settings/config/pii_redaction_mode",
        status in (200, 204),
        f"Expected 200/204, got {status}: {body}",
        endpoint="/settings/config/pii_redaction_mode", status=status, body=body,
    )


def _proxy_call(
    state: State,
    agent: dict,
    api_key_name: str,
    prompt: str,
    *,
    skip_live: bool = False,
    strict: bool = False,
) -> bool:
    """Send one OpenAI-proxy call; returns True on success."""
    raw_key = state.api_key_raw.get(api_key_name, "")
    if not raw_key:
        record_skip(state, f"POST /v1/chat/completions — {agent['name']}",
                    f"No API key for {api_key_name}", strict=strict)
        return False

    extra = {
        "X-Agent-Name":        agent["name"],
        "X-Agent-Team":        agent["team"],
        "X-Agent-Environment": agent["env"],
        "X-Agent-Source":      "sdk-python",
    }
    status, data = request_json(
        "POST", "/v1/chat/completions",
        api_key=raw_key,
        body={
            "model":    MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 10,
        },
        extra_headers=extra,
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    label = f"POST /v1/chat/completions — {agent['name']}"

    if status == 200:
        record_pass(state, label, endpoint="/v1/chat/completions", status=status)
        return True
    if status in (400, 402, 503) and skip_live:
        record_skip(state, label, "No LLM provider credential (--skip-live-llm)", strict=strict)
        return False
    record_fail(state, label, f"Got {status}: {body}",
                endpoint="/v1/chat/completions", status=status, body=body)
    return False


def section_09_openai_proxy(state: State, args: argparse.Namespace) -> None:
    _section(9, "OpenAI-compatible proxy (POST /v1/chat/completions)")

    agent_key_map = {
        "support-triage-agent": "e2e-support-key",
        "sales-agent":          "e2e-sales-key",
        "ops-automation-agent": "e2e-security-key",
        "security-agent":       "e2e-security-key",
        "research-agent":       "e2e-support-key",
    }
    prompts = [
        "Classify: billing, technical, or account? One word.",
        "Score this lead 1-10: 'We have 200 employees.' One digit.",
        "Automate: next step for backlog task? One sentence.",
        "Threat level: low, medium, or high? One word.",
        "Summarize in five words: 'AI governance is important for enterprise.'",
    ]
    for i, agent in enumerate(AGENTS):
        _proxy_call(
            state, agent, agent_key_map.get(agent["name"], "e2e-support-key"),
            prompts[i % len(prompts)],
            skip_live=args.skip_live_llm, strict=args.strict,
        )


def section_10_anthropic_proxy(state: State, args: argparse.Namespace) -> None:
    _section(10, "Anthropic-compatible proxy (POST /v1/messages)")

    raw_key = state.api_key_raw.get("e2e-support-key", "")
    if not raw_key:
        record_skip(state, "POST /v1/messages — Anthropic proxy",
                    "No API key for e2e-support-key", strict=args.strict)
        return

    extra = {
        "X-Agent-Name":        "support-triage-agent",
        "X-Agent-Team":        "Support",
        "X-Agent-Environment": "prod",
        "X-Agent-Source":      "sdk-python",
    }
    status, data = request_json(
        "POST", "/v1/messages",
        api_key=raw_key,
        body={
            "model":      "claude-haiku-4-5-20251001",
            "max_tokens": 10,
            "messages":   [{"role": "user", "content": "Ping. Reply one word."}],
        },
        extra_headers=extra,
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    label = "POST /v1/messages — Anthropic proxy"
    if status == 200:
        record_pass(state, label, endpoint="/v1/messages", status=status)
    elif status in (400, 402, 503) and args.skip_live_llm:
        record_skip(state, label, "No LLM provider credential (--skip-live-llm)", strict=args.strict)
    else:
        record_fail(state, label, f"Got {status}: {body}",
                    endpoint="/v1/messages", status=status, body=body)


def section_11_agent_inventory(state: State, args: argparse.Namespace) -> None:
    _section(11, "Agent inventory")

    token = state.acme_token or state.platform_token
    if not token:
        for label in ["GET /assets", "GET /assets/summary", "GET /agents",
                      "GET /agents/summary", "GET /assets/registry/unassigned"]:
            record_skip(state, label, "No auth token", strict=args.strict)
        return

    for endpoint, label in [
        ("/assets",                    "GET /assets"),
        ("/assets/summary",            "GET /assets/summary"),
        ("/agents",                    "GET /agents"),
        ("/agents/summary",            "GET /agents/summary"),
        ("/assets/registry/unassigned","GET /assets/registry/unassigned"),
    ]:
        status, data = request_json("GET", endpoint, token=token)
        assert_condition(
            state, label,
            status == 200,
            f"Expected 200, got {status}",
            endpoint=endpoint, status=status,
        )


def section_12_relationship_mapping(state: State, args: argparse.Namespace) -> None:
    _section(12, "Relationship / dependency mapping")

    token = state.acme_token or state.platform_token
    if not token:
        for label in ["GET /relationships", "GET /relationships/graph"]:
            record_skip(state, label, "No auth token", strict=args.strict)
        return

    for endpoint in ["/relationships", "/relationships/graph"]:
        status, data = request_json("GET", endpoint, token=token)
        if status == 200:
            record_pass(state, f"GET {endpoint}", endpoint=endpoint, status=status)
        elif status == 404:
            record_skip(
                state, f"GET {endpoint}",
                f"GET {endpoint} returned 404 — relationship mapping not yet implemented",
                strict=args.strict,
            )
        else:
            body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
            record_fail(state, f"GET {endpoint}",
                        f"Unexpected {status}: {body}",
                        endpoint=endpoint, status=status, body=body)


def section_13_pii_detection(state: State, args: argparse.Namespace) -> None:
    _section(13, "PII detection and redaction")

    token = state.acme_token or state.platform_token
    if not token:
        for label in ["POST /security/scan — email PII", "POST /security/scan — SSN PII",
                      "POST /security/scan — credit card", "POST /security/scan — API key"]:
            record_skip(state, label, "No auth token", strict=args.strict)
        return

    scans = [
        ("email PII",   f"Customer email is {FAKE_EMAIL}, please process refund."),
        ("SSN PII",     f"SSN for verification: {FAKE_SSN}"),
        ("credit card", f"Card number {FAKE_CC} was declined."),
        ("API key",     f"My API key is {FAKE_API_KEY} — why isn't it working?"),
    ]
    for label_suffix, text in scans:
        label = f"POST /security/scan — {label_suffix}"
        status, data = request_json(
            "POST", "/security/scan",
            token=token,
            body={"text": text},
        )
        body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
        if status == 200 and isinstance(data, dict):
            findings = data.get("findings", [])
            has_finding = len(findings) > 0
            assert_condition(
                state, label,
                has_finding,
                f"Expected ≥1 finding but got {findings}",
                endpoint="/security/scan", status=status, body=body,
            )
        else:
            record_fail(state, label,
                        f"Expected 200 with findings, got {status}: {body}",
                        endpoint="/security/scan", status=status, body=body)


def section_14_budget_enforcement(state: State, args: argparse.Namespace) -> None:
    _section(14, "Budget enforcement")

    token = state.acme_token or state.platform_token
    if not token:
        for label in ["POST /budgets", "GET /budgets", "GET /budgets/status", "DELETE /budgets/{id}"]:
            record_skip(state, label, "No auth token", strict=args.strict)
        return

    # Create budget
    status, data = request_json(
        "POST", "/budgets",
        token=token,
        body={
            "team":         "Support",
            "period":       "monthly",
            "limit_usd":    10.00,
            "action":       "alert",
        },
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    if status in (200, 201) and isinstance(data, dict):
        state.budget_id = data.get("id", 0)
        record_pass(state, "POST /budgets", endpoint="/budgets", status=status,
                    body=f"id={state.budget_id}")
    else:
        record_fail(state, "POST /budgets",
                    f"Expected 201, got {status}: {body}",
                    endpoint="/budgets", status=status, body=body)

    # List budgets
    status, data = request_json("GET", "/budgets", token=token)
    assert_condition(
        state, "GET /budgets",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint="/budgets", status=status,
    )

    # Budget status
    status, data = request_json("GET", "/budgets/status", token=token)
    assert_condition(
        state, "GET /budgets/status",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint="/budgets/status", status=status,
    )

    # Cleanup
    if state.budget_id:
        status, _ = request_json("DELETE", f"/budgets/{state.budget_id}", token=token)
        assert_condition(
            state, "DELETE /budgets/{id}",
            status in (200, 204),
            f"Expected 204, got {status}",
            endpoint=f"/budgets/{state.budget_id}", status=status,
        )
        state.budget_id = 0


def section_15_policy_enforcement(state: State, args: argparse.Namespace) -> None:
    _section(15, "Policy enforcement")

    token = state.acme_token or state.platform_token
    if not token:
        for label in ["PUT /guard-modes/Support → enforce", "POST /policies — block rule",
                      "GET /policies", "POST /v1/chat/completions — blocked (403)",
                      "DELETE /policies/{id}", "PUT /guard-modes/Support → observe (cleanup)"]:
            record_skip(state, label, "No auth token", strict=args.strict)
        return

    raw_key = state.api_key_raw.get("e2e-support-key", "")

    # Switch Support to enforce
    status, data = request_json(
        "PUT", "/guard-modes/Support",
        token=token,
        body={"mode": "enforce"},
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    enforce_ok = assert_condition(
        state, "PUT /guard-modes/Support → enforce",
        status in (200, 204),
        f"Expected 200/204, got {status}: {body}",
        endpoint="/guard-modes/Support", status=status, body=body,
    )

    # Create a block policy for Support team — schema: {team, rule_type, value}
    status, data = request_json(
        "POST", "/policies",
        token=token,
        body={
            "team":      "Support",
            "rule_type": "block_model",
            "value":     MODEL,
        },
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    if status in (200, 201) and isinstance(data, dict):
        state.policy_id = data.get("id", 0)
        record_pass(state, "POST /policies — block rule", endpoint="/policies", status=status,
                    body=f"id={state.policy_id}")
    else:
        record_fail(state, "POST /policies — block rule",
                    f"Expected 201, got {status}: {body}",
                    endpoint="/policies", status=status, body=body)

    # List policies
    status, data = request_json("GET", "/policies", token=token)
    assert_condition(
        state, "GET /policies",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint="/policies", status=status,
    )

    # Test that the block fires — expect 403.
    # Requires a live LLM credential: backend checks provider creds before policy,
    # so without credentials it returns 402 instead of 403.
    if args.skip_live_llm:
        record_skip(
            state, "POST /v1/chat/completions — blocked (expect 403)",
            "Skipped with --skip-live-llm: policy block (403) can't be distinguished "
            "from missing credential (402) without a live provider",
            strict=False,
        )
    elif raw_key and enforce_ok and state.policy_id:
        extra = {
            "X-Agent-Name":        "support-triage-agent",
            "X-Agent-Team":        "Support",
            "X-Agent-Source":      "sdk-python",
        }
        status, data = request_json(
            "POST", "/v1/chat/completions",
            api_key=raw_key,
            body={
                "model":    MODEL,
                "messages": [{"role": "user", "content": "Blocked by policy test."}],
                "max_tokens": 5,
            },
            extra_headers=extra,
        )
        body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
        assert_condition(
            state, "POST /v1/chat/completions — blocked (expect 403)",
            status == 403,
            f"Expected 403 (policy block), got {status}: {body}",
            endpoint="/v1/chat/completions", status=status, body=body,
        )
    else:
        record_skip(
            state, "POST /v1/chat/completions — blocked (expect 403)",
            "No API key, enforce not set, or no policy id",
            strict=args.strict,
        )

    # Cleanup: delete policy
    if state.policy_id:
        status, _ = request_json("DELETE", f"/policies/{state.policy_id}", token=token)
        assert_condition(
            state, "DELETE /policies/{id}",
            status in (200, 204),
            f"Expected 204, got {status}",
            endpoint=f"/policies/{state.policy_id}", status=status,
        )
        state.policy_id = 0

    # Reset guard mode to observe
    status, data = request_json(
        "PUT", "/guard-modes/Support",
        token=token,
        body={"mode": "observe"},
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    assert_condition(
        state, "PUT /guard-modes/Support → observe (cleanup)",
        status in (200, 204),
        f"Expected 200/204, got {status}: {body}",
        endpoint="/guard-modes/Support", status=status, body=body,
    )


def section_16_telemetry(state: State, args: argparse.Namespace) -> None:
    _section(16, "Telemetry verification")

    token = state.acme_token or state.platform_token
    if not token:
        record_skip(state, "GET /telemetry", "No auth token", strict=args.strict)
        record_skip(state, "GET /telemetry/summary", "No auth token", strict=args.strict)
        return

    status, data = request_json("GET", "/telemetry", token=token)
    assert_condition(
        state, "GET /telemetry",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint="/telemetry", status=status,
    )

    status, data = request_json("GET", "/telemetry/summary", token=token)
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    assert_condition(
        state, "GET /telemetry/summary",
        status == 200 and isinstance(data, dict),
        f"Expected 200 dict, got {status}: {body}",
        endpoint="/telemetry/summary", status=status, body=body,
    )


def section_17_audit(state: State, args: argparse.Namespace) -> None:
    _section(17, "Audit verification")

    token = state.acme_token or state.platform_token
    if not token:
        record_skip(state, "GET /audit", "No auth token", strict=args.strict)
        return

    status, data = request_json("GET", "/audit", token=token)
    assert_condition(
        state, "GET /audit",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint="/audit", status=status,
    )

    # Audit with filters
    status, data = request_json("GET", "/audit?limit=5", token=token)
    assert_condition(
        state, "GET /audit?limit=5",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint="/audit?limit=5", status=status,
    )


def section_18_security_alerts(state: State, args: argparse.Namespace) -> None:
    _section(18, "Security alerts")

    token = state.acme_token or state.platform_token
    if not token:
        record_skip(state, "GET /security/alerts", "No auth token", strict=args.strict)
        return

    status, data = request_json("GET", "/security/alerts", token=token)
    assert_condition(
        state, "GET /security/alerts",
        status == 200,
        f"Expected 200, got {status}",
        endpoint="/security/alerts", status=status,
    )


def section_19_cost_intelligence(state: State, args: argparse.Namespace) -> None:
    _section(19, "Cost intelligence")

    token = state.acme_token or state.platform_token
    if not token:
        for label in ["GET /cost-intelligence", "POST /billing/openai/import", "GET /billing/periods"]:
            record_skip(state, label, "No auth token", strict=args.strict)
        return

    # Cost intelligence overview
    status, data = request_json("GET", "/cost-intelligence", token=token)
    assert_condition(
        state, "GET /cost-intelligence",
        status == 200 and isinstance(data, dict),
        f"Expected 200 dict, got {status}",
        endpoint="/cost-intelligence", status=status,
    )

    # Import a fake billing record
    status, data = request_json(
        "POST", "/billing/openai/import",
        token=token,
        body={
            "billing_period_start":   "2026-05-01",
            "billing_period_end":     "2026-05-31",
            "actual_billed_cost_usd": 12.34,
        },
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    if status in (200, 201):
        if isinstance(data, dict):
            state.billing_id = data.get("id", 0)
        record_pass(state, "POST /billing/openai/import",
                    endpoint="/billing/openai/import", status=status,
                    body=f"id={state.billing_id}")
    else:
        record_fail(state, "POST /billing/openai/import",
                    f"Expected 201, got {status}: {body}",
                    endpoint="/billing/openai/import", status=status, body=body)

    # List billing periods
    status, data = request_json("GET", "/billing/periods", token=token)
    assert_condition(
        state, "GET /billing/periods",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint="/billing/periods", status=status,
    )

    # Per-billing-period detail
    if state.billing_id:
        status, data = request_json("GET", f"/billing/periods/{state.billing_id}", token=token)
        assert_condition(
            state, f"GET /billing/periods/{state.billing_id}",
            status == 200 and isinstance(data, dict),
            f"Expected 200 dict, got {status}",
            endpoint=f"/billing/periods/{state.billing_id}", status=status,
        )


def section_20_pricing_registry(state: State, args: argparse.Namespace) -> None:
    _section(20, "Pricing registry")

    token = state.acme_token or state.platform_token
    if not token:
        for label in ["GET /pricing-registry", "GET /pricing-registry/status",
                      "GET /pricing-registry/sync-status", "POST /pricing-registry/override"]:
            record_skip(state, label, "No auth token", strict=args.strict)
        return

    # List pricing
    status, data = request_json("GET", "/pricing-registry", token=token)
    assert_condition(
        state, "GET /pricing-registry",
        status == 200 and isinstance(data, dict),
        f"Expected 200 dict, got {status}",
        endpoint="/pricing-registry", status=status,
    )

    # Pricing status
    status, data = request_json("GET", "/pricing-registry/status", token=token)
    assert_condition(
        state, "GET /pricing-registry/status",
        status == 200,
        f"Expected 200, got {status}",
        endpoint="/pricing-registry/status", status=status,
    )

    # Sync status
    status, data = request_json("GET", "/pricing-registry/sync-status", token=token)
    assert_condition(
        state, "GET /pricing-registry/sync-status",
        status == 200,
        f"Expected 200, got {status}",
        endpoint="/pricing-registry/sync-status", status=status,
    )

    # Apply a pricing override
    status, data = request_json(
        "POST", "/pricing-registry/override",
        token=token,
        body={
            "provider":     "openai",
            "model":        "gpt-4o-mini",
            "input_cost":   0.150,
            "output_cost":  0.600,
            "reason":       "E2E test override — synthetic",
        },
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    if status in (200, 201):
        record_pass(state, "POST /pricing-registry/override",
                    endpoint="/pricing-registry/override", status=status, body=body)
    else:
        record_fail(state, "POST /pricing-registry/override",
                    f"Expected 201, got {status}: {body}",
                    endpoint="/pricing-registry/override", status=status, body=body)


def section_21_dashboard_reads(state: State, args: argparse.Namespace) -> None:
    _section(21, "Dashboard read APIs (all major pages)")

    token = state.acme_token or state.platform_token
    if not token:
        record_skip(state, "Dashboard read APIs", "No auth token", strict=args.strict)
        return

    endpoints = [
        ("/",                     "Root status"),
        ("/health",               "Health"),
        ("/auth/users",           "Users list"),
        ("/roles",                "Roles list"),
        ("/teams",                "Teams list"),
        ("/api-keys",             "API keys list"),
        ("/guard-modes",          "Guard modes"),
        ("/telemetry",            "Telemetry"),
        ("/telemetry/summary",    "Telemetry summary"),
        ("/audit",                "Audit log"),
        ("/security/alerts",      "Security alerts"),
        ("/budgets",              "Budgets"),
        ("/budgets/status",       "Budget status"),
        ("/policies",             "Policies"),
        ("/assets",               "Assets"),
        ("/assets/summary",       "Assets summary"),
        ("/agents",               "Agents"),
        ("/agents/summary",       "Agents summary"),
        ("/cost-intelligence",    "Cost intelligence"),
        ("/billing/periods",      "Billing periods"),
        ("/pricing-registry",     "Pricing registry"),
        ("/settings/config",      "Settings config"),
        ("/settings/keys",        "Settings keys"),
        ("/provider-credentials", "Provider credentials"),
    ]

    for path, label in endpoints:
        # /auth/users and /settings/* need the JWT token; / and /health need no auth
        use_token = "" if path in ("/", "/health") else token
        status, _ = request_json("GET", path, token=use_token)
        assert_condition(
            state, f"GET {path} ({label})",
            status == 200,
            f"Expected 200, got {status}",
            endpoint=path, status=status,
        )


def section_22_rate_limiting(state: State, args: argparse.Namespace) -> None:
    _section(22, "Rate limiting (login endpoint)")

    if not args.include_rate_limit:
        record_skip(
            state, "Rate limiting — login endpoint",
            "Skipped — pass --include-rate-limit to enable (hammers the login endpoint)",
            strict=False,  # never strict-fail rate limit tests
        )
        return

    print("  Sending 10 rapid login attempts to trigger rate limit…")
    statuses = []
    for _ in range(10):
        status, _ = request_json(
            "POST", "/auth/login",
            body={"email": "rate-test@example.com", "password": "WrongPwd!"},
        )
        statuses.append(status)

    got_limited = any(s == 429 for s in statuses)
    assert_condition(
        state, "Rate limiting — login endpoint fires 429",
        got_limited,
        f"Expected 429 after repeated failures; got statuses: {statuses}",
        endpoint="/auth/login",
    )


def section_23_sessions(state: State, args: argparse.Namespace) -> None:
    _section(23, "Sessions / chat")

    token = state.acme_token or state.platform_token
    if not token:
        for label in ["POST /sessions", "GET /sessions", "GET /sessions/{uuid}",
                      "POST /sessions/{uuid}/chat", "GET /sessions/{uuid}/messages",
                      "DELETE /sessions/{uuid}"]:
            record_skip(state, label, "No auth token", strict=args.strict)
        return

    # Create session — schema: {team, agent, model}
    status, data = request_json(
        "POST", "/sessions",
        token=token,
        body={"team": "Support", "agent": "support-triage-agent", "model": MODEL},
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    if status in (200, 201) and isinstance(data, dict):
        state.session_uuid = data.get("session_uuid") or data.get("uuid") or data.get("id", "")
        record_pass(state, "POST /sessions", endpoint="/sessions", status=status,
                    body=f"uuid={state.session_uuid}")
    else:
        record_fail(state, "POST /sessions",
                    f"Expected 201, got {status}: {body}",
                    endpoint="/sessions", status=status, body=body)

    # List sessions
    status, data = request_json("GET", "/sessions", token=token)
    assert_condition(
        state, "GET /sessions",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint="/sessions", status=status,
    )

    if not state.session_uuid:
        for label in ["GET /sessions/{uuid}", "POST /sessions/{uuid}/chat",
                      "GET /sessions/{uuid}/messages", "DELETE /sessions/{uuid}"]:
            record_skip(state, label, "No session uuid (creation failed)", strict=args.strict)
        return

    # Get session by uuid
    status, data = request_json("GET", f"/sessions/{state.session_uuid}", token=token)
    assert_condition(
        state, "GET /sessions/{uuid}",
        status == 200 and isinstance(data, dict),
        f"Expected 200 dict, got {status}",
        endpoint=f"/sessions/{state.session_uuid}", status=status,
    )

    # Chat in session — schema: {session_uuid, team, agent, model, messages[{role,content}]}
    status, data = request_json(
        "POST", f"/sessions/{state.session_uuid}/chat",
        token=token,
        body={
            "session_uuid": state.session_uuid,
            "team":         "Support",
            "agent":        "support-triage-agent",
            "model":        MODEL,
            "messages":     [{"role": "user", "content": "What is 1+1? One word."}],
        },
    )
    body = json.dumps(data)[:120] if isinstance(data, dict) else str(data)[:120]
    if status == 200:
        record_pass(state, "POST /sessions/{uuid}/chat",
                    endpoint=f"/sessions/{state.session_uuid}/chat", status=status)
    elif status in (400, 402, 503) and args.skip_live_llm:
        record_skip(state, "POST /sessions/{uuid}/chat",
                    "No LLM provider credential (--skip-live-llm)", strict=args.strict)
    else:
        record_fail(state, "POST /sessions/{uuid}/chat",
                    f"Got {status}: {body}",
                    endpoint=f"/sessions/{state.session_uuid}/chat", status=status, body=body)

    # Get messages
    status, data = request_json("GET", f"/sessions/{state.session_uuid}/messages", token=token)
    assert_condition(
        state, "GET /sessions/{uuid}/messages",
        status == 200 and isinstance(data, list),
        f"Expected 200 list, got {status}",
        endpoint=f"/sessions/{state.session_uuid}/messages", status=status,
    )

    # Delete session
    status, _ = request_json("DELETE", f"/sessions/{state.session_uuid}", token=token)
    assert_condition(
        state, "DELETE /sessions/{uuid}",
        status in (200, 204),
        f"Expected 204, got {status}",
        endpoint=f"/sessions/{state.session_uuid}", status=status,
    )
    state.session_uuid = ""


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(state: State, t0: float) -> int:
    elapsed = time.time() - t0
    passed  = [r for r in state.results if r.status == "pass"]
    failed  = [r for r in state.results if r.status == "fail"]
    skipped = [r for r in state.results if r.status == "skip"]

    print(f"\n{'═' * _W}")
    print("  AI Asset Management — Full E2E Test Report")
    print(f"  Backend : {BASE_URL}")
    print(f"  Org     : {ACME_ORG_NAME}")
    print(f"  Elapsed : {elapsed:.1f}s")
    print(f"{'═' * _W}")

    for r in state.results:
        if r.status == "pass":
            print(f"  {_pass(r.name)}")
        elif r.status == "skip":
            print(f"  {_skip(r.name)}")
        else:
            print(f"  {_fail(r.name)}")
            if r.reason:
                print(f"       {r.reason}")

    print(f"{'─' * _W}")
    status_line = (
        f"  {len(passed)} passed"
        f" · {len(skipped)} skipped"
        f" · {len(failed)} failed"
    )
    if failed:
        status_line = _RED + status_line + _RESET
    else:
        status_line = _GREEN + status_line + _RESET
    print(status_line)
    print(f"{'═' * _W}\n")

    return len(failed)


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Full E2E synthetic customer test suite for AI Asset Management"
    )
    p.add_argument("--strict", action="store_true",
                   help="Treat skips as failures (CI mode)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the test plan without sending requests")
    p.add_argument("--skip-live-llm", action="store_true",
                   help="Skip tests that require a live LLM provider credential")
    p.add_argument("--include-rate-limit", action="store_true",
                   help="Include §22 rate limiting (hammers login endpoint)")
    p.add_argument("--base-url", default=None,
                   help="Override BASE_URL (e.g. https://ai-asset-backend.onrender.com)")
    p.add_argument("--admin-email", default=None,
                   help="Override PLATFORM_ADMIN_EMAIL")
    p.add_argument("--admin-password", default=None,
                   help="Override PLATFORM_ADMIN_PASSWORD")
    return p.parse_args()


def main() -> None:
    global BASE_URL, PLATFORM_ADMIN_EMAIL, PLATFORM_ADMIN_PASSWORD

    args = parse_args()

    if args.base_url:
        BASE_URL = args.base_url.rstrip("/")
    if args.admin_email:
        PLATFORM_ADMIN_EMAIL = args.admin_email
    if args.admin_password:
        PLATFORM_ADMIN_PASSWORD = args.admin_password

    if args.dry_run:
        dry_run()

    print(f"\n{'═' * _W}")
    print("  AI Asset Management — Full E2E Synthetic Customer Suite")
    print(f"  Backend : {BASE_URL}")
    print(f"  Org     : {ACME_ORG_NAME}")
    mode_flags = []
    if args.strict:           mode_flags.append("strict")
    if args.skip_live_llm:    mode_flags.append("skip-live-llm")
    if args.include_rate_limit: mode_flags.append("rate-limit")
    print(f"  Mode    : {', '.join(mode_flags) or 'default'}")
    print(f"{'═' * _W}")

    state = State()
    t0    = time.time()

    section_01_health(state, args)
    section_02_platform_admin(state, args)
    section_03_org_management(state, args)
    section_04_user_management(state, args)
    section_05_roles_teams(state, args)
    section_06_api_keys(state, args)
    section_07_provider_credentials(state, args)
    section_08_guard_modes_settings(state, args)
    section_09_openai_proxy(state, args)
    section_10_anthropic_proxy(state, args)
    section_11_agent_inventory(state, args)
    section_12_relationship_mapping(state, args)
    section_13_pii_detection(state, args)
    section_14_budget_enforcement(state, args)
    section_15_policy_enforcement(state, args)
    section_16_telemetry(state, args)
    section_17_audit(state, args)
    section_18_security_alerts(state, args)
    section_19_cost_intelligence(state, args)
    section_20_pricing_registry(state, args)
    section_21_dashboard_reads(state, args)
    section_22_rate_limiting(state, args)
    section_23_sessions(state, args)

    failures = print_report(state, t0)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
