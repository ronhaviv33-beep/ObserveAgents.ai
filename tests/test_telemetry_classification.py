"""
Unit tests for app/telemetry_classification.py — the pure span-classification
rubric. No DB, no app boot: classify_span / merge_classification_counts /
detect_candidate_keys are pure functions over attribute dicts.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from app.telemetry_classification import (
    CONF_HIGH,
    CONF_LOW,
    CONF_MEDIUM,
    IDENTITY_DECLARED,
    IDENTITY_FALLBACK,
    IDENTITY_SERVICE,
    MISSING_ENVIRONMENT,
    MISSING_GENAI_MODEL,
    MISSING_GENAI_PROVIDER,
    MISSING_IDENTITY,
    MISSING_MCP_SERVER,
    STATUS_FULL,
    STATUS_PARTIAL,
    STATUS_UNCLASSIFIED,
    SpanClassification,
    classify_span,
    detect_candidate_keys,
    merge_classification_counts,
)

_PROD_RESOURCE = {"service.name": "customer-support-agent", "deployment.environment": "production"}


# ── Scenario 1: perfect GenAI span → fully classified, high confidence ────────

def test_perfect_genai_span_full_high():
    cls = classify_span(
        {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "anthropic",
            "gen_ai.request.model": "claude-sonnet-5",
            "gen_ai.usage.input_tokens": 10,
            "gen_ai.usage.output_tokens": 5,
        },
        _PROD_RESOURCE,
        identity_tier=IDENTITY_SERVICE,
    )
    assert cls.status == STATUS_FULL
    assert cls.confidence == CONF_HIGH
    assert cls.missing == []
    assert cls.tiers["genai_model"] == "standard"
    assert cls.tiers["environment"] == "standard"
    assert cls.candidate_keys == []


def test_perfect_non_genai_span_full_high():
    """A plain DB span with identity + environment is complete for its kind —
    GenAI/tool signals are not 'missing' on a span that isn't GenAI/tool."""
    cls = classify_span(
        {"db.system": "postgresql"},
        _PROD_RESOURCE,
        identity_tier=IDENTITY_SERVICE,
    )
    assert cls.status == STATUS_FULL
    assert cls.confidence == CONF_HIGH
    assert cls.missing == []


# ── Scenario 2: service.name only → partially classified ─────────────────────

def test_service_only_missing_environment_partial():
    cls = classify_span(
        {"gen_ai.request.model": "m", "gen_ai.provider.name": "openai"},
        {"service.name": "svc"},
        identity_tier=IDENTITY_SERVICE,
    )
    assert cls.status == STATUS_PARTIAL
    assert cls.missing == [MISSING_ENVIRONMENT]
    assert cls.confidence == CONF_MEDIUM


# ── Scenario 3: no identity → unclassified, low confidence ───────────────────

def test_fallback_identity_unclassified_low():
    cls = classify_span(
        {"http.url": "https://api.example.com"},
        {},
        identity_tier=IDENTITY_FALLBACK,
    )
    assert cls.status == STATUS_UNCLASSIFIED
    assert cls.confidence == CONF_LOW
    assert MISSING_IDENTITY in cls.missing
    assert MISSING_ENVIRONMENT in cls.missing


# ── Scenario 4: custom model field → not classified, surfaced as candidate ───

def test_custom_model_key_partial_with_candidate():
    cls = classify_span(
        {"gen_ai.operation.name": "chat", "mycompany.llm.model": "acme-1"},
        _PROD_RESOURCE,
        identity_tier=IDENTITY_SERVICE,
    )
    # GenAI span (gen_ai.operation.name) with no recognized model/provider key
    assert cls.status == STATUS_PARTIAL
    assert MISSING_GENAI_MODEL in cls.missing
    assert MISSING_GENAI_PROVIDER in cls.missing
    assert cls.confidence == CONF_LOW  # GenAI without model
    assert "mycompany.llm.model" in cls.candidate_keys


# ── Scenario 5: MCP activity without server name → detected, low confidence ──

def test_mcp_method_without_server_low_confidence():
    cls = classify_span(
        {"rpc.method": "tools/call", "gen_ai.tool.name": "get_weather"},
        _PROD_RESOURCE,
        identity_tier=IDENTITY_SERVICE,
    )
    assert cls.status == STATUS_PARTIAL
    assert MISSING_MCP_SERVER in cls.missing
    assert cls.confidence == CONF_LOW
    assert cls.tiers["mcp_method"] == "fallback"
    assert cls.tiers["tool_name"] == "standard"


