"""feat: add detection_rules table (admin-managed rule layer)

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-07-15

Admin-only rule management for Rules & Alerts: per-org overrides of built-in
real-time risk rules plus custom rules from approved templates. Template-based
only — config_json holds validated parameters, never code.
"""
from alembic import op
import sqlalchemy as sa

revision = 'c0d1e2f3a4b5'
down_revision = 'b9c0d1e2f3a4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded: create_all() may already have built this (it runs before
    # Alembic on startup); re-creating would wedge the migration chain.
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('detection_rules'):
        return
    op.create_table(
        'detection_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('rule_key', sa.String(64), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('description', sa.String(512), nullable=True),
        sa.Column('category', sa.String(32), nullable=False),
        sa.Column('severity', sa.String(16), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('source', sa.String(16), nullable=False),
        sa.Column('template_type', sa.String(64), nullable=False),
        sa.Column('config_json', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(256), nullable=True),
        sa.Column('updated_by', sa.String(256), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'rule_key', name='uq_detection_rules_org_key'),
    )
    op.create_index('ix_detection_rules_id', 'detection_rules', ['id'])
    op.create_index('ix_detection_rules_organization_id', 'detection_rules', ['organization_id'])
    op.create_index('ix_detection_rules_org_enabled', 'detection_rules', ['organization_id', 'enabled'])


def downgrade() -> None:
    op.drop_table('detection_rules')
