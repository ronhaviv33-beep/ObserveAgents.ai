import os, sys, time, random, argparse, textwrap
import schedule, requests
from openai import OpenAI

# ── Config ─────────────────────────────────────────────────────────────────────
GATEWAY_URL = os.environ.get("GATEWAY_URL",  "https://aifinops-backend.onrender.com/v1")
API_KEY     = os.environ.get("GATEWAY_KEY",  "gk-PkdKHCmt9F6SiLrI9rruHkTCBK-dz8n7SGelbl2zqMQ")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN",  "eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.eyJzdWIiOiAiMSIsICJlbWFpbCI6ICJhZG1pbkBhaWZpbm9wcy5sb2NhbCIsICJuYW1lIjogIkFkbWluIiwgInJvbGUiOiAiYWRtaW4iLCAidGVhbSI6ICJQbGF0Zm9ybSIsICJleHAiOiAxNzgwOTAyNzEyfQ.kKkuytDmhHhdmhQGCsJBwbgGoEte60tUp-d_vx3g0Gg")   # Bearer token — needed for --verify-alerts
TEAM        = os.environ.get("GUARD_TEAM",   "Developer")
BASE_URL    = GATEWAY_URL.removesuffix("/v1")      # https://aifinops-backend.onrender.com

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--hours",         type=float, default=8,     help="How long to run (default 8)")
parser.add_argument("--verify-alerts", action="store_true",       help="Query /security/alerts after each scenario")
ARGS = parser.parse_args()

RUN_HOURS = ARGS.hours
START_TIME = time.time()
END_TIME   = START_TIME + RUN_HOURS * 3600

client = OpenAI(api_key=API_KEY, base_url=GATEWAY_URL)

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def _ts():   return time.strftime("%H:%M:%S")
def _left():
    s = max(0, END_TIME - time.time())
    return f"{int(s//3600)}h {int((s%3600)//60)}m remaining"

# ── Core call ──────────────────────────────────────────────────────────────────
def call(agent: str, model: str, prompt: str, label: str = "task") -> int:
    """Send one request through the gateway. Returns total_tokens (0 on error)."""
    print(f"[{_ts()}] {label:<30} agent={agent}  model={model}")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            extra_headers={"X-Guard-Team": TEAM, "X-Guard-Agent": agent},
        )
        tokens = resp.usage.total_tokens
        snippet = resp.choices[0].message.content[:80].replace("\n", " ")
        print(f"  {GREEN}✓{RESET} {tokens} tokens | {snippet}…")
        return tokens
    except Exception as e:
        print(f"  {RED}✗{RESET} {e}")
        return 0

# ── Alert verifier ─────────────────────────────────────────────────────────────
def verify_alerts(scenario: str):
    """Query /security/alerts and print which types fired. Requires ADMIN_TOKEN."""
    if not ARGS.verify_alerts:
        return
    if not ADMIN_TOKEN:
        print(f"  {YELLOW}⚠ --verify-alerts set but ADMIN_TOKEN is empty — skipping check{RESET}")
        return
    try:
        r = requests.get(
            f"{BASE_URL}/security/alerts",
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
            timeout=10,
        )
        r.raise_for_status()
        alerts = r.json()
        if not alerts:
            print(f"  {CYAN}ℹ /security/alerts — no alerts yet (may need more traffic){RESET}")
            return
        print(f"  {BOLD}Alert check after [{scenario}]:{RESET}")
        for a in alerts:
            sev_color = RED if a["sev"] == "critical" else (YELLOW if a["sev"] == "warning" else CYAN)
            print(f"    {sev_color}[{a['sev'].upper():8}]{RESET} {a['type']:<35} {a['msg'][:60]}")
    except Exception as e:
        print(f"  {RED}✗ Alert check failed: {e}{RESET}")

