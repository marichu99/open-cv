"""aspirant candidacy link

Revision ID: c73f2df23f34
Revises: 65d64e093831
Create Date: 2026-09-18 00:00:00.000000

`agent.candidate_id` — the aspirant's own Candidate roster entry, set at
registration (api/auth.py's register_aspirant) via the same
get_or_create_candidate lookup a form extraction or a campaign-manager-seeded
roster entry uses. Null for every non-aspirant role. No backfill: this is a
brand new capability, not a fact about existing rows.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c73f2df23f34'
down_revision = '65d64e093831'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.add_column(sa.Column('candidate_id', sa.UUID(), nullable=True))
        batch_op.create_foreign_key(batch_op.f('fk_agent_candidate_id'), 'candidate', ['candidate_id'], ['id'])


def downgrade():
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_agent_candidate_id'), type_='foreignkey')
        batch_op.drop_column('candidate_id')
