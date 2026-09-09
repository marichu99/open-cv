"""phase 0 hardening: agent activation gate + vote sanity bounds

Revision ID: c3f1a72b9d84
Revises: 35653319bd80
Create Date: 2026-09-09 12:00:00.000000

Two independent Phase-0 changes that share a migration because both are
cheap DDL on tables the app writes on every submission.

1. `agent.activated_at` — privileged roles (campaign_manager/coordinator/
   admin) now hold no privileges until an admin activates them. Every
   EXISTING row is backfilled to `now()` so real campaign managers,
   coordinators and admins are not locked out the moment this deploys.
   That backfill is the load-bearing line here.

2. CHECK constraints bounding vote figures. Previously `votes_detected` /
   `votes_corrected` were plain Integers, so anything up to 2^31-1 — and
   any NEGATIVE value — was storable and would be summed straight into the
   national tally by tally_service.EFFECTIVE_VOTES.

   NOTE: if `ck_vote_record_*` fails to create, that means rows already
   violate it. Do NOT "fix" that by clamping the data in this migration —
   out-of-range vote records are a finding to investigate, not a value to
   silently rewrite. Inspect them first.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f1a72b9d84'
down_revision = '35653319bd80'
branch_labels = None
depends_on = None

# Keep in sync with app.models.submission.MAX_VOTES_PER_FIELD.
MAX_VOTES_PER_FIELD = 100_000


def upgrade():
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.add_column(sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True))

    # Grandfather every account that already exists. Without this, the
    # activation gate in api/auth.py locks out every current admin.
    op.execute("UPDATE agent SET activated_at = NOW() WHERE activated_at IS NULL")

    with op.batch_alter_table('vote_record', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_vote_record_votes_detected_range',
            f'votes_detected >= 0 AND votes_detected <= {MAX_VOTES_PER_FIELD}',
        )
        batch_op.create_check_constraint(
            'ck_vote_record_votes_corrected_range',
            f'votes_corrected IS NULL OR '
            f'(votes_corrected >= 0 AND votes_corrected <= {MAX_VOTES_PER_FIELD})',
        )

    with op.batch_alter_table('form_submission', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_form_submission_totals_range',
            f'(total_votes_cast IS NULL OR '
            f'(total_votes_cast >= 0 AND total_votes_cast <= {MAX_VOTES_PER_FIELD})) AND '
            f'(rejected_ballots IS NULL OR '
            f'(rejected_ballots >= 0 AND rejected_ballots <= {MAX_VOTES_PER_FIELD}))',
        )


def downgrade():
    with op.batch_alter_table('form_submission', schema=None) as batch_op:
        batch_op.drop_constraint('ck_form_submission_totals_range', type_='check')

    with op.batch_alter_table('vote_record', schema=None) as batch_op:
        batch_op.drop_constraint('ck_vote_record_votes_corrected_range', type_='check')
        batch_op.drop_constraint('ck_vote_record_votes_detected_range', type_='check')

    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.drop_column('activated_at')