# ── Normal tasks ───────────────────────────────────────────────────────────────
TASKS = [
    ("finance-analysis",  "gpt-4o-mini",      "Summarize the key risks in AI spending for a SaaS company in 3 bullet points."),
    ("code-review",       "gpt-4o-mini",      "Review this Python snippet and suggest improvements: def add(a,b): return a+b"),
    ("report-generation", "gpt-4o-mini",      "Write a 2-sentence executive summary for a Q2 cost optimization report."),
    ("data-extraction",   "gpt-4o-mini",      "Extract the key metrics from: 'Revenue was $2.3M, costs $1.1M, headcount 42.'"),
    ("policy-check",      "gpt-4o-mini",      "What are best practices for managing LLM API costs in a multi-team org?"),
    ("claude-analyst",    "claude-haiku-4-5", "In 3 bullet points, what are the top risks of unmonitored AI agents in enterprise?"),
    ("claude-writer",     "claude-haiku-4-5", "Write a 2-sentence summary: why do companies need an AI usage audit trail?"),
    ("claude-advisor",    "claude-haiku-4-5", "What KPIs should a FinOps team track for LLM cost management?"),
    ("claude-reviewer",   "claude-haiku-4-5", "Review this code for security issues: token = request.headers.get('token')"),
]

def run_normal_task():
    name, model, prompt = random.choice(TASKS)
    call(name, model, prompt, label=f"normal  [{_left()}]")

# ── Scenario: PII → sensitive_data_exposure alert ──────────────────────────────
def run_pii_task():
    """
    Triggers: sensitive_data_exposure (critical)
    Detection: Telemetry.sensitive=True rows exist for this org.
    """
    print(f"\n[{_ts()}] {RED}▶ PII scenario{RESET}  [{_left()}]")
    call("pii-tester", "gpt-4o-mini",
         "My SSN is 123-45-6789, can you help me fill out this form?",
         label="PII — SSN")
    call("pii-tester", "claude-haiku-4-5",
         "Process this payment: card 4111-1111-1111-1111 exp 12/26 CVV 123",
         label="PII — card")
    call("pii-tester", "gpt-4o-mini",
         "My password is S3cr3t! and my email is john.doe@internal.corp",
         label="PII — credentials")
    verify_alerts("PII")
    print()

# ── Scenario: loop → (client-side) runaway agent ──────────────────────────────
def run_loop_simulation():
    """
    Triggers: client-side loop detection (many rapid identical agents).
    No server alert type for this; visible in Alerts page on dashboard.
    """
    print(f"\n[{_ts()}] {YELLOW}▶ Loop simulation{RESET}  [{_left()}]")
    loop_prompts = [
        "Is this task done? Check status.",
        "Retry: is the report ready?",
        "Still waiting — check again.",
        "Poll: has the data been processed?",
        "Verify completion of previous step.",
        "Re-check: did the last action succeed?",
        "Loop iteration: confirm state.",
        "Agent heartbeat: still running?",
    ]
    for i, prompt in enumerate(loop_prompts):
        call("runaway-agent", "gpt-4o-mini", prompt, label=f"loop-{i+1}")
        time.sleep(2)
    verify_alerts("loop-simulation")
    print(f"  → Done. Check Alerts page.\n")

# ── Scenario: cost spike → cost_anomaly (client-side) ─────────────────────────
def run_cost_spike():
    """
    Triggers: client-side cost anomaly detection (gpt-4o burst).
    Also produces high-cost telemetry rows visible in audit table.
    """
    print(f"\n[{_ts()}] {YELLOW}▶ Cost spike  (gpt-4o × 3){RESET}  [{_left()}]")
    for prompt in [
        "Write a detailed 5-paragraph technical report on LLM cost optimization strategies.",
        "Analyze this dataset and produce a full risk assessment with recommendations.",
        "Generate a complete financial model for AI infrastructure ROI over 3 years.",
    ]:
        call("cost-spike-agent", "gpt-4o", prompt, label="spike")
        time.sleep(3)
    verify_alerts("cost-spike")
    print()

