"""Initial demo baseline: catalog, sessions, revisions, runs, snapshots."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('product_variants',
        sa.Column('id', sa.String(80), primary_key=True),
        sa.Column('category', sa.String(20), nullable=False),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('version', sa.String(160), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('mode', sa.String(12), nullable=False),
        sa.Column('reviewed', sa.String(20), nullable=False),
        sa.Column('price_observed_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_product_variants_category', 'product_variants', ['category'])
    op.create_index('ix_product_variants_mode', 'product_variants', ['mode'])
    op.create_table('anonymous_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('requirement_revisions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('anonymous_sessions.id'), nullable=False),
        sa.Column('base_id', sa.String(36), nullable=True),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_requirement_revisions_session_id', 'requirement_revisions', ['session_id'])
    op.create_table('operation_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('anonymous_sessions.id'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('idempotency_key', sa.String(100), nullable=False),
        sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('stage', sa.String(80), nullable=False),
        sa.Column('output', sa.JSON(), nullable=True),
        sa.Column('error', sa.JSON(), nullable=True),
        sa.Column('result_id', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('session_id', 'idempotency_key'))
    op.create_index('ix_operation_runs_session_id', 'operation_runs', ['session_id'])
    op.create_index('ix_operation_runs_status', 'operation_runs', ['status'])
    op.create_table('recommendation_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('anonymous_sessions.id'), nullable=False),
        sa.Column('run_id', sa.String(36), sa.ForeignKey('operation_runs.id'), nullable=False, unique=True),
        sa.Column('requirement_id', sa.String(36), sa.ForeignKey('requirement_revisions.id'), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_recommendation_snapshots_session_id', 'recommendation_snapshots', ['session_id'])


def downgrade():
    for table in ['recommendation_snapshots', 'operation_runs', 'requirement_revisions', 'anonymous_sessions', 'product_variants']:
        op.drop_table(table)
