"""add agent email column

Revision ID: ab77ee1b830b
Revises: 9c48c38371ce
Create Date: 2026-08-24 09:31:44.086707

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ab77ee1b830b'
down_revision = '9c48c38371ce'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.Text(), nullable=True))
        batch_op.create_unique_constraint('uq_agent_email', ['email'])


def downgrade():
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.drop_constraint('uq_agent_email', type_='unique')
        batch_op.drop_column('email')
