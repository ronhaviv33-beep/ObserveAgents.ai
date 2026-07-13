#!/usr/bin/env python3
"""
8-Hour Continuous E2E Test Runner — AI Asset Management Platform
================================================================
Runs the full synthetic customer E2E suite (synthetic_customer_e2e.py)
on a schedule and fires health heartbeats + optional gateway traffic
between runs.  After 8 hours it prints a final cumulative report.

What it does every cycle:
  1. Run scripts/synthetic_customer_e2e.py  (full 96-check suite)
  2. Until the next scheduled E2E run:
       • Every --heartbeat seconds: GET /health + telemetry snapshot
       • Every --gw-interval seconds: send a gateway proxy call (if --gk given)

Required:
    PLATFORM_ADMIN_PASSWORD env var  OR  --admin-password flag

Optional:
    BASE_URL                   default: http://localhost:10000
    PLATFORM_ADMIN_EMAIL       default: admin@ai-asset-mgmt.local

Usage:
    # Basic (no live LLM, no gateway traffic)
    BASE_URL=http://localhost:10000 \\
    PLATFORM_ADMIN_PASSWORD='Admin123!' \\
    python scripts/run_8h_e2e.py

    # With gateway traffic via API key
    BASE_URL=http://localhost:10000 \\
    PLATFORM_ADMIN_PASSWORD='Admin123!' \\
    python scripts/run_8h_e2e.py --gk gk-<your-key>

    # Short smoke test (1 h, E2E every 15 min)
    PLATFORM_ADMIN_PASSWORD='Admin123!' \\
    python scripts/run_8h_e2e.py --hours 1 --e2e-interval 15

    # Strict mode — any skip is a failure
    PLATFORM_ADMIN_PASSWORD='Admin123!' \\
    python scripts/run_8h_e2e.py --strict
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import random
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL                = os.getenv("BASE_URL", "http://localhost:10000").rstrip("/")
PLATFORM_ADMIN_EMAIL    = os.getenv("PLATFORM_ADMIN_EMAIL", "admin@ai-asset-mgmt.local")
PLATFORM_ADMIN_PASSWORD = os.getenv("PLATFORM_ADMIN_PASSWORD", "")

E2E_SCRIPT = os.path.join(os.path.dirname(__file__), "synthetic_customer_e2e.py")

# Gateway soak agents (used if --gk provided)
_GW_AGENTS = [
    {"name": "soak-rag-agent",     "team": "Engineering",  "env": "prod"},
    {"name": "soak-chat-agent",    "team": "Support",      "env": "prod"},
    {"name": "soak-ops-agent",     "team": "Operations",   "env": "prod"},
    {"name": "soak-qa-agent",      "team": "QA",           "env": "staging"},
    {"name": "soak-monitor-agent", "team": "Security",     "env": "prod"},
]

_GW_PROMPTS = [
    "What is 2+2? One word.",
    "Name one planet. One word.",
    "What colour is the sky? One word.",
    "Capital of France? One word.",
    "Is water wet? Yes or no.",
    "Name one element. One word.",
    "Is Python interpreted? Yes or no.",
    "Square root of 9? Number only.",
]

# ── ANSI ──────────────────────────────────────────────────────────────────────

_G = "\033[92m"   # green
_R = "\033[91m"   # red
_Y = "\033[93m"   # yellow
_C = "\033[96m"   # cyan
_B = "\033[1m"    # bold
_X = "\033[0m"    # reset

W = 70


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class E2ERun:
    run_no:   int
    started:  float
    elapsed:  float  = 0.0
    passed:   int    = 0
    skipped:  int    = 0
    failed:   int    = 0
    exit_code:int    = -1
    error:    str    = ""


@dataclass
class HeartbeatResult:
    ts:      str
    healthy: bool
    agents:  int    = 0
    records: int    = 0
    latency: float  = 0.0
    error:   str    = ""


@dataclass
class GWResult:
    ts:    str
    agent: str
    ok:    bool
    code:  int    = 0
    msg:   str    = ""


@dataclass
class State:
    e2e_runs:   list[E2ERun]        = field(default_factory=list)
    heartbeats: list[HeartbeatResult] = field(default_factory=list)
    gw_calls:   list[GWResult]      = field(default_factory=list)
    jwt_token:  str                 = ""
    jwt_expiry: float               = 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _fmt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def _eta(end_time: float) -> str:
    remaining = max(0.0, end_time - time.time())
    return _fmt(remaining)


def _header(state: State, args: argparse.Namespace, end_time: float) -> None:
    runs        = state.e2e_runs
    total_p     = sum(r.passed  for r in runs)
    total_f     = sum(r.failed  for r in runs)
    total_s     = sum(r.skipped for r in runs)
    hb_ok       = sum(1 for h in state.heartbeats if h.healthy)
    hb_total    = len(state.heartbeats)
    gw_ok       = sum(1 for g in state.gw_calls if g.ok)
    gw_total    = len(state.gw_calls)
    elapsed_total = time.time() - (end_time - args.hours * 3600)

    print(f"\n{'─' * W}")
    print(f"  Elapsed {_fmt(elapsed_total)}  |  Remaining {_eta(end_time)}  |  Run #{len(runs)}")
    if runs:
        last = runs[-1]
        last_color = _G if last.failed == 0 else _R
        print(f"  Last E2E : {last_color}{last.passed}✅ {last.skipped}⏭  {last.failed}❌{_X}  ({last.elapsed:.1f}s)")
    print(f"  Total    : {_G}{total_p}✅{_X}  {_Y}{total_s}⏭{_X}  {_R}{total_f}❌{_X}  across {len(runs)} run(s)")
    if hb_total:
        pct = 100 * hb_ok / hb_total
        print(f"  Health   : {hb_ok}/{hb_total} OK ({pct:.0f}%)")
    if gw_total:
        pct = 100 * gw_ok / gw_total
        print(f"  Gateway  : {gw_ok}/{gw_total} OK ({pct:.0f}%)")
    print(f"{'─' * W}")


# ── JWT management ────────────────────────────────────────────────────────────

def _ensure_token(state: State) -> None:
    """Refresh JWT if missing or within 5 min of expiry."""
    if state.jwt_token and time.time() < state.jwt_expiry - 300:
        return
    try:
        r = httpx.post(
            f"{BASE_URL}/auth/login",
            json={"email": PLATFORM_ADMIN_EMAIL, "password": PLATFORM_ADMIN_PASSWORD},
            timeout=15,
        )
        if r.status_code == 200:
            state.jwt_token  = r.json().get("access_token", "")
            state.jwt_expiry = time.time() + 3600   # assume 1h TTL
        else:
            print(f"  [{_ts()}] {_R}Login failed: {r.status_code}{_X}")
    except Exception as e:
        print(f"  [{_ts()}] {_R}Login error: {e}{_X}")


# ── Health heartbeat ──────────────────────────────────────────────────────────

def run_heartbeat(state: State) -> HeartbeatResult:
    t0 = time.time()
    result = HeartbeatResult(ts=_ts(), healthy=False)
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=10)
        result.healthy = (r.status_code == 200)
        result.latency = time.time() - t0
        if state.jwt_token:
            try:
                t = httpx.get(
                    f"{BASE_URL}/telemetry/summary",
                    headers={"Authorization": f"Bearer {state.jwt_token}"},
                    timeout=10,
                )
                if t.status_code == 200:
                    body = t.json()
                    result.records = body.get("total_calls", 0)
                a = httpx.get(
                    f"{BASE_URL}/agents/summary",
                    headers={"Authorization": f"Bearer {state.jwt_token}"},
                    timeout=10,
                )
                if a.status_code == 200:
                    result.agents = a.json().get("total_agents", 0)
            except Exception:
                pass
    except Exception as e:
        result.error = str(e)[:60]

    state.heartbeats.append(result)
    color = _G if result.healthy else _R
    status = "200" if result.healthy else f"ERR {result.error}"
    agent_str = f"  agents={result.agents}  records={result.records}" if result.agents or result.records else ""
    print(f"  [{result.ts}] {color}[PING]{_X} /health → {status}  {result.latency*1000:.0f}ms{agent_str}")
    return result


# ── Gateway traffic ───────────────────────────────────────────────────────────

def run_gw_call(state: State, gk: str) -> GWResult:
    agent  = random.choice(_GW_AGENTS)
    prompt = random.choice(_GW_PROMPTS)
    result = GWResult(ts=_ts(), agent=agent["name"], ok=False)
    try:
        r = httpx.post(
            f"{BASE_URL}/v1/chat/completions",
            headers={
                "Authorization":       f"Bearer {gk}",
                "X-Agent-Name":        agent["name"],
                "X-Agent-Team":        agent["team"],
                "X-Agent-Environment": agent["env"],
                "X-Agent-Source":      "sdk-python",
            },
            json={
                "model":      "gpt-4o-mini",
                "messages":   [{"role": "user", "content": prompt}],
                "max_tokens": 20,
            },
            timeout=45,
        )
        result.code = r.status_code
        result.ok   = r.status_code == 200
        if result.ok:
            try:
                result.msg = r.json()["choices"][0]["message"]["content"][:30].strip()
            except Exception:
                result.msg = r.text[:30]
        else:
            result.msg = r.text[:50]
    except Exception as e:
        result.msg = str(e)[:50]

    state.gw_calls.append(result)
    color  = _G if result.ok else _R
    status = f"{result.code}" if result.code else "ERR"
    print(f"  [{result.ts}] {color}[GW  ]{_X} {agent['name']:<22} {status}  {result.msg!r}")
    return result


# ── E2E suite run ─────────────────────────────────────────────────────────────

_RESULT_RE = re.compile(r"(\d+)\s+passed\s*·\s*(\d+)\s+skipped\s*·\s*(\d+)\s+failed")


def run_e2e(state: State, args: argparse.Namespace, run_no: int) -> E2ERun:
    run = E2ERun(run_no=run_no, started=time.time())
    print(f"\n[{_ts()}] {_B}── Run #{run_no} — Full E2E Suite ─{'─' * (W - 30)}{_X}")
    print(f"  Running synthetic_customer_e2e.py … ({_eta(args._end_time)} remaining)")

    cmd = [sys.executable, E2E_SCRIPT, "--skip-live-llm"]
    if args.strict:
        cmd.append("--strict")

    env = os.environ.copy()
    env["BASE_URL"]                = BASE_URL
    env["PLATFORM_ADMIN_EMAIL"]    = PLATFORM_ADMIN_EMAIL
    env["PLATFORM_ADMIN_PASSWORD"] = PLATFORM_ADMIN_PASSWORD

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,   # 5 min max for one E2E pass
        )
        run.exit_code = result.returncode
        output = result.stdout + result.stderr

        # Parse summary line: "88 passed · 8 skipped · 0 failed"
        m = _RESULT_RE.search(output)
        if m:
            run.passed, run.skipped, run.failed = int(m.group(1)), int(m.group(2)), int(m.group(3))

        # Print the last section of output (summary block)
        lines = output.strip().splitlines()
        start = next((i for i, l in enumerate(lines) if "══" in l and "Report" in l), -20)
        for line in lines[start:]:
            print(f"  {line}")

    except subprocess.TimeoutExpired:
        run.exit_code = -1
        run.error = "E2E suite timed out after 5 min"
        print(f"  {_R}✗ E2E suite timed out after 5 min{_X}")
    except Exception as e:
        run.exit_code = -1
        run.error = str(e)
        print(f"  {_R}✗ E2E launch error: {e}{_X}")

    run.elapsed = time.time() - run.started
    state.e2e_runs.append(run)

    color = _G if run.failed == 0 and run.exit_code == 0 else _R
    print(f"\n  {color}{'✅' if run.failed == 0 else '❌'} Run #{run_no}: "
          f"{run.passed} passed · {run.skipped} skipped · {run.failed} failed  "
          f"({run.elapsed:.1f}s){_X}")
    return run


# ── Final report ──────────────────────────────────────────────────────────────

def final_report(state: State, args: argparse.Namespace, t0: float) -> int:
    elapsed = time.time() - t0
    runs    = state.e2e_runs
    hb_ok   = sum(1 for h in state.heartbeats if h.healthy)
    gw_ok   = sum(1 for g in state.gw_calls   if g.ok)
    total_p = sum(r.passed  for r in runs)
    total_f = sum(r.failed  for r in runs)
    total_s = sum(r.skipped for r in runs)
    failed_runs = [r for r in runs if r.failed > 0 or r.exit_code != 0]

    print(f"\n{'═' * W}")
    print(f"  {_B}AI Asset Management — 8-Hour E2E Final Report{_X}")
    print(f"  Backend  : {BASE_URL}")
    print(f"  Duration : {_fmt(elapsed)}")
    print(f"{'═' * W}")
    print(f"\n  E2E Suite runs: {len(runs)}")
    print(f"  Total checks  : {_G}{total_p} passed{_X}  "
          f"{_Y}{total_s} skipped{_X}  "
          f"{(_R if total_f else _G)}{total_f} failed{_X}")

    if runs:
        best  = min(runs, key=lambda r: r.failed)
        worst = max(runs, key=lambda r: r.failed)
        avg_t = sum(r.elapsed for r in runs) / len(runs)
        print(f"  Best run      : Run #{best.run_no}  ({best.passed}✅ {best.failed}❌)")
        print(f"  Worst run     : Run #{worst.run_no} ({worst.passed}✅ {worst.failed}❌)")
        print(f"  Avg duration  : {avg_t:.1f}s per E2E pass")

    print(f"\n  Health pings  : {hb_ok}/{len(state.heartbeats)} OK")
    if state.gw_calls:
        print(f"  Gateway calls : {gw_ok}/{len(state.gw_calls)} OK")

    if failed_runs:
        print(f"\n  {_R}Runs with failures:{_X}")
        for r in failed_runs:
            print(f"    Run #{r.run_no}: {r.passed}✅ {r.failed}❌  {r.error or ''}")

    print(f"\n{'═' * W}")
    overall_ok = total_f == 0 and all(r.exit_code == 0 for r in runs)
    if overall_ok:
        print(f"  {_G}{_B}OVERALL: PASS — no failures across all runs{_X}")
    else:
        print(f"  {_R}{_B}OVERALL: FAIL — {total_f} check failure(s) across {len(failed_runs)} run(s){_X}")
    print(f"{'═' * W}\n")

    return 0 if overall_ok else 1


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="8-hour continuous E2E test runner for AI Asset Management"
    )
    p.add_argument("--hours",        type=float, default=8.0,
                   help="Total run duration in hours (default: 8)")
    p.add_argument("--e2e-interval", type=int,   default=30,
                   help="Minutes between full E2E suite runs (default: 30)")
    p.add_argument("--heartbeat",    type=int,   default=60,
                   help="Seconds between health pings (default: 60)")
    p.add_argument("--gk",           default="",
                   help="API key for gateway traffic (gk-…). Omit to skip gateway calls.")
    p.add_argument("--gw-interval",  type=int,   default=30,
                   help="Seconds between gateway calls when --gk provided (default: 30)")
    p.add_argument("--strict",       action="store_true",
                   help="Pass --strict to E2E suite (skips count as failures)")
    p.add_argument("--base-url",     default=None)
    p.add_argument("--admin-email",  default=None)
    p.add_argument("--admin-password", default=None)
    return p.parse_args()


def main() -> None:
    global BASE_URL, PLATFORM_ADMIN_EMAIL, PLATFORM_ADMIN_PASSWORD

    args = parse_args()
    if args.base_url:     BASE_URL                = args.base_url.rstrip("/")
    if args.admin_email:  PLATFORM_ADMIN_EMAIL    = args.admin_email
    if args.admin_password: PLATFORM_ADMIN_PASSWORD = args.admin_password

    if not PLATFORM_ADMIN_PASSWORD:
        print(f"{_R}Error: PLATFORM_ADMIN_PASSWORD not set.{_X}")
        print("  Set the env var or pass --admin-password.")
        sys.exit(1)

    t0       = time.time()
    end_time = t0 + args.hours * 3600
    args._end_time = end_time   # shared with run_e2e for ETA display

    e2e_interval_s  = args.e2e_interval * 60
    heartbeat_s     = args.heartbeat
    gw_interval_s   = args.gw_interval
    total_runs_est  = max(1, int(args.hours * 60 / args.e2e_interval))

    print(f"\n{'═' * W}")
    print(f"  {_B}AI Asset Management — Continuous 8-Hour E2E Test{_X}")
    print(f"  Backend   : {BASE_URL}")
    print(f"  Duration  : {args.hours:.1f}h  (~{total_runs_est} E2E runs)")
    print(f"  E2E every : {args.e2e_interval} min  |  Heartbeat: {heartbeat_s}s")
    if args.gk:
        print(f"  Gateway   : enabled  (interval: {gw_interval_s}s)")
    if args.strict:
        print(f"  Mode      : strict")
    print(f"{'═' * W}")

    state   = State()
    run_no  = 0

    _ensure_token(state)

    try:
        while time.time() < end_time:
            # ── E2E run ───────────────────────────────────────────────────────
            run_no += 1
            run_e2e(state, args, run_no)
            _ensure_token(state)
            _header(state, args, end_time)

            # ── Heartbeat / soak phase until next E2E ─────────────────────────
            next_e2e = time.time() + e2e_interval_s
            last_hb  = 0.0
            last_gw  = 0.0

            print(f"\n[{_ts()}] Heartbeat phase — next E2E in {args.e2e_interval} min "
                  f"(or at end of test)\n")

            while time.time() < min(next_e2e, end_time):
                now = time.time()

                if now - last_hb >= heartbeat_s:
                    _ensure_token(state)
                    run_heartbeat(state)
                    last_hb = now

                if args.gk and now - last_gw >= gw_interval_s:
                    run_gw_call(state, args.gk)
                    last_gw = now

                # Sleep in short slices so we can react to end_time
                time.sleep(min(5, max(0, min(next_e2e, end_time) - time.time())))

    except KeyboardInterrupt:
        print(f"\n\n[{_ts()}] {_Y}Interrupted by user — generating final report…{_X}")

    sys.exit(final_report(state, args, t0))


if __name__ == "__main__":
    main()
