#!/usr/bin/env python3
"""
Collector-style OTLP smoke test for ObserveAgents.

Posts an OTLP/HTTP protobuf ExportTraceServiceRequest to /otel/v1/traces the
same way an OpenTelemetry Collector's otlp_http exporter does — once
uncompressed, and once gzip-compressed with Content-Encoding: gzip (the
Collector default). Both should return HTTP 202.

Usage:
    python scripts/collector_smoke_otlp.py --url https://app.observeagents.ai --key gk-XXXX
    # or via env:
    OA_URL=http://localhost:8000 OA_KEY=gk-XXXX python scripts/collector_smoke_otlp.py

Requires: opentelemetry-proto, requests (or falls back to urllib).
Traces only — this never sends metrics/logs.
"""
from __future__ import annotations

import argparse
import gzip
import os
import sys
import time
import uuid

try:
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
    from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
except ImportError:
    sys.exit("Missing dependency: pip install opentelemetry-proto")

import urllib.error
import urllib.request


def _kv(key: str, value) -> KeyValue:
    if isinstance(value, bool):
        return KeyValue(key=key, value=AnyValue(bool_value=value))
    if isinstance(value, int):
        return KeyValue(key=key, value=AnyValue(int_value=value))
    return KeyValue(key=key, value=AnyValue(string_value=str(value)))


def build_request() -> bytes:
    """A minimal but realistic production agent trace (one session, 3 spans)."""
    now = time.time_ns()
    session = uuid.uuid4().hex
    trace_id = uuid.uuid4().bytes

    req = ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    rs.resource.attributes.extend([
        _kv("service.name", "collector-smoke-agent"),
        _kv("deployment.environment", "production"),
        _kv("team", "smoke-test"),
    ])
    ss = rs.scope_spans.add()
    ss.scope.name = "collector-smoke"

    def span(name: str, attrs: dict):
        s = ss.spans.add()
        s.trace_id = trace_id
        s.span_id = uuid.uuid4().bytes[:8]
        s.name = name
        s.kind = 3
        s.start_time_unix_nano = now
        s.end_time_unix_nano = now + 200_000_000
        s.attributes.extend([_kv(k, v) for k, v in attrs.items()])

    span("gen_ai.request", {
        "session.id": session,
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": "claude-sonnet-5",
    })
    span("db.query", {"session.id": session, "db.system": "postgresql", "db.name": "tickets"})
    span("mcp.call", {"session.id": session, "mcp.method.name": "tools/call",
                      "gen_ai.tool.name": "jira_search"})
    return req.SerializeToString()


def post(endpoint: str, key: str, raw: bytes, gzip_body: bool) -> tuple[int, str]:
    headers = {
        "Content-Type": "application/x-protobuf",
        "Authorization": f"Bearer {key}",
    }
    data = raw
    if gzip_body:
        data = gzip.compress(raw)
        headers["Content-Encoding"] = "gzip"
    request = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        return 0, f"connection error: {exc.reason}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=os.environ.get("OA_URL", "http://localhost:8000"),
                    help="Base URL, e.g. https://app.observeagents.ai (no trailing /otel)")
    ap.add_argument("--key", default=os.environ.get("OA_KEY", ""),
                    help="Bearer credential — a gk-... API key or a JWT")
    args = ap.parse_args()

    if not args.key:
        return int(bool(sys.stderr.write("error: pass --key or set OA_KEY\n"))) or 2

    endpoint = args.url.rstrip("/") + "/otel/v1/traces"
    print(f"POST {endpoint}  (OTLP protobuf, 3 spans each)\n")

    ok = True
    for label, gz in (("uncompressed", False), ("gzip (Collector default)", True)):
        raw = build_request()  # fresh trace ids per post so neither dedups the other
        status, body = post(endpoint, args.key, raw, gz)
        verdict = "OK" if status == 202 else "FAIL"
        if status != 202:
            ok = False
        print(f"  [{verdict}] {label:26s} -> HTTP {status}")
        print(f"           {body[:200]}")
    print()
    if ok:
        print("Both requests accepted (202). Open Runtime to see the "
              "'collector-smoke-agent' session.")
        return 0
    print("At least one request failed — see the status/body above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
