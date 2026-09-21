"""campaign manager aspirant link

Revision ID: 7a2e731a4aa2
Revises: c73f2df23f34
Create Date: 2026-09-18 00:00:00.000000

`agent.aspirant_id` — the aspirant a campaign manager registered under (see
api/auth.py's register_campaign_manager), chosen from the list of
already-registered aspirants at signup. Mirrors `agent.assigned_by` one
level up the hierarchy. Null for every non-campaign_manager role, and for
every existing campaign manager row (no backfill possible — the old
registration flow never asked for this).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7a2e731a4aa2'
down_revision = 'c73f2df23f34'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.add_column(sa.Column('aspirant_id', sa.UUID(), nullable=True))
        batch_op.create_foreign_key(batch_op.f('fk_agent_aspirant_id'), 'agent', ['aspirant_id'], ['id'])


def downgrade():
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_agent_aspirant_id'), type_='foreignkey')
        batch_op.drop_column('aspirant_id')