def test_mcp_with_server_is_complete():
    cls = classify_span(
        {
            "mcp.method.name": "tools/call",
            "mcp.server.name": "crm-mcp",
            "gen_ai.tool.name": "lookup",
        },
        _PROD_RESOURCE,
        identity_tier=IDENTITY_SERVICE,
    )
    assert cls.status == STATUS_FULL
    assert cls.confidence == CONF_HIGH


# ── Fallback-tier signals cap confidence at medium ────────────────────────────

def test_fallback_tier_signals_yield_medium():
    cls = classify_span(
        {"llm.model": "m", "llm.provider": "acme"},
        {"service.name": "svc", "env": "staging"},
        identity_tier=IDENTITY_SERVICE,
    )
    assert cls.status == STATUS_FULL
    assert cls.confidence == CONF_MEDIUM
    assert cls.tiers["genai_model"] == "fallback"
    assert cls.tiers["environment"] == "fallback"


def test_mapped_keys_yield_medium():
    cls = classify_span(
        {"gen_ai.request.model": "m", "gen_ai.provider.name": "acme"},
        _PROD_RESOURCE,
        identity_tier=IDENTITY_SERVICE,
        mapped_keys=frozenset({"gen_ai.request.model"}),
    )
    assert cls.status == STATUS_FULL
    assert cls.confidence == CONF_MEDIUM
    assert cls.tiers["genai_model"] == "mapped"


# ── Candidate-key detection ───────────────────────────────────────────────────

def test_detect_candidate_keys_conservative():
    keys = detect_candidate_keys(
        {
            "mycompany.llm.model": "x",        # candidate (contains "model")
            "tool_used": "y",                  # candidate (contains "tool")
            "acme.request.id": "z",            # not signal-ish → skipped
            "http.status_code": 200,           # known namespace → skipped
            "gen_ai.request.model": "m",       # known namespace → skipped
            "team": "core",                    # known bare key → skipped
        },
        {},
    )
    assert "mycompany.llm.model" in keys
    assert "tool_used" in keys
    assert "acme.request.id" not in keys
    assert "http.status_code" not in keys
    assert "gen_ai.request.model" not in keys
    assert "team" not in keys


def test_candidate_keys_only_scanned_when_something_missing():
    cls = classify_span(
        {
            "gen_ai.request.model": "m",
            "gen_ai.provider.name": "anthropic",
            "mycompany.llm.model": "x",
        },
        _PROD_RESOURCE,
        identity_tier=IDENTITY_DECLARED,
    )
    # nothing missing → clean spans pay zero for candidate detection
    assert cls.status == STATUS_FULL
    assert cls.candidate_keys == []


# ── Asset rollup: merge_classification_counts ─────────────────────────────────

def test_merge_counts_from_empty():
    counts_json, status, score = merge_classification_counts(
        None, {"full": 10, "partial": 0, "unclassified": 0})
    assert json.loads(counts_json) == {"full": 10, "partial": 0, "unclassified": 0}
    assert status == STATUS_FULL
    assert score == 100.0


def test_merge_counts_accumulates_and_is_order_independent():
    j1, _, _ = merge_classification_counts(None, {"full": 5})
    j2, status, score = merge_classification_counts(j1, {"partial": 5})
    assert json.loads(j2) == {"full": 5, "partial": 5, "unclassified": 0}
    assert status == STATUS_PARTIAL
    assert score == 80.0  # (5*1.0 + 5*0.6) / 10 * 100

    # reversed arrival order → identical result
    k1, _, _ = merge_classification_counts(None, {"partial": 5})
    k2, status2, score2 = merge_classification_counts(k1, {"full": 5})
    assert json.loads(k2) == json.loads(j2)
    assert (status2, score2) == (status, score)


def test_merge_counts_all_unclassified():
    _, status, score = merge_classification_counts(None, {"unclassified": 4})
    assert status == STATUS_UNCLASSIFIED
    assert score == 20.0


def test_merge_counts_garbage_existing_json_ignored():
    counts_json, status, score = merge_classification_counts(
        "not-json", {"full": 2})
    assert json.loads(counts_json) == {"full": 2, "partial": 0, "unclassified": 0}
    assert status == STATUS_FULL


def test_counts_key_property():
    assert SpanClassification(STATUS_FULL, CONF_HIGH).counts_key == "full"
    assert SpanClassification(STATUS_PARTIAL, CONF_MEDIUM).counts_key == "partial"
    assert SpanClassification(STATUS_UNCLASSIFIED, CONF_LOW).counts_key == "unclassified"
