import pytest

from app.bot.handlers import menu_callback, confirm_payment, withdraw_ok
from app.db.models import Balance, Currency, Deal, DealStatus, Payment, PaymentStatus, User, WithdrawStatus
from app.db.repository import BalanceRepository, DealRepository, WithdrawRepository
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
async def test_next_deal_number_starts_at_1():
    session = InMemorySession()
    repo = DealRepository(session)

    number = await repo.next_deal_number()

    assert number == 1


@pytest.mark.asyncio
async def test_consecutive_deals_increment_from_1():
    session = InMemorySession()
    repo = DealRepository(session)

    first = await repo.create(1, Currency.RUB, 10.0, 'First', 'COMMENT')
    second = await repo.create(2, Currency.RUB, 20.0, 'Second', 'COMMENT2')

    assert first.deal_number == 1
    assert second.deal_number == 2


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
