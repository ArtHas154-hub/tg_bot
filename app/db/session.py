from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import DATABASE_URL

engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class InMemoryStore:
    def __init__(self) -> None:
        self.users: dict[int, object] = {}
        self.balances: dict[tuple[int, object], object] = {}
        self.deals: dict[int, object] = {}
        self.payments: dict[int, object] = {}
        self.withdraws: dict[int, object] = {}
        self.settings: dict[str, object] = {}
        self.admin_logs: list[object] = []
        self.next_deal_number: int = 1

    def get_next_deal_number(self) -> int:
        """Get next deal number, accounting for existing deals in memory"""
        if self.deals:
            max_num = max(self.deals.keys()) if self.deals else 0
            self.next_deal_number = max(self.next_deal_number, max_num + 1)
        else:
            self.next_deal_number = 1
        next_num = self.next_deal_number
        self.next_deal_number += 1
        return next_num


IN_MEMORY_STORE = InMemoryStore()


class InMemorySession:
    def __init__(self) -> None:
        self.store = IN_MEMORY_STORE

    def add(self, obj: object) -> None:
        from app.db.models import AdminLog, Balance, Deal, Payment, Setting, User, WithdrawRequest

        if isinstance(obj, User):
            self.store.users[obj.id] = obj
        elif isinstance(obj, Balance):
            self.store.balances[(obj.user_id, obj.currency)] = obj
        elif isinstance(obj, Deal):
            # ensure in-memory deals have an `id` for callbacks that expect it
            deal_id = getattr(obj, 'id', None)
            if deal_id is None:
                # assign a simple incremental id
                deal_id = (max(self.store.deals.keys()) + 1) if self.store.deals else 1
                try:
                    obj.id = deal_id
                except Exception:
                    pass
            self.store.deals[obj.deal_number] = obj
        elif isinstance(obj, Payment):
            payment_id = getattr(obj, 'id', None)
            if payment_id is None:
                payment_id = len(self.store.payments) + 1
                obj.id = payment_id
            self.store.payments[payment_id] = obj
        elif isinstance(obj, WithdrawRequest):
            request_id = getattr(obj, 'id', None)
            if request_id is None:
                request_id = len(self.store.withdraws) + 1
                obj.id = request_id
            self.store.withdraws[request_id] = obj
        elif isinstance(obj, Setting):
            self.store.settings[obj.key] = obj
        elif isinstance(obj, AdminLog):
            self.store.admin_logs.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def get(self, model, pk):
        # Minimal support for session.get(model, pk) in in-memory tests
        from app.db.models import Deal, Payment, WithdrawRequest, User

        if model is Deal:
            # PK might be id or deal_number; find by id first
            for deal in self.store.deals.values():
                if getattr(deal, 'id', None) == pk:
                    return deal
            # fallback: treat pk as deal_number
            return self.store.deals.get(pk)
        if model is Payment:
            return self.store.payments.get(pk)
        if model is WithdrawRequest:
            return self.store.withdraws.get(pk)
        if model is User:
            return self.store.users.get(pk)
        return None


def get_session() -> AsyncSession | InMemorySession:
    return AsyncSessionLocal()