# ── Scenario: unapproved model ─────────────────────────────────────────────────
def run_unapproved_model():
    """
    Triggers: policy_block_spike if gpt-4o is blocked for this team.
    Otherwise produces a telemetry row with a non-default model.
    """
    call("shadow-agent", "gpt-4o",
         "Summarize AI governance best practices.",
         label=f"unapproved  [{_left()}]")

# ── Scenario: unknown model → pricing_estimated alert ─────────────────────────
UNKNOWN_MODELS = [
    "gpt-5-preview",       # not in pricing table → pricing_estimated=True
    "o3-pro",              # not in pricing table → pricing_estimated=True
    "claude-opus-5",       # not in pricing table → pricing_estimated=True
    "gemini-ultra-2",      # not in pricing table → pricing_estimated=True
]

def run_unknown_model():
    """
    Triggers: pricing_estimated=True on the telemetry row.
    The dashboard shows these with a ~ prefix and 'est.' badge.
    The server emits a WARNING log: 'Unknown model ... add to COST_PER_1M'.

    NOTE: This will likely get a 400/404 from the upstream provider since
    these model names don't exist — but the gateway still logs the attempt
    (blocked=True) and records pricing_estimated=True if cost is calculated
    before the block. The point is to confirm the flag works end-to-end.
    """
    model = random.choice(UNKNOWN_MODELS)
    print(f"\n[{_ts()}] {CYAN}▶ Unknown model: {model}{RESET}  [{_left()}]")
    call(
        "unknown-model-agent", model,
        "What is the capital of France?",
        label=f"unknown-model [{model}]",
    )

    # Also verify via /telemetry if we have an admin token
    if ARGS.verify_alerts and ADMIN_TOKEN:
        try:
            r = requests.get(
                f"{BASE_URL}/telemetry",
                headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
                timeout=10,
            )
            r.raise_for_status()
            rows = r.json()
            estimated = [row for row in rows if row.get("pricing_estimated")]
            if estimated:
                print(f"  {CYAN}ℹ pricing_estimated=True rows in telemetry: {len(estimated)}{RESET}")
                for row in estimated[:3]:
                    cost = row.get("cost_usd", 0)
                    print(f"    model={row['model']!r}  cost=~${cost:.6f}  agent={row['agent']}")
            else:
                print(f"  {YELLOW}⚠ No pricing_estimated=True rows found yet{RESET}")
        except Exception as e:
            print(f"  {RED}✗ Telemetry check failed: {e}{RESET}")
    print()

# ── Scenario: after-hours burst → unusual_after_hours_usage alert ──────────────
def run_after_hours_burst():
    """
    Triggers: unusual_after_hours_usage (info) — server detects >10 calls
    outside 07:00–20:00 UTC per agent within the last 7 days.

    This scenario fires 12 rapid calls from 'night-batch-agent'.
    If the server's current UTC hour is already outside 07:00–20:00 this
    will immediately contribute to the counter; otherwise it seeds the
    history so future runs tip it over the threshold.
    """
    print(f"\n[{_ts()}] {CYAN}▶ After-hours burst (12 calls × night-batch-agent){RESET}  [{_left()}]")
    batch_prompts = [
        "Summarize daily revenue for region EMEA.",
        "Generate nightly audit log digest.",
        "Run scheduled cost reconciliation for Q2.",
        "Export telemetry summary for the last 24h.",
        "Check model usage quota for all teams.",
        "Aggregate token spend by agent for yesterday.",
        "Produce overnight anomaly detection report.",
        "Validate budget rules are within thresholds.",
        "Sync cost data to reporting warehouse.",
        "Flag any policy violations from today's logs.",
        "Compute rolling 7-day cost trend.",
        "Generate executive cost dashboard snapshot.",
    ]
    for i, prompt in enumerate(batch_prompts):
        call("night-batch-agent", "gpt-4o-mini", prompt, label=f"after-hours-{i+1:02d}")
        time.sleep(1)
    verify_alerts("after-hours-burst")
    print(f"  → {len(batch_prompts)} calls sent. "
          f"Alert fires when >10 calls outside 07:00–20:00 UTC in last 7d.\n")

