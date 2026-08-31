"""add stream_number to form_submission

Revision ID: 35653319bd80
Revises: f3a9c1d4e8b2
Create Date: 2026-08-31 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '35653319bd80'
down_revision = 'f3a9c1d4e8b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('form_submission', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stream_number', sa.SmallInteger(), nullable=False, server_default='1'))


def downgrade():
    with op.batch_alter_table('form_submission', schema=None) as batch_op:
        batch_op.drop_column('stream_number')
