import pytest

from app.bot import middlewares
from app.bot.handlers import admin_callback, broadcast_confirm, menu_callback, confirm_payment, send_messages_concurrently, withdraw_ok
from app.db.models import Balance, Currency, Deal, DealStatus, Payment, PaymentStatus, User, UserRole, WithdrawStatus
from app.db.repository import BalanceRepository, DealRepository, UserRepository, WithdrawRepository
from app.db.session import InMemorySession


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))

    async def send_photo(self, chat_id, photo, caption=None, **kwargs):
        self.sent.append((chat_id, caption, kwargs))


class FakeChat:
    def __init__(self, chat_id):
        self.id = chat_id


class FakeMessage:
    def __init__(self, chat_id, bot=None, text=''):
        self.chat = FakeChat(chat_id)
        self.bot = bot
        self.text = text
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))
        return None


class FakeState:
    def __init__(self, data=None):
        self.data = data or {}
        self.cleared = False

    async def get_data(self):
        return self.data

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def set_state(self, *args, **kwargs):
        return None

    async def clear(self):
        self.cleared = True


class FakeCallback:
    def __init__(self, data, bot, message=None):
        self.data = data
        self.bot = bot
        self.message = message
        self.answered = False

    async def answer(self, *args, **kwargs):
        self.answered = True


@pytest.mark.asyncio
async def test_sync_user_profile_commits_after_persisting_user(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.commit_calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def add(self, obj):
            return None

        async def flush(self):
            return None

        async def commit(self):
            self.commit_calls += 1

        async def execute(self, *args, **kwargs):
            return None

    session = FakeSession()
    monkeypatch.setattr(middlewares, 'get_session', lambda: session)
    monkeypatch.setattr(middlewares, 'PROFILE_CACHE', {})
    monkeypatch.setattr(middlewares, 'PROFILE_SYNC_TASKS', {})

    async def fake_set(self, key, value):
        return None

    monkeypatch.setattr(middlewares.SettingsRepository, 'set', fake_set)

    await middlewares._sync_user_profile(session, 123456, 'tester', 'Tester')

    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_menu_callback_switches_language():
    bot = FakeBot()
    session = InMemorySession()
    user = User(id=42, username='tester')
    session.add(user)

    callback = FakeCallback(data='set_lang_en', bot=bot, message=FakeMessage(chat_id=42))
    await menu_callback(callback, None, session, user, False, False)

    assert callback.answered is True
    assert any('Interface language updated.' in (text or '') for _, text, _ in bot.sent)


@pytest.mark.asyncio
async def test_next_deal_number_is_randomized_and_unique():
    session = InMemorySession()
    repo = DealRepository(session)

    number = await repo.next_deal_number()

    assert 1000 <= number <= 99999


@pytest.mark.asyncio
async def test_consecutive_deals_are_randomized_and_unique():
    session = InMemorySession()
    repo = DealRepository(session)

    first = await repo.create(1, Currency.RUB, 500.0, 'First', 'COMMENT')
    second = await repo.create(2, Currency.RUB, 600.0, 'Second', 'COMMENT2')

    assert first.deal_number != second.deal_number
    assert 1000 <= first.deal_number <= 99999
    assert 1000 <= second.deal_number <= 99999


@pytest.mark.asyncio
async def test_send_messages_concurrently_delivers_to_all_targets():
    class SpyBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, chat_id, text, **kwargs):
            self.sent.append((chat_id, text, kwargs))

    bot = SpyBot()
    await send_messages_concurrently(bot, [1, 2, 3], 'hello')

    assert [chat_id for chat_id, _, _ in bot.sent] == [1, 2, 3]


@pytest.mark.asyncio
async def test_user_repository_get_returns_target_user_for_in_memory_sessions():
    session = InMemorySession()
    first = User(id=1, username='first')
    second = User(id=2, username='second')
    session.add(first)
    session.add(second)

    found = await UserRepository(session).get(2)

    assert found is second
    assert found.id == 2


@pytest.mark.asyncio
async def test_withdraw_ok_reduces_balance():
    session = InMemorySession()
    user = User(id=10, username='user')
    session.add(user)

    balance = Balance(user_id=user.id, currency=Currency.RUB, amount=250.0)
    session.add(balance)

    withdraw_repo = WithdrawRepository(session)
    request = await withdraw_repo.create(user.id, Currency.RUB, 250.0)

    admin = User(id=11, username='admin')
    session.add(admin)

    callback = FakeCallback(data=f'withdraw_ok:{request.id}', bot=FakeBot(), message=FakeMessage(chat_id=11))
    await withdraw_ok(callback, session, admin, True, True)

    updated_balance = await BalanceRepository(session).get_balance(user.id, Currency.RUB)
    assert updated_balance is not None
    assert updated_balance.amount == 0.0
    assert request.status == WithdrawStatus.COMPLETED