# ── Scenario: high-token prompt → high_token_prompt alert ─────────────────────
def run_high_token_prompt():
    """
    Triggers: high_token_prompt (warning) — server detects total_tokens > 30,000.
    We approximate by sending a very large prompt. Real 30K+ requires a big
    document; this sends the largest prompt the API will accept within limits.
    """
    print(f"\n[{_ts()}] {YELLOW}▶ High-token prompt{RESET}  [{_left()}]")
    # Generate a large prompt (~8K chars, pushing token count high)
    big_text = textwrap.dedent("""
        You are a financial analyst. Below is a very long transcript of a board meeting
        discussing AI cost optimisation. Please summarise the key decisions and action items.

    """) + ("The CFO raised concerns about uncontrolled AI spend across business units. " * 300)
    call("large-context-agent", "gpt-4o-mini", big_text.strip(), label="high-token")
    verify_alerts("high-token-prompt")
    print()

# ── Schedule ───────────────────────────────────────────────────────────────────
schedule.every(3).minutes.do(run_normal_task)
schedule.every(20).minutes.do(run_pii_task)
schedule.every(30).minutes.do(run_loop_simulation)
schedule.every(45).minutes.do(run_cost_spike)
schedule.every(25).minutes.do(run_unapproved_model)
schedule.every(15).minutes.do(run_unknown_model)
schedule.every(40).minutes.do(run_after_hours_burst)
schedule.every(60).minutes.do(run_high_token_prompt)

# ── Main ───────────────────────────────────────────────────────────────────────
print("=" * 64)
print(f"  {BOLD}AIFinOps Guard — test agent{RESET}")
print(f"  Gateway:  {GATEWAY_URL}")
print(f"  Team:     {TEAM}")
print(f"  Started:  {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  Stops:    {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(END_TIME))}")
print(f"  Runtime:  {RUN_HOURS}h")
print(f"  Verify:   {'yes (ADMIN_TOKEN set)' if ADMIN_TOKEN else 'no (set ADMIN_TOKEN env var)'}")
print("=" * 64)
print()
print("Scenarios and the alerts they target:")
print("  run_pii_task          → sensitive_data_exposure (critical)")
print("  run_high_token_prompt → high_token_prompt (warning)")
print("  run_cost_spike        → cost_anomaly / gpt-4o burst (client-side)")
print("  run_after_hours_burst → unusual_after_hours_usage (info, >10 calls outside 07-20 UTC)")
print("  run_unknown_model     → pricing_estimated=True flag on telemetry row")
print("  run_unapproved_model  → policy_block_spike if team has gpt-4o blocked")
print("  run_loop_simulation   → runaway agent pattern (client-side detection)")
print()

# Fire one of each immediately at start
print(f"{BOLD}── Initial burst ──────────────────────────────────────────{RESET}")
run_normal_task();        time.sleep(3)
run_pii_task();           time.sleep(3)
run_unknown_model();      time.sleep(3)
run_after_hours_burst();  time.sleep(3)
run_high_token_prompt();  time.sleep(3)
run_loop_simulation();    time.sleep(3)
run_cost_spike()
print(f"{BOLD}── Initial burst complete — entering scheduled loop ───────{RESET}\n")

while time.time() < END_TIME:
    schedule.run_pending()
    time.sleep(10)

print()
print("=" * 64)
print(f"  {GREEN}✓ {RUN_HOURS}h run complete — {time.strftime('%H:%M:%S')}{RESET}")
print(f"  Check the dashboard for the full telemetry and alerts.")
print("=" * 64)
