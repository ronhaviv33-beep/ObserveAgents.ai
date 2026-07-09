"""feat: add notification_channels and notification_deliveries tables

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-07-09

Detection Rules webhook notifications (R5). notification_channels stores
per-org webhook targets with the URL Fernet-encrypted at rest;
notification_deliveries logs one row per delivery attempt and doubles as
the cooldown ledger. Application-level dedup — no unique indexes.
"""
from alembic import op
import sqlalchemy as sa

revision = 'a8b9c0d1e2f3'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded per table: create_all() may already have built these (it runs
    # before Alembic on startup); re-creating would wedge the migration chain.
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('notification_channels'):
        _create_channels()
    if not inspector.has_table('notification_deliveries'):
        _create_deliveries()


def _create_channels() -> None:
    op.create_table(
        'notification_channels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('type', sa.String(32), nullable=True),
        sa.Column('name', sa.String(128), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('encrypted_config_json', sa.Text(), nullable=True),
        sa.Column('url_host', sa.String(255), nullable=True),
        sa.Column('min_severity', sa.String(16), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notification_channels_id',              'notification_channels', ['id'])
    op.create_index('ix_notification_channels_organization_id', 'notification_channels', ['organization_id'])


def _create_deliveries() -> None:
    op.create_table(
        'notification_deliveries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('channel_id', sa.Integer(), sa.ForeignKey('notification_channels.id'), nullable=False),
        sa.Column('finding_id', sa.Integer(), sa.ForeignKey('asset_findings.id'), nullable=False),
        sa.Column('status', sa.String(24), nullable=True),
        sa.Column('attempt_count', sa.Integer(), nullable=True),
        sa.Column('request_url_host', sa.String(255), nullable=True),
        sa.Column('response_status', sa.Integer(), nullable=True),
        sa.Column('last_error', sa.String(255), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notification_deliveries_id',              'notification_deliveries', ['id'])
    op.create_index('ix_notification_deliveries_organization_id', 'notification_deliveries', ['organization_id'])
    op.create_index('ix_notification_deliveries_channel_id',      'notification_deliveries', ['channel_id'])
    op.create_index('ix_notification_deliveries_finding_id',      'notification_deliveries', ['finding_id'])
    op.create_index('ix_notif_deliveries_org_channel_finding',   'notification_deliveries',
                    ['organization_id', 'channel_id', 'finding_id'])


def downgrade() -> None:
    op.drop_table('notification_deliveries')
    op.drop_table('notification_channels')
