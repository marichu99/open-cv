"""national geography, elective positions, dynamic candidates, campaign manager role

Revision ID: bed158bf3def
Revises: ab77ee1b830b
Create Date: 2026-08-24 12:02:30.613981

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bed158bf3def'
down_revision = 'ab77ee1b830b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('county',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('registered_voters', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('elective_position',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('form_series', sa.Text(), nullable=False),
    sa.Column('level', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.add_column(sa.Column('position_id', sa.UUID(), nullable=True))
        batch_op.create_foreign_key('fk_agent_position_id', 'elective_position', ['position_id'], ['id'])

    with op.batch_alter_table('candidate', schema=None) as batch_op:
        batch_op.add_column(sa.Column('position_id', sa.UUID(), nullable=False))
        batch_op.add_column(sa.Column('county_id', sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column('constituency_id', sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column('ward_id', sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column('normalized_name', sa.Text(), nullable=False))
        batch_op.drop_constraint(batch_op.f('candidate_ballot_position_key'), type_='unique')
        batch_op.create_unique_constraint('uq_candidate_scope_name', ['position_id', 'county_id', 'constituency_id', 'ward_id', 'normalized_name'])
        batch_op.create_foreign_key('fk_candidate_constituency_id', 'constituency', ['constituency_id'], ['id'])
        batch_op.create_foreign_key('fk_candidate_position_id', 'elective_position', ['position_id'], ['id'])
        batch_op.create_foreign_key('fk_candidate_county_id', 'county', ['county_id'], ['id'])
        batch_op.create_foreign_key('fk_candidate_ward_id', 'ward', ['ward_id'], ['id'])
        batch_op.drop_column('ballot_position')

    with op.batch_alter_table('constituency', schema=None) as batch_op:
        batch_op.add_column(sa.Column('county_id', sa.UUID(), nullable=False))
        batch_op.create_foreign_key('fk_constituency_county_id', 'county', ['county_id'], ['id'])

    with op.batch_alter_table('form_submission', schema=None) as batch_op:
        batch_op.add_column(sa.Column('position_id', sa.UUID(), nullable=False))
        batch_op.create_foreign_key('fk_form_submission_position_id', 'elective_position', ['position_id'], ['id'])

    with op.batch_alter_table('polling_station', schema=None) as batch_op:
        batch_op.alter_column('iebc_code',
               existing_type=sa.TEXT(),
               nullable=True)


def downgrade():
    with op.batch_alter_table('polling_station', schema=None) as batch_op:
        batch_op.alter_column('iebc_code',
               existing_type=sa.TEXT(),
               nullable=False)

    with op.batch_alter_table('form_submission', schema=None) as batch_op:
        batch_op.drop_constraint('fk_form_submission_position_id', type_='foreignkey')
        batch_op.drop_column('position_id')

    with op.batch_alter_table('constituency', schema=None) as batch_op:
        batch_op.drop_constraint('fk_constituency_county_id', type_='foreignkey')
        batch_op.drop_column('county_id')

    with op.batch_alter_table('candidate', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ballot_position', sa.SMALLINT(), autoincrement=False, nullable=False))
        batch_op.drop_constraint('fk_candidate_constituency_id', type_='foreignkey')
        batch_op.drop_constraint('fk_candidate_position_id', type_='foreignkey')
        batch_op.drop_constraint('fk_candidate_county_id', type_='foreignkey')
        batch_op.drop_constraint('fk_candidate_ward_id', type_='foreignkey')
        batch_op.drop_constraint('uq_candidate_scope_name', type_='unique')
        batch_op.create_unique_constraint(batch_op.f('candidate_ballot_position_key'), ['ballot_position'], postgresql_nulls_not_distinct=False)
        batch_op.drop_column('normalized_name')
        batch_op.drop_column('ward_id')
        batch_op.drop_column('constituency_id')
        batch_op.drop_column('county_id')
        batch_op.drop_column('position_id')

    with op.batch_alter_table('agent', schema=None) as batch_op:
        batch_op.drop_constraint('fk_agent_position_id', type_='foreignkey')
        batch_op.drop_column('position_id')

    op.drop_table('elective_position')
    op.drop_table('county')