@pytest.mark.asyncio
async def test_confirm_payment_sends_seller_transfer_button():
    bot = FakeBot()
    session = InMemorySession()

    seller = User(id=1, username='seller')
    buyer = User(id=2, username='buyer')
    session.add(seller)
    session.add(buyer)

    deal_repo = DealRepository(session)
    deal = await deal_repo.create(seller.id, Currency.RUB, 100.0, 'Test NFT', 'PAYCOMMENT')
    payment = Payment()
    payment.deal = deal
    payment.deal_id = deal.id
    payment.buyer_id = buyer.id
    payment.amount = deal.amount
    payment.currency = deal.currency
    payment.comment = 'comment'
    payment.status = PaymentStatus.WAITING
    session.add(payment)

    admin = User(id=3, username='admin')
    session.add(admin)

    callback = FakeCallback(data=f'confirm_payment:{payment.id}', bot=bot, message=FakeMessage(chat_id=3))
    await confirm_payment(callback, session, admin, True, True)

    assert any('Передайте подарок покупателю' in (text or '') for _, text, _ in bot.sent)
    assert any('seller_transferred' in str(kwargs.get('reply_markup')) for _, _, kwargs in bot.sent)


@pytest.mark.asyncio
async def test_admin_balances_shows_in_memory_balances():
    session = InMemorySession()
    admin = User(id=1001, username='admin')
    target = User(id=1002, username='seller')
    session.add(admin)
    session.add(target)
    await BalanceRepository(session).change(target.id, Currency.RUB, 125.0)

    message = FakeMessage(chat_id=admin.id)
    callback = FakeCallback(data='admin_balances', bot=FakeBot(), message=message)
    await admin_callback(callback, FakeState(), session, admin, True, False)

    assert callback.answered is True
    assert message.answers
    assert 'Балансы отсутствуют' not in message.answers[-1][0]
    assert '@seller | 125.00 RUB' in message.answers[-1][0]


@pytest.mark.asyncio
async def test_broadcast_reports_total_recipients_when_delivery_fails():
    class FailingBot:
        async def send_message(self, chat_id, text, **kwargs):
            raise RuntimeError('network unavailable')

    session = InMemorySession()
    admin = User(id=2001, username='admin', role=UserRole.ADMIN)
    user = User(id=2002, username='user')
    session.add(admin)
    session.add(user)

    state = FakeState({'broadcast_text': 'hello'})
    message = FakeMessage(chat_id=admin.id, bot=FailingBot(), text='Да')
    await broadcast_confirm(message, state, session, admin)

    assert state.cleared is True
    assert message.answers[-1][0].startswith('✅ Рассылка отправлена 0 из ')
    assert message.answers[-1][0] != '✅ Рассылка отправлена 0 пользователям.'

@pytest.mark.asyncio
async def test_db_export_import_round_trips_core_tables():
    from app.bot.handlers import export_db_file, import_db_payload
    import json

    session = InMemorySession()
    seller = User(id=901, username='seller')
    buyer = User(id=902, username='buyer')
    session.add(seller)
    session.add(buyer)
    deal = await DealRepository(session).create(seller.id, Currency.RUB, 500.0, 'Gift', 'COMMENT')
    payment = Payment(deal_id=deal.id, buyer_id=buyer.id, amount=500.0, currency=Currency.RUB, comment='COMMENT', status=PaymentStatus.WAITING)
    session.add(payment)
    request = await WithdrawRepository(session).create(seller.id, Currency.RUB, 100.0)
    await BalanceRepository(session).change(seller.id, Currency.RUB, 100.0)

    export_path = await export_db_file(session)
    payload = json.loads(export_path.read_text(encoding='utf-8'))

    assert len(payload['users']) >= 2
    assert len(payload['deals']) >= 1
    assert len(payload['payments']) >= 1
    assert len(payload['withdraw_requests']) >= 1
    assert len(payload['balances']) >= 1

    counts = await import_db_payload(session, payload)

    assert counts['users'] >= 2
    assert counts['deals'] >= 1
    assert counts['payments'] >= 1
    assert counts['withdraw_requests'] >= 1
    assert counts['balances'] >= 1
