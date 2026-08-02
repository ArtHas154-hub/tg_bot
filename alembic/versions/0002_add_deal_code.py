from alembic import op
import sqlalchemy as sa

revision = '0002_add_deal_code'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('deals', sa.Column('deal_code', sa.String(length=16), nullable=True))
    op.execute("UPDATE deals SET deal_code = 'deal_' || deal_number")
    op.alter_column('deals', 'deal_code', nullable=False)
    op.create_unique_constraint('uq_deal_code', 'deals', ['deal_code'])


def downgrade() -> None:
    op.drop_constraint('uq_deal_code', 'deals', type_='unique')
    op.drop_column('deals', 'deal_code')
