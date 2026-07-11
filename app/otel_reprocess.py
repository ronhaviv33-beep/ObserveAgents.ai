"""
Retroactive reclassification and re-extraction of stored OTel spans.

Two callers:
  - POST /intelligence/reclassify and the attribute-mapping save
    (PUT /settings/otel-attribute-mapping) run a FULL pass: apply the CURRENT
    org attribute mapping to in-memory copies of every stored span's
    attributes, re-run gen_ai scalar extraction + telemetry classification,
    update the matching ProvenanceEvent denormalized copies, and rebuild the
    OtelAsset classification rollups from scratch.
  - The startup backfill (app/startup.py backfill_span_classification) runs a
    NULL-only pass: classify pre-migration spans (classification_status IS
    NULL) without touching gen_ai scalars (those were always populated at
    ingest), merging counts additively (those spans were never counted).

Invariants:
  - Stored attributes_json / resource_attributes_json are NEVER modified —
    the mapping is applied to in-memory copies only, which also re-derives
    the lossy mapped-tier provenance (canonical key absent in storage +
    custom source key present ⇒ mapped).
  - OtelAsset counters are monotonic at ingest, so the full pass REPLACES
    them with recomputed values (merge_classification_counts(None, ...));
    the NULL-only pass merges additively.
  - ProvenanceEvent rows are UPDATED in place (no unique key on span_id —
    inserting would duplicate); rows with NULL span_id are skipped.
  - Identity is NOT re-keyed: identity_tier feeds classification only.
    OtelSpan.service_name, OtelAsset, AssetRegistry, findings, and
    relationships keep their ingest-time keys — renaming stored identities
    would orphan rows keyed by the old names. Pre-fix per-span
    observed-ai-system fragments therefore stay as-is (they age out).
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from app.genai_semconv import (
    extract_environment_tiered,
    extract_genai_scalar_fields,
    extract_provider,
)
from app.models import AgentRelationship, OtelAsset, OtelSpan, ProvenanceEvent
from app.otel_attribute_mapping import apply_attribute_mapping, load_org_attribute_mapping
from app.otel_normalizer import (
    _extract_model,
    _extract_tool_name,
    resolve_span_identity,
    resolve_trace_identities,
    upsert_otel_asset,
    _merge_json_array,
)
from app.relationship_resolver import ResolvedRelationship
from app.relationships import upsert_relationship
from app.telemetry_classification import classify_span, merge_classification_counts

_log = logging.getLogger("ai_asset_mgmt.otel_reprocess")

TRACE_COMMIT_CHUNK = 200        # commit every N traces (bounds transactions)
BACKFILL_SPAN_CAP = 100_000     # per-boot cap for the startup backfill

# OtelSpan column → extract_genai_scalar_fields key
_SCALAR_COLUMNS = {
    "gen_ai_operation_name": "operation_name",
    "gen_ai_provider_name": "provider_name",
    "gen_ai_request_model": "request_model",
    "gen_ai_response_model": "response_model",
    "gen_ai_input_tokens": "input_tokens",
    "gen_ai_output_tokens": "output_tokens",
    "gen_ai_reasoning_output_tokens": "reasoning_output_tokens",
    "gen_ai_cache_read_input_tokens": "cache_read_input_tokens",
    "gen_ai_cache_creation_input_tokens": "cache_creation_input_tokens",
    "gen_ai_finish_reasons_json": "finish_reasons_json",
    "gen_ai_request_stream": "request_stream",
    "gen_ai_time_to_first_chunk_ms": "time_to_first_chunk_ms",
}


def _parse_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


class _ServiceAcc:
    """Per-(service_name, environment) rollup accumulated over the pass."""

    def __init__(self) -> None:
        self.counts = {"full": 0, "partial": 0, "unclassified": 0}
        self.trace_ids: set[str] = set()
        self.span_count = 0
        self.candidate_keys: set[str] = set()
        self.models: set[str] = set()
        self.providers: set[str] = set()
        self.tools: set[str] = set()
        self.span_dts: list = []  # start_times, for the create-if-missing path


def reclassify_org_spans(
    db: Session,
    org_id: int,
    *,
    only_null: bool = False,
    skip_scalars: bool = False,
    span_cap: int | None = None,
) -> dict:
    """Reclassify (and, unless skip_scalars, re-extract) an org's stored spans.

    only_null=True processes only spans whose classification_status IS NULL
    (their full traces are still loaded — identity inheritance needs the
    siblings) and merges asset counters additively; the default full pass
    processes everything and rebuilds counters from scratch.

    Returns {"spans_seen", "spans_reclassified", "spans_rescored",
             "provenance_updated", "assets_rebuilt", "relationships_created",
             "capped": bool}.
    """
    mapping = load_org_attribute_mapping(db, org_id)

    q = db.query(OtelSpan).filter(OtelSpan.organization_id == org_id)
    if only_null:
        null_traces = (
            db.query(OtelSpan.trace_id)
            .filter(
                OtelSpan.organization_id == org_id,
                OtelSpan.classification_status.is_(None),
            )
            .distinct()
        )
        trace_ids = [t[0] for t in null_traces.all()]
        if not trace_ids:
            return {
                "spans_seen": 0, "spans_reclassified": 0, "spans_rescored": 0,
                "provenance_updated": 0, "assets_rebuilt": 0,
                "relationships_created": 0, "capped": False,
            }
        q = q.filter(OtelSpan.trace_id.in_(trace_ids))
    rows = q.order_by(OtelSpan.trace_id, OtelSpan.id).all()

    by_trace: dict[str, list[OtelSpan]] = defaultdict(list)
    for row in rows:
        by_trace[row.trace_id].append(row)

    spans_seen = 0
    spans_reclassified = 0
    spans_rescored = 0
    provenance_updated = 0
    relationships_created = 0
    capped = False

    # (service_name, environment) → rollup; identity → {model: span_count}
    service_accs: dict[tuple[str, str | None], _ServiceAcc] = defaultdict(_ServiceAcc)
    model_edges: dict[tuple[str, str], int] = defaultdict(int)

    traces_since_commit = 0
    for trace_id, trace_rows in by_trace.items():
        if span_cap is not None and spans_seen >= span_cap:
            capped = True
            break

        # In-memory parsed copies — stored JSON is never modified. The mapping
        # is applied per span; mapped canonical keys are exactly those absent
        # from storage, which re-derives the lossy TIER_MAPPED provenance.
        parsed: list[dict] = []
        span_mapped: list[frozenset[str]] = []
        for row in trace_rows:
            attrs = _parse_json(row.attributes_json)
            resource_attrs = _parse_json(row.resource_attributes_json)
            mapped = apply_attribute_mapping(attrs, resource_attrs, mapping) if mapping else frozenset()
            parsed.append({
                "attributes": attrs,
                "resource_attributes": resource_attrs,
                "trace_id": trace_id,
                "span_id": row.span_id,
            })
            span_mapped.append(mapped)

        trace_identity = resolve_trace_identities(parsed)

        for row, p, mapped_keys in zip(trace_rows, parsed, span_mapped):
            # NULL-only mode: siblings participate in pass 0 but are not touched.
            if only_null and row.classification_status is not None:
                continue
            spans_seen += 1
            attrs = p["attributes"]
            resource_attrs = p["resource_attributes"]

            agent_name, _display, _itype, identity_tier = resolve_span_identity(
                attrs, resource_attrs, trace_id, trace_identity
            )
            cls = classify_span(
                attrs, resource_attrs,
                identity_tier=identity_tier,
                mapped_keys=mapped_keys,
            )
            new_missing = json.dumps(cls.missing) if cls.missing else None
            if (
                row.classification_status != cls.status
                or row.classification_confidence != cls.confidence
                or row.classification_missing != new_missing
            ):
                row.classification_status = cls.status
                row.classification_confidence = cls.confidence
                row.classification_missing = new_missing
                spans_reclassified += 1

            if not skip_scalars:
                genai = extract_genai_scalar_fields(attrs)
                changed = False
                for col, key in _SCALAR_COLUMNS.items():
                    if getattr(row, col) != genai[key]:
                        setattr(row, col, genai[key])
                        changed = True
                if changed:
                    spans_rescored += 1
                    # Update the denormalized copies in place — ProvenanceEvent
                    # has no unique key on span_id, inserting would duplicate.
                    if row.span_id:
                        events = db.query(ProvenanceEvent).filter(
                            ProvenanceEvent.organization_id == org_id,
                            ProvenanceEvent.trace_id == trace_id,
                            ProvenanceEvent.span_id == row.span_id,
                        ).all()
                        for ev in events:
                            ev.gen_ai_provider_name = genai["provider_name"]
                            ev.gen_ai_request_model = genai["request_model"]
                            ev.gen_ai_response_model = genai["response_model"]
                            ev.input_tokens = genai["input_tokens"]
                            ev.output_tokens = genai["output_tokens"]
                            ev.finish_reasons_json = genai["finish_reasons_json"]
                            ev.request_stream = genai["request_stream"]
                            ev.time_to_first_chunk_ms = genai["time_to_first_chunk_ms"]
                            provenance_updated += 1

            # Rollup accumulation — keyed by the STORED service_name (no
            # identity re-keying) + the re-derived environment.
            environment = extract_environment_tiered(resource_attrs, attrs)[0]
            acc = service_accs[(row.service_name or "", environment)]
            acc.counts[cls.counts_key] += 1
            acc.span_count += 1
            acc.trace_ids.add(trace_id)
            if row.start_time is not None:
                acc.span_dts.append(row.start_time)
            acc.candidate_keys.update(cls.candidate_keys)
            model = _extract_model(attrs)
            if model:
                acc.models.add(model)
                model_edges[(agent_name, model)] += 1
            provider = extract_provider(attrs)
            if provider:
                acc.providers.add(str(provider).capitalize())
            tool = _extract_tool_name(attrs)
            if tool:
                acc.tools.add(tool)

        traces_since_commit += 1
        if traces_since_commit >= TRACE_COMMIT_CHUNK:
            db.commit()
            traces_since_commit = 0
    db.commit()

    # ── Asset rollup rebuild ──────────────────────────────────────────────────
    assets_rebuilt = 0
    for (service_name, environment), acc in service_accs.items():
        if not service_name:
            continue
        oa_q = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org_id,
            OtelAsset.service_name == service_name,
        )
        if environment is None:
            existing = oa_q.filter(OtelAsset.environment.is_(None)).first()
        else:
            existing = oa_q.filter(OtelAsset.environment == environment).first()
        if existing is None:
            # A newly-mapped environment must not split an existing asset:
            # fall back to the service's row under its stored environment.
            existing = db.query(OtelAsset).filter(
                OtelAsset.organization_id == org_id,
                OtelAsset.service_name == service_name,
            ).first()
        if existing is None:
            # No row at all (spans predate OtelAsset, or upsert failed at
            # ingest) — create one with the recomputed counts. Needs at least
            # one span timestamp; upsert_otel_asset no-ops without them.
            if acc.span_dts:
                upsert_otel_asset(
                    db=db, org_id=org_id, ai_asset_id=None,
                    service_name=service_name, agent_name=service_name,
                    environment=environment, resource_attrs={},
                    new_models=acc.models, new_providers=acc.providers,
                    new_tools=acc.tools, new_dependencies=set(),
                    trace_ids=acc.trace_ids,
                    span_dts=acc.span_dts,
                    class_counts=acc.counts,
                    candidate_keys=acc.candidate_keys,
                )
                assets_rebuilt += 1
            continue

        if only_null:
            # Legacy spans were never counted into the classification
            # counters — additive merge is exact here.
            counts_json, status, score = merge_classification_counts(
                existing.classification_counts_json, acc.counts
            )
            merged_keys = set(json.loads(existing.candidate_attr_keys_json or "[]"))
            merged_keys |= acc.candidate_keys
            existing.candidate_attr_keys_json = json.dumps(sorted(merged_keys)[:40])
        else:
            # Full pass saw every span — replace, never merge (ingest counters
            # are monotonic; merging would double-count).
            counts_json, status, score = merge_classification_counts(None, acc.counts)
            existing.candidate_attr_keys_json = (
                json.dumps(sorted(acc.candidate_keys)[:40]) if acc.candidate_keys else None
            )
            existing.span_count = acc.span_count
            existing.trace_count = len(acc.trace_ids)
        existing.classification_counts_json = counts_json
        existing.classification_status = status
        existing.confidence_score = score
        existing.models_json = _merge_json_array(existing.models_json, acc.models)
        existing.providers_json = _merge_json_array(existing.providers_json, acc.providers)
        existing.tools_json = _merge_json_array(existing.tools_json, acc.tools)
        assets_rebuilt += 1
    db.commit()

    # ── Missing uses_model relationships (e.g. models surfaced by a new
    #    mapping). Existence-checked first: existing edges are never touched,
    #    so request_count is not inflated and a second run is a no-op. ──────
    for (identity, model), count in model_edges.items():
        exists = db.query(AgentRelationship.id).filter(
            AgentRelationship.organization_id == org_id,
            AgentRelationship.source_agent_name == identity,
            AgentRelationship.target_type == "model",
            AgentRelationship.target_name == model,
            AgentRelationship.relationship_type == "uses_model",
        ).first()
        if exists:
            continue
        upsert_relationship(db, org_id, ResolvedRelationship(
            source_agent_name=identity,
            target_type="model",
            target_name=model,
            relationship_type="uses_model",
            evidence_source="otel_trace",
            confidence_score=0.90,
            metadata={"reprocessed": True, "span_count": count},
        ))
        relationships_created += 1
    db.commit()

    return {
        "spans_seen": spans_seen,
        "spans_reclassified": spans_reclassified,
        "spans_rescored": spans_rescored,
        "provenance_updated": provenance_updated,
        "assets_rebuilt": assets_rebuilt,
        "relationships_created": relationships_created,
        "capped": capped,
    }
