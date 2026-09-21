"""campaign-manager ownership trail + structured correction diffs

Revision ID: 65d64e093831
Revises: c3f1a72b9d84
Create Date: 2026-09-18 00:00:00.000000

Two changes in support of scoped read access to submissions/images/logs
(aspirant unscoped, campaign_manager scoped to their own agents):

1. `agent.assigned_by` — the campaign manager who last set an agent's
   station/position assignment via PATCH /api/agents/:id/assignment. Null
   for every existing row (no backfill possible — the old endpoint never
   recorded who made the assignment) and for any assignment an admin makes
   directly. This is what api/submissions.py's can_view_submission scopes a
   campaign manager's visibility on.

2. `verification_log.candidate_id` / `old_value` / `new_value` — a
   correction log row previously said only that *something* was corrected,
   by whom, and when; not which candidate's figure changed or what it
   changed from/to. VoteRecord.votes_corrected is a single mutable column,
   so a second correction silently overwrites the first with nothing else
   recording what it used to be. These columns make each log row
   self-describing. Same range bound as vote_record's existing
   ck_vote_record_votes_*_range constraints (see c3f1a72b9d84).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '65d64e093831'
down_revision = 'c3f1a72b9d84'
branch_labels = None
depends_on = None

# Keep in sync with app.models.submission.MAX_VOTES_PER_FIELD.
MAX_VOTES_PER_FIELD = 100_000


def upgrade():
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assigned_by', sa.UUID(), nullable=True))
        batch_op.create_foreign_key(batch_op.f('fk_agent_assigned_by'), 'agent', ['assigned_by'], ['id'])
        batch_op.create_index(batch_op.f('ix_agent_assigned_by'), ['assigned_by'], unique=False)

    with op.batch_alter_table('verification_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('candidate_id', sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column('old_value', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('new_value', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f('fk_verification_log_candidate_id'), 'candidate', ['candidate_id'], ['id']
        )
        batch_op.create_check_constraint(
            'ck_verification_log_values_range',
            f'(old_value IS NULL OR (old_value >= 0 AND old_value <= {MAX_VOTES_PER_FIELD})) AND '
            f'(new_value IS NULL OR (new_value >= 0 AND new_value <= {MAX_VOTES_PER_FIELD}))',
        )


def downgrade():
    with op.batch_alter_table('verification_log', schema=None) as batch_op:
        batch_op.drop_constraint('ck_verification_log_values_range', type_='check')
        batch_op.drop_constraint(batch_op.f('fk_verification_log_candidate_id'), type_='foreignkey')
        batch_op.drop_column('new_value')
        batch_op.drop_column('old_value')
        batch_op.drop_column('candidate_id')

    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agent_assigned_by'))
        batch_op.drop_constraint(batch_op.f('fk_agent_assigned_by'), type_='foreignkey')
        batch_op.drop_column('assigned_by')
