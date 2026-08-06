import pytest

from app.bot import middlewares
from app.bot.handlers import menu_callback, confirm_payment, send_messages_concurrently, withdraw_ok
from app.db.models import Balance, Currency, Deal, DealStatus, Payment, PaymentStatus, User, WithdrawStatus
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
    def __init__(self, chat_id):
        self.chat = FakeChat(chat_id)

    async def answer(self, text, **kwargs):
        return None


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
