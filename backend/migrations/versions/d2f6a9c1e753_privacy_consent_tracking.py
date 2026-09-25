"""privacy consent tracking

Revision ID: d2f6a9c1e753
Revises: 7a2e731a4aa2
Create Date: 2026-09-23 00:00:00.000000

`agent.privacy_consent_at` / `agent.privacy_policy_version` — records when
an account explicitly agreed to the privacy policy at registration (see
api/auth.py's _record_consent) and which version they agreed to. No
backfill: consent is a fact about what happened at signup, not something a
migration can manufacture for existing rows.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2f6a9c1e753'
down_revision = '7a2e731a4aa2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.add_column(sa.Column('privacy_consent_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('privacy_policy_version', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.drop_column('privacy_policy_version')
        batch_op.drop_column('privacy_consent_at')
