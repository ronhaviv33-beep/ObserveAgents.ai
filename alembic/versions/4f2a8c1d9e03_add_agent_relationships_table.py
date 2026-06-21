"""add_agent_relationships_table

Revision ID: 4f2a8c1d9e03
Revises: 99d18c0f5741
Create Date: 2026-06-21 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4f2a8c1d9e03'
down_revision: Union[str, Sequence[str], None] = '99d18c0f5741'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_relationships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('source_agent_id', sa.String(64), nullable=True),
        sa.Column('source_agent_name', sa.String(256), nullable=False),
        sa.Column('target_type', sa.String(32), nullable=False),
        sa.Column('target_name', sa.String(256), nullable=False),
        sa.Column('target_identifier', sa.String(512), nullable=True),
        sa.Column('relationship_type', sa.String(64), nullable=False),
        sa.Column('evidence_source', sa.String(32), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=False, server_default='0.70'),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('request_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'organization_id', 'source_agent_name', 'target_type', 'target_name', 'relationship_type',
            name='uq_agent_relationship',
        ),
    )
    op.create_index('ix_agent_relationships_id',                'agent_relationships', ['id'])
    op.create_index('ix_agent_relationships_organization_id',   'agent_relationships', ['organization_id'])
    op.create_index('ix_agent_relationships_source_agent_name', 'agent_relationships', ['source_agent_name'])
    op.create_index('ix_agent_relationships_target_type',       'agent_relationships', ['target_type'])
    op.create_index('ix_agent_relationships_target_name',       'agent_relationships', ['target_name'])
    op.create_index('ix_agent_relationships_relationship_type', 'agent_relationships', ['relationship_type'])
    op.create_index('ix_agent_relationships_last_seen_at',      'agent_relationships', ['last_seen_at'])


def downgrade() -> None:
    op.drop_index('ix_agent_relationships_last_seen_at',      table_name='agent_relationships')
    op.drop_index('ix_agent_relationships_relationship_type', table_name='agent_relationships')
    op.drop_index('ix_agent_relationships_target_name',       table_name='agent_relationships')
    op.drop_index('ix_agent_relationships_target_type',       table_name='agent_relationships')
    op.drop_index('ix_agent_relationships_source_agent_name', table_name='agent_relationships')
    op.drop_index('ix_agent_relationships_organization_id',   table_name='agent_relationships')
    op.drop_index('ix_agent_relationships_id',                table_name='agent_relationships')
    op.drop_table('agent_relationships')
