import asyncio
import sys
from pathlib import Path
# Ensure project root is on path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.session import InMemorySession, IN_MEMORY_STORE
from app.db.models import User, Deal, Payment, Currency, PaymentStatus, DealStatus
from app.db.repository import DealRepository, PaymentRepository, UserRepository, BalanceRepository
from app.bot.handlers import confirm_payment, admin_callback


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))

    async def send_photo(self, chat_id, photo, caption=None, **kwargs):
        self.sent.append((chat_id, f'<photo:{caption}>', kwargs))


class FakeChat:
    def __init__(self, chat_id):
        self.id = chat_id


class FakeMessage:
    def __init__(self, chat_id):
        self.chat = FakeChat(chat_id)
        self._answers = []

    async def answer(self, text, **kwargs):
        # emulate message.answer by calling bot (not available here); just record
        self._answers.append((text, kwargs))


class FakeCallback:
    def __init__(self, data, bot, message=None):
        self.data = data
        self.bot = bot
        self.message = message
        self.answered = False

    async def answer(self, *args, **kwargs):
        self.answered = True


async def run_scenario():
    bot = FakeBot()
    session = InMemorySession()

    # create seller and buyer
    seller = User(id=1111, username='seller')
    buyer = User(id=2222, username='buyer')
    session.add(seller)
    session.add(buyer)

    # create deal by seller via repository
    deal_repo = DealRepository(session)
    deal_number = await deal_repo.next_deal_number()
    deal = await deal_repo.create(seller.id, Currency.RUB, 123.45, 'Test NFT', 'PAYCOMMENT')
    # add to store via session.add was done inside create through session.add(deal)

    # create payment (buyer pays)
    from app.db.models import Payment as PaymentModel
    payment = PaymentModel()
    payment.deal = deal
    payment.deal_id = getattr(deal, 'id', None)
    payment.buyer_id = buyer.id
    payment.amount = deal.amount
    payment.currency = deal.currency
    payment.comment = 'payment comment'
    payment.status = PaymentStatus.WAITING
    session.add(payment)

    print('Initial store:', list(IN_MEMORY_STORE.deals.keys()), list(IN_MEMORY_STORE.payments.keys()))

    # admin confirms payment using confirm_payment handler
    # create fake callback for admin confirm (callback.data uses format 'confirm_payment:{payment.id}')
    admin_user = User(id=9999, username='admin')
    admin_user.role = None
    session.add(admin_user)

    cb_msg = FakeMessage(chat_id=9999)
    cb = FakeCallback(data=f'confirm_payment:{payment.id}', bot=bot, message=cb_msg)

    # call confirm_payment (simulate admin privileges by passing True flags)
    await confirm_payment(cb, session, admin_user, True, True)

    # verify outcomes
    deal_after = await deal_repo.get_by_number(deal.deal_number)
    print('Deal status after confirm_payment:', deal_after.status)
    print('Bot messages sent:', bot.sent)

    # Now simulate admin completing via admin_callback
    # prepare fake callback for admin panel with data 'admin_complete_deal:{deal.deal_number}'
    cb2 = FakeCallback(data=f'admin_complete_deal:{deal.deal_number}', bot=bot, message=cb_msg)
    # call admin_callback
    await admin_callback(cb2, session, admin_user, True, True)

    deal_after2 = await deal_repo.get_by_number(deal.deal_number)
    print('Deal status after admin_complete_deal:', deal_after2.status)
    print('Bot messages after admin complete:', bot.sent)


if __name__ == '__main__':
    asyncio.run(run_scenario())
