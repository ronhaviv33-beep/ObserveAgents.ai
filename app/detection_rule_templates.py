"""
Approved detection-rule templates for admin-managed custom rules.

Safety model: a custom rule is (template_type, config_json). template_type
must be one of the approved templates below; config_json is validated against
that template's parameter spec (typed, bounded scalars and short string lists
only). Rules never carry code — evaluation maps template_type to the fixed
functions in this module. This is deliberate: no DSL, no eval, no arbitrary
logic, so a compromised admin account cannot turn rules into an execution
vector.

Each evaluator receives the normalized event dict (TelemetryEvent field
names) and the rule's validated config, and returns a reason string when the
rule fires, else None. Severity → weight mapping lives here too so built-in
overrides and custom rules score consistently.
"""
from __future__ import annotations

import json

SEVERITY_WEIGHT = {"low": 10, "medium": 15, "high": 25}
VALID_SEVERITIES = set(SEVERITY_WEIGHT)

_MAX_LIST_ITEMS = 50
_MAX_STR_LEN = 128


def _num(config: dict, key: str, lo: float, hi: float) -> tuple[float | None, str | None]:
    v = config.get(key)
    if v is None:
        return None, f"{key} is required"
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None, f"{key} must be a number"
    if not (lo <= float(v) <= hi):
        return None, f"{key} must be between {lo} and {hi}"
    return float(v), None


def _str_list(config: dict, key: str) -> tuple[list[str] | None, str | None]:
    v = config.get(key)
    if v is None:
        return None, f"{key} is required"
    if not isinstance(v, list) or not v:
        return None, f"{key} must be a non-empty list of strings"
    if len(v) > _MAX_LIST_ITEMS:
        return None, f"{key} may have at most {_MAX_LIST_ITEMS} items"
    out = []
    for item in v:
        if not isinstance(item, str) or not item.strip() or len(item) > _MAX_STR_LEN:
            return None, f"{key} items must be non-empty strings (max {_MAX_STR_LEN} chars)"
        out.append(item.strip().lower())
    return out, None


# ── Evaluators (event: normalized dict; config: validated) ───────────────────

def _eval_cost_threshold(event: dict, config: dict) -> str | None:
    cost = event.get("cost_usd")
    if cost is not None and cost > config["cost_usd"]:
        return f"Cost ${cost:.2f} exceeds ${config['cost_usd']:.2f} rule threshold"
    return None


def _eval_latency_threshold(event: dict, config: dict) -> str | None:
    latency = event.get("latency_ms")
    if latency is not None and latency > config["latency_ms"]:
        return f"Latency {latency:.0f}ms exceeds {config['latency_ms']:.0f}ms rule threshold"
    return None


def _eval_token_threshold(event: dict, config: dict) -> str | None:
    tokens = event.get("total_tokens")
    if tokens is not None and tokens > config["total_tokens"]:
        return f"Token usage {tokens} exceeds {config['total_tokens']:.0f} rule threshold"
    return None


def _eval_environment_condition(event: dict, config: dict) -> str | None:
    env = (event.get("environment") or "").strip().lower()
    if env and env in config["environments"]:
        return f"Activity in watched environment '{env}'"
    return None


def _eval_provider_model_condition(event: dict, config: dict) -> str | None:
    model = (event.get("model") or "").strip().lower()
    provider = (event.get("provider") or "").strip().lower()
    watched = config["values"]
    if (model and model in watched) or (provider and provider in watched):
        return f"Watched provider/model '{model or provider}' used"
    return None


def _eval_tool_condition(event: dict, config: dict) -> str | None:
    tool = (event.get("tool_name") or "").strip().lower()
    if tool and tool in config["tools"]:
        return f"Watched tool '{tool}' called"
    return None


# ── Template registry ─────────────────────────────────────────────────────────

TEMPLATES: dict[str, dict] = {
    "cost_threshold": {
        "label": "Cost per event exceeds threshold",
        "category": "cost",
        "params": [{"key": "cost_usd", "type": "number", "label": "Max cost per event (USD)", "min": 0.001, "max": 10000}],
        "validate": lambda c: _num(c, "cost_usd", 0.001, 10000)[1],
        "evaluate": _eval_cost_threshold,
    },
    "latency_threshold": {
        "label": "Latency exceeds threshold",
        "category": "operations",
        "params": [{"key": "latency_ms", "type": "number", "label": "Max latency (ms)", "min": 1, "max": 3_600_000}],
        "validate": lambda c: _num(c, "latency_ms", 1, 3_600_000)[1],
        "evaluate": _eval_latency_threshold,
    },
    "token_usage_threshold": {
        "label": "Token usage exceeds threshold",
        "category": "cost",
        "params": [{"key": "total_tokens", "type": "number", "label": "Max total tokens per event", "min": 1, "max": 100_000_000}],
        "validate": lambda c: _num(c, "total_tokens", 1, 100_000_000)[1],
        "evaluate": _eval_token_threshold,
    },
    "environment_condition": {
        "label": "Activity in watched environment",
        "category": "governance",
        "params": [{"key": "environments", "type": "string_list", "label": "Watched environments"}],
        "validate": lambda c: _str_list(c, "environments")[1],
        "evaluate": _eval_environment_condition,
    },
    "provider_model_condition": {
        "label": "Watched provider or model used",
        "category": "security",
        "params": [{"key": "values", "type": "string_list", "label": "Provider/model names to watch"}],
        "validate": lambda c: _str_list(c, "values")[1],
        "evaluate": _eval_provider_model_condition,
    },
    "tool_condition": {
        "label": "Watched tool called",
        "category": "security",
        "params": [{"key": "tools", "type": "string_list", "label": "Tool names to watch"}],
        "validate": lambda c: _str_list(c, "tools")[1],
        "evaluate": _eval_tool_condition,
    },
}


def validate_config(template_type: str, config: dict) -> str | None:
    """Return an error string, or None when (template_type, config) is valid."""
    tpl = TEMPLATES.get(template_type)
    if tpl is None:
        return f"Unknown template_type '{template_type}' — allowed: {sorted(TEMPLATES)}"
    if not isinstance(config, dict):
        return "config must be an object"
    return tpl["validate"](config)


def normalize_config(template_type: str, config: dict) -> dict:
    """Return the canonical config (numbers coerced, lists lowercased)."""
    tpl = TEMPLATES[template_type]
    out = {}
    for p in tpl["params"]:
        if p["type"] == "number":
            out[p["key"]] = float(config[p["key"]])
        else:
            out[p["key"]], _ = _str_list(config, p["key"])
    return out


def evaluate_custom_rule(template_type: str, config_json: str | None, event: dict) -> str | None:
    """Evaluate one custom rule against one normalized event. Fail-safe:
    unknown template or bad stored config never raises, never fires."""
    tpl = TEMPLATES.get(template_type)
    if tpl is None or not config_json:
        return None
    try:
        config = json.loads(config_json)
        if validate_config(template_type, config) is not None:
            return None
        return tpl["evaluate"](event, normalize_config(template_type, config))
    except Exception:
        return None
