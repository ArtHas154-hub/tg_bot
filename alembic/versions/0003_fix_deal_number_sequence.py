from alembic import op
import sqlalchemy as sa

revision = '0003_fix_deal_number_sequence'
down_revision = '0002_add_deal_code'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create a sequence for deal_number
    op.execute("""
        CREATE SEQUENCE deal_number_seq START 1001;
    """)
    
    # Set the default for deal_number to use the sequence
    op.alter_column(
        'deals',
        'deal_number',
        existing_type=sa.Integer(),
        server_default=sa.text("nextval('deal_number_seq')"),
    )


def downgrade() -> None:
    # Remove the default
    op.alter_column(
        'deals',
        'deal_number',
        existing_type=sa.Integer(),
        server_default=None,
    )
    
    # Drop the sequence
    op.execute("DROP SEQUENCE IF EXISTS deal_number_seq")
