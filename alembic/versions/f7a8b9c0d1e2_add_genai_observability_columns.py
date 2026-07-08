"""feat: add OTel GenAI SemConv scalar columns and query indexes

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-08

Promotes safe GenAI SemConv metadata (operation, provider, models, token
counts, finish reasons, streaming flag, time-to-first-chunk) from
attributes_json to nullable scalar columns on otel_spans and
provenance_events, plus non-unique composite indexes for the hot GenAI
queries. Purely additive: no backfill, existing rows stay NULL, no raw
prompt/response/tool content is involved.
"""
from alembic import op
import sqlalchemy as sa

revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None

_OTEL_SPANS_COLUMNS = [
    sa.Column('gen_ai_operation_name', sa.String(64), nullable=True),
    sa.Column('gen_ai_provider_name', sa.String(128), nullable=True),
    sa.Column('gen_ai_request_model', sa.String(255), nullable=True),
    sa.Column('gen_ai_response_model', sa.String(255), nullable=True),
    sa.Column('gen_ai_input_tokens', sa.Integer(), nullable=True),
    sa.Column('gen_ai_output_tokens', sa.Integer(), nullable=True),
    sa.Column('gen_ai_reasoning_output_tokens', sa.Integer(), nullable=True),
    sa.Column('gen_ai_cache_read_input_tokens', sa.Integer(), nullable=True),
    sa.Column('gen_ai_cache_creation_input_tokens', sa.Integer(), nullable=True),
    sa.Column('gen_ai_finish_reasons_json', sa.Text(), nullable=True),
    sa.Column('gen_ai_request_stream', sa.Boolean(), nullable=True),
    sa.Column('gen_ai_time_to_first_chunk_ms', sa.Integer(), nullable=True),
]

_PROVENANCE_EVENTS_COLUMNS = [
    sa.Column('gen_ai_provider_name', sa.String(128), nullable=True),
    sa.Column('gen_ai_request_model', sa.String(255), nullable=True),
    sa.Column('gen_ai_response_model', sa.String(255), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('finish_reasons_json', sa.Text(), nullable=True),
    sa.Column('request_stream', sa.Boolean(), nullable=True),
    sa.Column('time_to_first_chunk_ms', sa.Integer(), nullable=True),
]

_INDEXES = [
    ('ix_otel_spans_org_trace_start', 'otel_spans',
     ['organization_id', 'trace_id', 'start_time']),
    ('ix_otel_spans_org_genai_op_start', 'otel_spans',
     ['organization_id', 'gen_ai_operation_name', 'start_time']),
    ('ix_otel_spans_org_genai_provider_model_start', 'otel_spans',
     ['organization_id', 'gen_ai_provider_name', 'gen_ai_request_model', 'start_time']),
    ('ix_provenance_events_org_event_target_ts', 'provenance_events',
     ['organization_id', 'event_type', 'target_type', 'target_name', 'timestamp']),
    ('ix_provenance_events_org_source_event_ts', 'provenance_events',
     ['organization_id', 'source_name', 'event_type', 'timestamp']),
    ('ix_provenance_events_org_genai_provider_model_ts', 'provenance_events',
     ['organization_id', 'gen_ai_provider_name', 'gen_ai_request_model', 'timestamp']),
    ('ix_asset_findings_org_asset_status_sev_cat', 'asset_findings',
     ['organization_id', 'asset_key', 'status', 'severity', 'category']),
    ('ix_asset_capabilities_org_asset_type_name_source', 'asset_capabilities',
     ['organization_id', 'asset_key', 'capability_type', 'capability_name', 'source']),
]


def upgrade() -> None:
    # Guarded: create_all()/ensure_model_columns() both run before Alembic on
    # startup and may already have added the columns and (on fresh DBs) the
    # model-declared indexes.
    inspector = sa.inspect(op.get_bind())

    def _add_column(table: str, col: sa.Column) -> None:
        if not inspector.has_table(table):
            return
        if col.name in {c['name'] for c in inspector.get_columns(table)}:
            return
        op.add_column(table, col)

    for col in _OTEL_SPANS_COLUMNS:
        _add_column('otel_spans', col)
    for col in _PROVENANCE_EVENTS_COLUMNS:
        _add_column('provenance_events', col)

    # Re-inspect: the inspector caches, and the index guard must see the
    # columns just added above.
    inspector = sa.inspect(op.get_bind())

    def _create_index(name: str, table: str, cols: list[str]) -> None:
        if not inspector.has_table(table):
            return
        if name in {ix['name'] for ix in inspector.get_indexes(table)}:
            return
        if not set(cols) <= {c['name'] for c in inspector.get_columns(table)}:
            return
        op.create_index(name, table, cols)

    for name, table, cols in _INDEXES:
        _create_index(name, table, cols)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    for name, table, _cols in reversed(_INDEXES):
        if inspector.has_table(table) and name in {ix['name'] for ix in inspector.get_indexes(table)}:
            op.drop_index(name, table_name=table)

    # batch_alter_table so drop_column works on SQLite.
    if inspector.has_table('provenance_events'):
        existing = {c['name'] for c in inspector.get_columns('provenance_events')}
        with op.batch_alter_table('provenance_events') as batch:
            for col in reversed(_PROVENANCE_EVENTS_COLUMNS):
                if col.name in existing:
                    batch.drop_column(col.name)
    if inspector.has_table('otel_spans'):
        existing = {c['name'] for c in inspector.get_columns('otel_spans')}
        with op.batch_alter_table('otel_spans') as batch:
            for col in reversed(_OTEL_SPANS_COLUMNS):
                if col.name in existing:
                    batch.drop_column(col.name)
