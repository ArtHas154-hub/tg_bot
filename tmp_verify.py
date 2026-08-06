import asyncio
from app.db.session import InMemorySession
from app.db.models import Currency, WithdrawStatus
from app.db.repository import UserRepository, BalanceRepository, WithdrawRepository

async def main():
    session = InMemorySession()
    user = await UserRepository(session).create_or_update(777, 'tester', 'Tester')
    balance = await BalanceRepository(session).ensure_balance(user.id, Currency.RUB)
    balance.amount = 150.0
    await session.flush()
    request = await WithdrawRepository(session).create(user.id, Currency.RUB, 150.0)
    print('request_status', request.status, type(request.status), request.status == WithdrawStatus.PENDING)
    pending = await WithdrawRepository(session).list_pending()
    print('pending_len', len(pending))
    print('pending_items', [(r.id, r.user_id, r.amount, r.status, type(r.status)) for r in pending])

asyncio.run(main())
