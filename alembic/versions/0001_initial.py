from alembic import op
import sqlalchemy as sa

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('username', sa.String(length=64), nullable=True),
        sa.Column('full_name', sa.String(length=128), nullable=True),
        sa.Column('registered_at', sa.DateTime(), nullable=True),
        sa.Column('card_data', sa.String(length=256), nullable=True),
        sa.Column('ton_wallet', sa.String(length=128), nullable=True),
        sa.Column('stars_recipient', sa.String(length=128), nullable=True),
        sa.Column('completed_deals', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_volume', sa.Float(), nullable=False, server_default='0'),
        sa.Column('blocked', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('role', sa.Enum('user', 'admin', 'super_admin', name='userrole'), nullable=False, server_default='user'),
    )
    op.create_table(
        'settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(length=64), nullable=False, unique=True),
        sa.Column('value', sa.Text(), nullable=False),
    )
    op.create_table(
        'admin_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('action', sa.String(length=128), nullable=False),
        sa.Column('target_type', sa.String(length=64), nullable=True),
        sa.Column('target_id', sa.String(length=64), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'deals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('deal_number', sa.Integer(), nullable=False),
        sa.Column('seller_id', sa.BigInteger(), nullable=False),
        sa.Column('buyer_id', sa.BigInteger(), nullable=True),
        sa.Column('deal_type', sa.String(length=32), nullable=False, server_default='gift'),
        sa.Column('currency', sa.Enum('RUB', 'EUR', 'KZT', 'UZS', 'UAH', 'BYN', 'TON', 'Stars', name='currency'), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('item_description', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('created', 'waiting_payment', 'payment_verification', 'awaiting_transfer', 'awaiting_confirm', 'completed', 'cancelled', 'rejected', name='dealstatus'), nullable=False, server_default='created'),
        sa.Column('payment_comment', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['seller_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['buyer_id'], ['users.id'], ),
        sa.UniqueConstraint('deal_number', name='uq_deal_number'),
    )
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('deal_id', sa.Integer(), nullable=False),
        sa.Column('buyer_id', sa.BigInteger(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.Enum('RUB', 'EUR', 'KZT', 'UZS', 'UAH', 'BYN', 'TON', 'Stars', name='currency'), nullable=False),
        sa.Column('comment', sa.String(length=64), nullable=False),
        sa.Column('status', sa.Enum('waiting', 'confirmed', 'rejected', name='paymentstatus'), nullable=False, server_default='waiting'),
        sa.Column('admin_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ),
        sa.ForeignKeyConstraint(['buyer_id'], ['users.id'], ),
    )
    op.create_table(
        'withdraw_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.Enum('RUB', 'EUR', 'KZT', 'UZS', 'UAH', 'BYN', 'TON', 'Stars', name='currency'), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'completed', 'rejected', name='withdrawstatus'), nullable=False, server_default='pending'),
        sa.Column('admin_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    )
    op.create_table(
        'balances',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.Enum('RUB', 'EUR', 'KZT', 'UZS', 'UAH', 'BYN', 'TON', 'Stars', name='currency'), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.UniqueConstraint('user_id', 'currency', name='uq_user_currency'),
    )


def downgrade() -> None:
    op.drop_table('balances')
    op.drop_table('withdraw_requests')
    op.drop_table('payments')
    op.drop_table('deals')
    op.drop_table('admin_logs')
    op.drop_table('settings')
    op.drop_table('users')
    op.execute('DROP TYPE IF EXISTS withdrawstatus')
    op.execute('DROP TYPE IF EXISTS paymentstatus')
    op.execute('DROP TYPE IF EXISTS dealstatus')
    op.execute('DROP TYPE IF EXISTS currency')
    op.execute('DROP TYPE IF EXISTS userrole')
