"""drop agent password_hash column

Revision ID: f3a9c1d4e8b2
Revises: 2cfae5ed4e54
Create Date: 2026-08-24 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3a9c1d4e8b2'
down_revision = '2cfae5ed4e54'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.drop_column('password_hash')


def downgrade():
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.add_column(sa.Column('password_hash', sa.Text(), nullable=True))
