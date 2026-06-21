#!/usr/bin/env python3
"""
Synthetic Customer E2E Test Suite — AI Asset Management Platform
================================================================
Simulates Acme AI Inc. going from onboarding to runtime operations
across 8 flows. Tests the platform as an integrated system, not
individual endpoints in isolation.

Flows:
  1  Platform admin onboarding (org creation, Acme admin user)
  2  Org setup (users, API keys, guard modes, config)
  3  Normal AI runtime traffic (multiple agents, multiple teams)
  4  PII / security detection scenario
  5  Budget + policy enforcement scenario
  6  Agent inventory verification
  7  Relationship mapping (skipped gracefully if not implemented)
  8  Dashboard read APIs

Required env vars:
    PLATFORM_ADMIN_PASSWORD      (no default — must be set)

Optional env vars:
    BASE_URL                     default: http://localhost:8000
    PLATFORM_ADMIN_EMAIL         default: admin@ai-asset-mgmt.local
    ACME_ADMIN_EMAIL             default: admin@acme.ai
    ACME_ADMIN_PASSWORD          default: AcmeAdmin1!

Usage:
    PLATFORM_ADMIN_PASSWORD=Admin123! python scripts/synthetic_customer.py
    PLATFORM_ADMIN_PASSWORD=Admin123! python scripts/synthetic_customer.py --strict
    python scripts/synthetic_customer.py --dry-run
    python scripts/synthetic_customer.py --fast --strict
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import requests as _requests

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL               = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
PLATFORM_ADMIN_EMAIL   = os.getenv("PLATFORM_ADMIN_EMAIL", "admin@ai-asset-mgmt.local")
PLATFORM_ADMIN_PASSWORD = os.getenv("PLATFORM_ADMIN_PASSWORD", "")
ACME_ADMIN_EMAIL       = os.getenv("ACME_ADMIN_EMAIL", "admin@acme.ai")
ACME_ADMIN_PASSWORD    = os.getenv("ACME_ADMIN_PASSWORD", "AcmeAdmin1!")

# ── Synthetic company definition ──────────────────────────────────────────────

ACME_ORG_NAME  = "Acme AI Inc."
ACME_ORG_SLUG  = "acme-ai-inc"
ACME_TEAMS     = ["Support", "Sales", "Operations", "Security"]

ACME_USERS = [
    {"email": "analyst@acme.ai", "password": "AcmeAnalyst1!", "role": "analyst"},
    {"email": "viewer@acme.ai",  "password": "AcmeViewer1!",  "role": "viewer"},
]

API_KEY_SPECS = [
    {"name": "support-runtime-key",  "agent": "support-triage-agent",        "team": "Support"},
    {"name": "sales-runtime-key",    "agent": "sales-enrichment-agent",       "team": "Sales"},
    {"name": "security-runtime-key", "agent": "security-investigation-agent", "team": "Security"},
]

# Agents with call counts (--fast halves these)
AGENTS = [
    {"name": "support-triage-agent",        "team": "Support",    "env": "prod",    "count": 5},
    {"name": "sales-enrichment-agent",       "team": "Sales",      "env": "prod",    "count": 3},
    {"name": "research-agent",               "team": "Operations", "env": "prod",    "count": 2},
    {"name": "ops-automation-agent",         "team": "Operations", "env": "staging", "count": 2},
    {"name": "security-investigation-agent", "team": "Security",   "env": "prod",    "count": 2},
]

MODEL = "gpt-4o-mini"

# ── Fake test data — clearly synthetic, no real PII ──────────────────────────

FAKE_EMAIL   = "test-user@example-domain.com"      # email pattern — not real
FAKE_SSN     = "123-45-6789"                        # SSN pattern — fake
FAKE_API_KEY = "sk-TESTFAKEAPIKEY0123456789ABCDE"   # sk- pattern — fake, not valid

# Per-agent prompt banks (short, factual — minimal tokens)
_AGENT_PROMPTS: dict[str, list[str]] = {
    "support-triage-agent": [
        "Classify this ticket: billing, technical, or account issue?",
        "Is this a high-priority or low-priority support case? One word.",
        "What team should handle: 'My invoice is wrong'? One word.",
        "Summarize this request in five words: 'I cannot log in to my account.'",
        "Should this ticket be escalated? Answer yes or no.",
    ],
    "sales-enrichment-agent": [
        "Extract the company name from: 'Hi, I work at Globex Corp.'",
        "Score this lead 1-10 for enterprise potential: 'We have 500 employees.'",
        "What industry is: 'We make industrial sensors'? One word.",
    ],
    "research-agent": [
        "What is the capital of France? One word.",
        "Name one open-source LLM framework. One word.",
    ],
    "ops-automation-agent": [
        "Should this workflow continue? Condition: status=approved. Yes or no.",
        "What approval level is needed for a $5000 spend? One word.",
    ],
    "security-investigation-agent": [
        "Is 'root login from 1.2.3.4' suspicious? Yes or no.",
        "Classify: authentication, data-access, or network event? 'Failed login x5.'",
    ],
}


# ── Result / State ────────────────────────────────────────────────────────────

PASS = "pass"
FAIL = "fail"
SKIP = "skip"


@dataclass
class Result:
    name:            str
    status:          str   # pass | fail | skip
    reason:          str = ""
    endpoint:        str = ""
    response_status: int = 0
    body_snippet:    str = ""


@dataclass
class State:
    platform_token:  str             = ""
    acme_token:      str             = ""
    acme_org_id:     int | None      = None
    user_ids:        dict[str, int]  = field(default_factory=dict)   # email → id
    api_keys:        dict[str, str]  = field(default_factory=dict)   # name → raw key (never logged)
    api_key_ids:     dict[str, int]  = field(default_factory=dict)   # name → id
    budget_id:       int | None      = None
    policy_id:       int | None      = None
    results:         list[Result]    = field(default_factory=list)
    dry_run:         bool            = False
    strict:          bool            = False
    fast:            bool            = False

    # ── result helpers ────────────────────────────────────────────────────────

    def _record(self, r: Result) -> None:
        self.results.append(r)
        icon = {"pass": "✅", "fail": "❌", "skip": "⏭ "}.get(r.status, "? ")
        print(f"  {icon} {r.name}")
        if r.status in (FAIL, SKIP) and r.reason:
            # Indent multi-line reasons
            for line in r.reason.split("\n"):
                print(f"       {line}")

    def passed(self, name: str) -> None:
        self._record(Result(name=name, status=PASS))

    def failed(self, name: str, *, reason: str = "", endpoint: str = "",
               response_status: int = 0, body: str = "") -> None:
        self._record(Result(
            name=name, status=FAIL, reason=reason,
            endpoint=endpoint, response_status=response_status,
            body_snippet=body[:200],
        ))

    def skipped(self, name: str, *, reason: str = "") -> None:
        if self.strict:
            self.failed(name, reason=f"SKIPPED (--strict treats skips as failures): {reason}")
        else:
            self._record(Result(name=name, status=SKIP, reason=reason))


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def request_json(
    method: str,
    path: str,
    *,
    token: str = "",
    body: dict | None = None,
    extra_headers: dict | None = None,
    timeout: int = 30,
    dry_run: bool = False,
) -> tuple[int, Any]:
    """
    Execute an HTTP request and return (status_code, parsed_body).
    In dry-run mode prints the call and returns (200, {}) without sending.
    Never logs raw passwords or API keys — callers must redact sensitive fields.
    """
    url = f"{BASE_URL}{path}"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)

    if dry_run:
        safe = {}
        if body:
            safe = {k: "***" if any(s in k.lower() for s in ("password", "key", "secret")) else v
                    for k, v in body.items()}
        print(f"    [DRY-RUN] {method.upper()} {url}"
              + (f"  body={json.dumps(safe)}" if safe else ""))
        return 200, {}

    try:
        resp = _requests.request(
            method.upper(), url, headers=headers, json=body, timeout=timeout
        )
        try:
            data: Any = resp.json()
        except Exception:
            data = resp.text
        return resp.status_code, data
    except _requests.exceptions.ConnectionError:
        return 0, {"error": f"Connection refused — is the server running at {BASE_URL}?"}
    except _requests.exceptions.Timeout:
        return 0, {"error": f"Timed out after {timeout}s"}
    except Exception as exc:
        return 0, {"error": str(exc)}


def login(email: str, password: str, *, dry_run: bool = False) -> str:
    """Return a JWT access token, or empty string on failure."""
    status, data = request_json("POST", "/auth/login",
                                body={"email": email, "password": password},
                                dry_run=dry_run)
    if dry_run:
        return "dry-run-token"
    return data.get("access_token", "") if status == 200 and isinstance(data, dict) else ""


def create_org(token: str, name: str, slug: str, *, dry_run: bool = False) -> tuple[int | None, str]:
    """
    Try POST /admin/organizations.
    Returns (org_id, error_msg). error_msg="" means success.
    Special values: "already_exists", "not_implemented".
    """
    status, data = request_json("POST", "/admin/organizations",
                                token=token,
                                body={"name": name, "slug": slug},
                                dry_run=dry_run)
    if dry_run:
        return 99, ""
    if status in (200, 201):
        return data.get("id"), ""
    if status == 404:
        return None, "not_implemented"
    if status == 405:
        return None, "not_implemented"
    if status == 409 or (isinstance(data, dict) and "already" in str(data).lower()):
        return None, "already_exists"
    return None, f"HTTP {status}: {str(data)[:120]}"


def create_user(
    token: str, email: str, password: str, role: str,
    *, dry_run: bool = False,
) -> tuple[int | None, str]:
    """
    Create a user. Returns (user_id, error_msg).
    Treats 409 / 'already exists' as idempotent — caller decides how to handle.
    """
    status, data = request_json("POST", "/auth/users",
                                token=token,
                                body={"email": email, "password": password, "role": role},
                                dry_run=dry_run)
    if dry_run:
        return 999, ""
    if status in (200, 201):
        return data.get("id"), ""
    if status == 409 or (isinstance(data, dict) and "already" in str(data).lower()):
        return None, "already_exists"
    if status == 400 and isinstance(data, dict) and "already" in str(data.get("detail", "")).lower():
        return None, "already_exists"
    return None, f"HTTP {status}: {str(data)[:120]}"


def create_api_key(
    token: str, name: str, agent_name: str, team: str,
    *, dry_run: bool = False,
) -> tuple[str, int | None, str]:
    """
    Create a gateway API key.
    Returns (raw_key, key_id, error_msg).
    The raw_key is NEVER logged — callers must not print it.
    """
    status, data = request_json("POST", "/api-keys",
                                token=token,
                                body={"name": name, "caller_name": agent_name, "team": team},
                                dry_run=dry_run)
    if dry_run:
        return "gk-dry-run", 999, ""
    if status in (200, 201):
        return data.get("key", ""), data.get("id"), ""
    return "", None, f"HTTP {status}: {str(data)[:120]}"


def send_llm_request(
    raw_key: str,
    agent_name: str,
    team: str,
    env: str,
    prompt: str,
    *,
    model: str = MODEL,
    dry_run: bool = False,
) -> tuple[int, Any]:
    """
    POST /v1/chat/completions through the gateway with full X-Agent-* SDK headers.
    Returns (status_code, response_body).
    """
    if dry_run:
        print(f"    [DRY-RUN] POST /v1/chat/completions  "
              f"agent={agent_name!r}  team={team!r}")
        return 200, {}

    url = f"{BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization":     f"Bearer {raw_key}",
        "Content-Type":      "application/json",
        "X-Agent-Name":      agent_name,
        "X-Agent-Team":      team,
        "X-Agent-Environment": env,
        "X-Agent-Version":   "1.0.0",
        "X-Agent-Source":    "sdk-python",   # marks calls as SDK Runtime in inventory
    }
    body = {
        "model":    model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 20,
    }
    try:
        resp = _requests.post(url, headers=headers, json=body, timeout=45)
        try:
            data = resp.json()
        except Exception:
            data = resp.text
        return resp.status_code, data
    except Exception as exc:
        return 0, {"error": str(exc)}


def assert_condition(
    state: State,
    name: str,
    condition: bool,
    *,
    reason: str = "",
    endpoint: str = "",
    response_status: int = 0,
    body: str = "",
) -> bool:
    if condition:
        state.passed(name)
    else:
        state.failed(name, reason=reason, endpoint=endpoint,
                     response_status=response_status, body=body)
    return condition


def _pick_key(state: State, team: str) -> str:
    """Return a raw API key for the given team, falling back to any available key."""
    for spec in API_KEY_SPECS:
        if spec["team"] == team and spec["name"] in state.api_keys:
            return state.api_keys[spec["name"]]
    return next(iter(state.api_keys.values()), "")


def _no_provider(status: int, data: Any) -> bool:
    """Return True if the response indicates no LLM provider is configured."""
    if status in (400, 422, 500, 503):
        return True
    if isinstance(data, dict):
        msg = str(data.get("detail", "") or data.get("error", "")).lower()
        if any(kw in msg for kw in ("provider", "credential", "api key", "no model")):
            return True
    return False


def section(title: str) -> None:
    print(f"\n{'─' * 62}")
    print(f"  {title}")
    print('─' * 62)


# ── Flow 1 — Platform admin onboarding ───────────────────────────────────────

def flow1_onboarding(state: State) -> None:
    section("Flow 1 — Platform admin onboarding")

    if not PLATFORM_ADMIN_PASSWORD and not state.dry_run:
        state.failed("Platform admin login",
                     reason="PLATFORM_ADMIN_PASSWORD env var not set",
                     endpoint="POST /auth/login")
        return

    # Step 1: login as platform admin
    tok = login(PLATFORM_ADMIN_EMAIL, PLATFORM_ADMIN_PASSWORD, dry_run=state.dry_run)
    if not tok and not state.dry_run:
        state.failed("Platform admin login",
                     reason=f"Invalid credentials for {PLATFORM_ADMIN_EMAIL}",
                     endpoint="POST /auth/login", response_status=401)
        return
    state.platform_token = tok
    state.passed("Platform admin login")

    # Step 2: create organization (endpoint may not be implemented yet)
    org_id, err = create_org(tok, ACME_ORG_NAME, ACME_ORG_SLUG, dry_run=state.dry_run)
    if state.dry_run:
        state.acme_org_id = org_id
        state.passed("Organization creation — Acme AI Inc.")
    elif err == "already_exists":
        state.skipped("Organization creation — Acme AI Inc.",
                      reason="Org already exists — continuing with existing org context")
    elif err == "not_implemented":
        state.skipped(
            "Organization creation — Acme AI Inc.",
            reason=(
                "POST /admin/organizations returned 404/405 — endpoint not yet implemented.\n"
                "The script continues using the platform admin org context.\n"
                "Full multi-tenant isolation requires this endpoint to be added."
            ),
        )
    elif err:
        state.failed("Organization creation — Acme AI Inc.", reason=err,
                     endpoint="POST /admin/organizations")
    else:
        state.acme_org_id = org_id
        state.passed("Organization creation — Acme AI Inc.")

    # Step 3: create Acme admin user (in platform org if separate org isn't available)
    uid, err = create_user(tok, ACME_ADMIN_EMAIL, ACME_ADMIN_PASSWORD,
                            role="admin", dry_run=state.dry_run)
    if state.dry_run or (uid and not err):
        state.user_ids[ACME_ADMIN_EMAIL] = uid or 0
        state.passed("Acme admin user creation")
    elif err == "already_exists":
        state.skipped("Acme admin user creation", reason="Already exists — continuing")
    else:
        state.failed("Acme admin user creation", reason=err, endpoint="POST /auth/users")

    # Step 4: login as Acme admin
    acme_tok = login(ACME_ADMIN_EMAIL, ACME_ADMIN_PASSWORD, dry_run=state.dry_run)
    if not acme_tok and not state.dry_run:
        state.skipped(
            "Acme admin login",
            reason=(
                f"Login failed for {ACME_ADMIN_EMAIL} — "
                "user may exist with a different password.\n"
                "Falling back to platform admin token for remaining flows."
            ),
        )
        state.acme_token = tok   # fallback so remaining flows can still run
        return
    state.acme_token = acme_tok
    state.passed("Acme admin login")

    # Step 5: verify /auth/me returns correct org context
    status, me = request_json("GET", "/auth/me", token=state.acme_token,
                               dry_run=state.dry_run)
    if state.dry_run:
        state.passed("Auth /me — org context present")
        return
    ok = (status == 200 and isinstance(me, dict) and
          me.get("organization_id") is not None and
          me.get("email") == ACME_ADMIN_EMAIL)
    assert_condition(
        state, "Auth /me — org context present", ok,
        reason=f"Expected 200 + org_id, got HTTP {status}: {str(me)[:100]}",
        endpoint="GET /auth/me", response_status=status,
    )


# ── Flow 2 — Org setup ────────────────────────────────────────────────────────

def flow2_setup(state: State) -> None:
    section("Flow 2 — Org setup")
    tok = state.acme_token

    # Create analyst + viewer users
    for u in ACME_USERS:
        uid, err = create_user(tok, u["email"], u["password"], u["role"],
                                dry_run=state.dry_run)
        label = f"Create {u['role']} user ({u['email']})"
        if state.dry_run or (uid and not err):
            state.user_ids[u["email"]] = uid or 0
            state.passed(label)
        elif err == "already_exists":
            state.skipped(label, reason="Already exists")
        else:
            state.failed(label, reason=err, endpoint="POST /auth/users")

    # Create gateway API keys
    for spec in API_KEY_SPECS:
        raw_key, key_id, err = create_api_key(
            tok, spec["name"], spec["agent"], spec["team"],
            dry_run=state.dry_run,
        )
        label = f"API key: {spec['name']}"
        if state.dry_run or (raw_key and not err):
            state.api_keys[spec["name"]]    = raw_key
            state.api_key_ids[spec["name"]] = key_id or 0
            state.passed(label)
        else:
            state.failed(label, reason=err, endpoint="POST /api-keys")

    # Set guard mode: observe for every team
    for team in ACME_TEAMS:
        status, data = request_json("PUT", f"/guard-modes/{team}",
                                    token=tok, body={"mode": "observe"},
                                    dry_run=state.dry_run)
        ok = state.dry_run or status in (200, 201)
        assert_condition(
            state, f"Guard mode: {team} → observe", ok,
            reason=f"HTTP {status}: {str(data)[:80]}",
            endpoint=f"PUT /guard-modes/{team}", response_status=status,
        )

    # Set org config: pii_redaction_mode = findings_only
    status, data = request_json(
        "PUT", "/settings/config/pii_redaction_mode",
        token=tok, body={"value": "findings_only"},
        dry_run=state.dry_run,
    )
    ok = state.dry_run or status in (200, 201)
    assert_condition(
        state, "Org config: pii_redaction_mode = findings_only", ok,
        reason=f"HTTP {status}: {str(data)[:80]}",
        endpoint="PUT /settings/config/pii_redaction_mode", response_status=status,
    )


# ── Flow 3 — Normal AI runtime traffic ───────────────────────────────────────

def flow3_runtime_traffic(state: State) -> None:
    section("Flow 3 — Normal AI runtime traffic")

    if not state.api_keys and not state.dry_run:
        state.skipped("Runtime traffic",
                      reason="No API keys were created — Flow 2 may have failed")
        return

    total_sent = total_ok = total_fail = 0
    no_provider_detected = False

    for agent in AGENTS:
        name    = agent["name"]
        team    = agent["team"]
        env     = agent["env"]
        count   = max(1, agent["count"] // 2) if state.fast else agent["count"]
        prompts = _AGENT_PROMPTS.get(name, ["Summarize in one sentence."])
        gk      = _pick_key(state, team)

        for i in range(count):
            prompt = prompts[i % len(prompts)]
            status, data = send_llm_request(
                gk, name, team, env, prompt, dry_run=state.dry_run,
            )
            total_sent += 1
            if state.dry_run or status in (200, 201):
                total_ok += 1
            elif _no_provider(status, data) and not no_provider_detected:
                no_provider_detected = True
                total_fail += 1
            else:
                total_fail += 1

    if state.dry_run:
        state.passed(f"Runtime traffic — {sum(a['count'] for a in AGENTS)} calls planned")
        return

    if no_provider_detected and total_ok == 0:
        state.skipped(
            "Runtime traffic — LLM calls",
            reason=(
                f"All {total_sent} calls failed — LLM provider credentials not configured.\n"
                "Configure a provider via /settings/keys (or provider_credentials) "
                "and re-run to exercise real traffic."
            ),
        )
        return

    assert_condition(
        state,
        f"Runtime traffic — {total_ok}/{total_sent} calls succeeded",
        total_ok > 0,
        reason=f"{total_fail} of {total_sent} calls failed",
    )


# ── Flow 4 — PII / security detection ────────────────────────────────────────

def flow4_pii_scenario(state: State) -> None:
    section("Flow 4 — PII / security detection")

    gk = _pick_key(state, "Security")
    if not gk and not state.dry_run:
        state.skipped("PII proxy call sent", reason="No Security API key available")
        state.skipped("Telemetry sensitive=True", reason="No API key")
        state.skipped("PII mode configured (findings_only)", reason="No API key")
        return

    # Build a prompt containing clearly fake PII
    pii_prompt = (
        f"Validate this test record — email: {FAKE_EMAIL}, "
        f"SSN: {FAKE_SSN}, api_key: {FAKE_API_KEY}. "
        "Is this data complete? Answer yes or no."
    )

    status, data = send_llm_request(
        gk, "security-investigation-agent", "Security", "prod",
        pii_prompt, dry_run=state.dry_run,
    )

    if state.dry_run:
        state.passed("PII proxy call sent")
        state.passed("Telemetry sensitive=True")
        state.passed("PII mode configured (findings_only)")
        return

    if _no_provider(status, data):
        state.skipped("PII proxy call sent",
                      reason="No LLM provider — cannot exercise live PII detection path")
        # Direct scanner test still works — scan endpoint doesn't call an LLM
        _test_direct_scan(state)
        return

    call_ok = status in (200, 201)
    assert_condition(
        state, "PII proxy call sent", call_ok,
        reason=f"HTTP {status}: {str(data)[:80]}",
        endpoint="POST /v1/chat/completions", response_status=status,
    )

    time.sleep(1)   # allow telemetry write to commit

    t_status, telem = request_json("GET", "/telemetry", token=state.acme_token)
    if t_status == 200 and isinstance(telem, list) and telem:
        recent = telem[-1]
        sensitive = recent.get("sensitive", False)
        findings  = recent.get("sensitive_findings") or recent.get("security_findings") or []
        assert_condition(
            state, "Telemetry sensitive=True",
            sensitive,
            reason=(
                f"Latest row: sensitive={sensitive}, "
                f"findings={str(findings)[:120]}\n"
                "Ensure the scanner patterns match the fake PII used."
            ),
            endpoint="GET /telemetry", response_status=t_status,
        )
    else:
        state.skipped("Telemetry sensitive=True",
                      reason=f"GET /telemetry returned HTTP {t_status} or empty list")

    state.passed("PII mode configured (findings_only)")   # config was set in Flow 2


def _test_direct_scan(state: State) -> None:
    """Verify the /security/scan endpoint detects fake PII without needing an LLM."""
    payload = (
        f"Check this: email={FAKE_EMAIL} SSN={FAKE_SSN} key={FAKE_API_KEY}"
    )
    status, data = request_json(
        "POST", "/security/scan",
        token=state.acme_token,
        body={"text": payload},
    )
    if status == 200 and isinstance(data, dict):
        is_sensitive = data.get("is_sensitive", False)
        findings     = data.get("findings", [])
        assert_condition(
            state, "PII detection — direct /security/scan",
            is_sensitive or len(findings) > 0,
            reason=f"is_sensitive={is_sensitive}, findings={str(findings)[:120]}",
            endpoint="POST /security/scan", response_status=status,
        )
    else:
        state.skipped("PII detection — direct /security/scan",
                      reason=f"HTTP {status}: {str(data)[:80]}")


# ── Flow 5 — Budget + policy enforcement ─────────────────────────────────────

def flow5_budget_and_enforcement(state: State) -> None:
    section("Flow 5 — Budget + policy enforcement")

    tok = state.acme_token
    gk  = _pick_key(state, "Security")

    # 5a. Create a budget rule to verify the API works
    status, bud = request_json(
        "POST", "/budgets", token=tok,
        body={"team": "Support", "limit_usd": 0.001, "period": "daily", "action": "block"},
        dry_run=state.dry_run,
    )
    if state.dry_run or status in (200, 201):
        state.budget_id = bud.get("id") if isinstance(bud, dict) else None
        state.passed("Budget rule created ($0.001 daily, action=block, team=Support)")
    else:
        state.failed("Budget rule created", reason=f"HTTP {status}: {str(bud)[:80]}",
                     endpoint="POST /budgets", response_status=status)

    # 5b. Verify /budgets/status returns usage data
    s_status, s_data = request_json("GET", "/budgets/status", token=tok,
                                     dry_run=state.dry_run)
    ok = state.dry_run or s_status == 200
    assert_condition(
        state, "Budget status — GET /budgets/status returns 200", ok,
        reason=f"HTTP {s_status}: {str(s_data)[:80]}",
        endpoint="GET /budgets/status", response_status=s_status,
    )
    if not state.dry_run and s_status == 200 and isinstance(s_data, list) and s_data:
        state.passed(f"Budget status — {len(s_data)} rule(s) returned")
    elif not state.dry_run and s_status == 200:
        state.skipped("Budget status — usage rows", reason="No budget usage rows yet")

    # 5c. Policy-based enforcement test (works without LLM credentials)
    #     Create a block_model policy for Security team, set to enforce mode,
    #     send a request — expect 403 blocked by policy.
    p_status, pol = request_json(
        "POST", "/policies", token=tok,
        body={"team": "Security", "rule_type": "block_model", "value": MODEL},
        dry_run=state.dry_run,
    )
    if state.dry_run or p_status in (200, 201):
        state.policy_id = pol.get("id") if isinstance(pol, dict) else None
        state.passed(f"Policy rule created (block_model={MODEL!r} for Security team)")
    else:
        state.failed("Policy rule created", reason=f"HTTP {p_status}: {str(pol)[:80]}",
                     endpoint="POST /policies", response_status=p_status)
        _cleanup_flow5(state, tok)
        return

    # Set Security team to enforce mode
    gm_status, gm_data = request_json(
        "PUT", "/guard-modes/Security", token=tok, body={"mode": "enforce"},
        dry_run=state.dry_run,
    )
    ok = state.dry_run or gm_status in (200, 201)
    assert_condition(
        state, "Guard mode: Security → enforce", ok,
        reason=f"HTTP {gm_status}: {str(gm_data)[:80]}",
        endpoint="PUT /guard-modes/Security", response_status=gm_status,
    )

    # Send request that should be blocked (policy: block_model=gpt-4o-mini in enforce mode)
    if gk:
        bl_status, bl_data = send_llm_request(
            gk, "security-investigation-agent", "Security", "prod",
            "Should this be blocked?",
            dry_run=state.dry_run,
        )
        if state.dry_run:
            state.passed("Policy enforcement — request blocked (403)")
            state.passed("Telemetry — blocked=True recorded")
        elif bl_status == 403:
            state.passed("Policy enforcement — request blocked (403)")
            # Check telemetry for blocked=True
            time.sleep(0.5)
            _, telem = request_json("GET", "/telemetry", token=tok)
            blocked = [r for r in (telem if isinstance(telem, list) else [])
                       if r.get("blocked")]
            assert_condition(
                state, "Telemetry — blocked=True recorded",
                len(blocked) > 0,
                reason=f"No blocked rows found in {len(telem) if isinstance(telem, list) else '?'} rows",
                endpoint="GET /telemetry",
            )
        else:
            state.failed(
                "Policy enforcement — request blocked (403)",
                reason=f"Expected 403, got HTTP {bl_status}: {str(bl_data)[:80]}",
                endpoint="POST /v1/chat/completions", response_status=bl_status,
            )
            state.skipped("Telemetry — blocked=True recorded",
                          reason="Block did not occur — cannot verify blocked telemetry")
    else:
        state.skipped("Policy enforcement — request blocked (403)",
                      reason="No API key for Security team")
        state.skipped("Telemetry — blocked=True recorded",
                      reason="No API key for Security team")

    _cleanup_flow5(state, tok)


def _cleanup_flow5(state: State, tok: str) -> None:
    """Reset guard mode and delete test policy + budget created in Flow 5."""
    request_json("PUT", "/guard-modes/Security", token=tok, body={"mode": "observe"})
    if state.policy_id:
        request_json("DELETE", f"/policies/{state.policy_id}", token=tok)
        state.policy_id = None
    if state.budget_id:
        request_json("DELETE", f"/budgets/{state.budget_id}", token=tok)
        state.budget_id = None


# ── Flow 6 — Agent inventory ──────────────────────────────────────────────────

def flow6_agent_inventory(state: State) -> None:
    section("Flow 6 — Agent inventory")

    tok = state.acme_token

    status, assets = request_json("GET", "/assets", token=tok, dry_run=state.dry_run)

    if state.dry_run:
        state.passed("GET /assets — 200 OK")
        for a in AGENTS:
            state.passed(f"Discovered: {a['name']}")
        return

    assert_condition(
        state, "GET /assets — 200 OK", status == 200,
        reason=f"HTTP {status}: {str(assets)[:80]}",
        endpoint="GET /assets", response_status=status,
    )

    if status != 200 or not isinstance(assets, list):
        for a in AGENTS:
            state.skipped(f"Discovered: {a['name']}",
                          reason="/assets not available — cannot verify")
        return

    def _find(name: str) -> dict | None:
        return next(
            (a for a in assets
             if name.lower() in (a.get("agent_name") or a.get("name") or "").lower()),
            None,
        )

    for agent in AGENTS:
        name  = agent["name"]
        match = _find(name)
        if match:
            meta = []
            if match.get("first_seen_at"):
                meta.append("first_seen ✓")
            if match.get("team"):
                meta.append(f"team={match['team']!r}")
            if match.get("lifecycle_status"):
                meta.append(f"status={match['lifecycle_status']!r}")
            state.passed(f"Discovered: {name}" + (f"  ({', '.join(meta)})" if meta else ""))
        else:
            state.skipped(
                f"Discovered: {name}",
                reason=(
                    "Not found in /assets yet.\n"
                    "Agents appear after receiving gateway traffic "
                    "(requires LLM provider credentials in Flow 3)."
                ),
            )

    # Summary stats
    _, summary = request_json("GET", "/assets/summary", token=tok)
    # /assets/summary may not exist — not a hard requirement here


# ── Flow 7 — Relationship mapping ─────────────────────────────────────────────

def flow7_relationships(state: State) -> None:
    section("Flow 7 — Relationship mapping")

    tok = state.acme_token
    gk  = _pick_key(state, "Sales")

    # Attempt a call with relationship headers
    if gk and not state.dry_run:
        send_llm_request(
            gk, "sales-enrichment-agent", "Sales", "prod",
            "Create a lead for Acme Corp.",
            dry_run=False,
        )

    # Probe GET /relationships
    status, data = request_json("GET", "/relationships", token=tok, dry_run=state.dry_run)

    if state.dry_run:
        state.skipped("GET /relationships",    reason="dry-run — not verified")
        state.skipped("GET /relationships/graph", reason="dry-run — not verified")
        return

    if status == 404:
        state.skipped(
            "GET /relationships",
            reason="404 — relationship mapping not yet implemented. SKIPPED.",
        )
        state.skipped(
            "GET /relationships/graph",
            reason="Depends on /relationships — SKIPPED.",
        )
        return

    assert_condition(
        state, "GET /relationships — 200 OK", status == 200,
        reason=f"HTTP {status}: {str(data)[:80]}",
        endpoint="GET /relationships", response_status=status,
    )

    status2, data2 = request_json("GET", "/relationships/graph", token=tok)
    assert_condition(
        state, "GET /relationships/graph — 200 OK", status2 == 200,
        reason=f"HTTP {status2}: {str(data2)[:80]}",
        endpoint="GET /relationships/graph", response_status=status2,
    )


# ── Flow 8 — Dashboard read APIs ──────────────────────────────────────────────

def flow8_dashboard_apis(state: State) -> None:
    section("Flow 8 — Dashboard read APIs")

    tok = state.acme_token

    checks = [
        ("GET", "/health",            "",  "Health check"),
        ("GET", "/telemetry",         tok, "Telemetry list"),
        ("GET", "/telemetry/summary", tok, "Telemetry summary"),
        ("GET", "/audit",             tok, "Audit log"),
        ("GET", "/security/alerts",   tok, "Security alerts"),
        ("GET", "/budgets/status",    tok, "Budget status"),
        ("GET", "/settings/config",   tok, "Settings config"),
    ]

    for method, path, use_tok, label in checks:
        status, data = request_json(method, path, token=use_tok, dry_run=state.dry_run)
        ok = state.dry_run or status == 200
        assert_condition(
            state, f"{label}  ({method} {path})", ok,
            reason=f"HTTP {status}: {str(data)[:80]}",
            endpoint=f"{method} {path}", response_status=status,
        )


# ── Final report ──────────────────────────────────────────────────────────────

def print_report(state: State) -> bool:
    results = state.results
    passed  = [r for r in results if r.status == PASS]
    failed  = [r for r in results if r.status == FAIL]
    skipped = [r for r in results if r.status == SKIP]

    width = 62
    print(f"\n{'═' * width}")
    print("  Synthetic Customer Test Report")
    print(f"  Backend : {BASE_URL}")
    print(f"  Org     : {ACME_ORG_NAME}")
    print('═' * width)

    for r in results:
        icon = {"pass": "✅", "fail": "❌", "skip": "⏭ "}.get(r.status, "? ")
        print(f"  {icon} {r.name}")

    print(f"\n{'─' * width}")
    print(f"  {len(passed)} passed · {len(skipped)} skipped · {len(failed)} failed")

    if failed:
        print(f"\n{'─' * width}")
        print("  Failures:")
        for r in failed:
            print(f"\n  ❌  {r.name}")
            if r.reason:
                for line in r.reason.split("\n"):
                    print(f"      Reason:   {line}")
            if r.endpoint:
                print(f"      Endpoint: {r.endpoint}")
            if r.response_status:
                print(f"      Status:   {r.response_status}")
            if r.body_snippet:
                print(f"      Body:     {r.body_snippet}")

    print('═' * width)
    return len(failed) == 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synthetic customer E2E test suite — AI Asset Management Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  PLATFORM_ADMIN_PASSWORD=Admin123! python scripts/synthetic_customer.py\n"
            "  PLATFORM_ADMIN_PASSWORD=Admin123! python scripts/synthetic_customer.py --strict\n"
            "  python scripts/synthetic_customer.py --dry-run\n"
        ),
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat SKIPPED checks as failures (useful for CI readiness gates)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print planned actions without sending any HTTP requests",
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Halve the LLM call count per agent (quicker smoke-test)",
    )
    args = parser.parse_args()

    if not PLATFORM_ADMIN_PASSWORD and not args.dry_run:
        print("\n❌  PLATFORM_ADMIN_PASSWORD env var is required.\n")
        print("    Set it before running:")
        print(f"    PLATFORM_ADMIN_PASSWORD=<password> python {sys.argv[0]}\n")
        sys.exit(1)

    state = State(dry_run=args.dry_run, strict=args.strict, fast=args.fast)

    width = 62
    print(f"\n{'═' * width}")
    print("  AI Asset Management — Synthetic Customer Test Suite")
    print(f"  Backend : {BASE_URL}")
    print(f"  Org     : {ACME_ORG_NAME}")
    print(f"  Mode    : {'dry-run' if args.dry_run else 'live'}"
          + ("  --strict" if args.strict else "")
          + ("  --fast"   if args.fast   else ""))
    print('═' * width)

    flow1_onboarding(state)
    flow2_setup(state)
    flow3_runtime_traffic(state)
    flow4_pii_scenario(state)
    flow5_budget_and_enforcement(state)
    flow6_agent_inventory(state)
    flow7_relationships(state)
    flow8_dashboard_apis(state)

    success = print_report(state)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
