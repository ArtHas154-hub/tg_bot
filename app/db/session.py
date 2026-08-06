import re

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


class _InMemoryScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None

    def scalar_one_or_none(self):
        return self._values[0] if self._values else None


class _InMemoryResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        scalar_values = []
        for row in self._rows:
            if isinstance(row, tuple):
                scalar_values.append(row[0] if len(row) == 1 else row)
            else:
                scalar_values.append(row)
        return _InMemoryScalarResult(scalar_values)


class InMemorySession:
    def __init__(self) -> None:
        self.store = IN_MEMORY_STORE

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

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
            elif request_id in self.store.withdraws:
                self.store.withdraws[request_id] = obj
                return
            if getattr(obj, 'status', None) is None:
                obj.status = WithdrawStatus.PENDING
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

    async def execute(self, statement):
        from app.db.models import Balance, Deal, Payment, User, WithdrawRequest

        def _filter_rows(model, rows):
            statement_text = str(statement).lower()
            if model is User:
                if 'blocked = false' in statement_text or 'blocked=false' in statement_text:
                    rows = [row for row in rows if not getattr(row, 'blocked', False)]
                if 'blocked is true' in statement_text or 'blocked=true' in statement_text:
                    rows = [row for row in rows if getattr(row, 'blocked', False)]
                if 'blocked = true' in statement_text or 'blocked=true' in statement_text:
                    rows = [row for row in rows if getattr(row, 'blocked', False)]
                match = re.search(r'user_id\s*=\s*(\d+)', statement_text)
                if match:
                    target_id = int(match.group(1))
                    rows = [row for row in rows if getattr(row, 'id', None) == target_id]
            if model is Balance:
                match = re.search(r'user_id\s*=\s*(\d+)', statement_text)
                if match:
                    target_id = int(match.group(1))
                    rows = [row for row in rows if getattr(row, 'user_id', None) == target_id]
            return rows

        if hasattr(statement, 'column_descriptions'):
            raw_columns = getattr(statement, '_raw_columns', ())
            if not raw_columns:
                return _InMemoryResult([])

            target = getattr(statement, 'get_final_froms', lambda: [])()
            froms = target or []
            model = froms[0].entity if froms and hasattr(froms[0], 'entity') else None
            if model is None:
                model = getattr(statement, '_from_obj', None)
                if model is not None and hasattr(model, 'entity'):
                    model = model.entity

            if model in {User, Deal, Balance, Payment, WithdrawRequest}:
                items = _filter_rows(model, list(self._iter_model_rows(model)))
                if hasattr(statement, 'limit') and statement.limit is not None:
                    items = items[:statement.limit]
                if len(raw_columns) == 1 and getattr(raw_columns[0], 'name', None) == 'id':
                    return _InMemoryResult([(item.id if hasattr(item, 'id') else item,) for item in items])
                return _InMemoryResult([(item,) for item in items])

            raw_column = raw_columns[0]
            if raw_column is not None and hasattr(raw_column, 'name'):
                column_name = raw_column.name
                if model is User:
                    values = [getattr(obj, column_name) for obj in _filter_rows(model, list(self.store.users.values()))]
                    if hasattr(statement, 'limit') and statement.limit is not None:
                        values = values[:statement.limit]
                    return _InMemoryResult([(value,) for value in values])

            return _InMemoryResult([])

        return _InMemoryResult([])

    async def scalar(self, statement):
        from app.db.models import Balance, Deal, Payment, User, WithdrawRequest
        from sqlalchemy import func

        columns = getattr(statement, '_raw_columns', ())
        if not columns:
            return None

        first = columns[0]
        froms = getattr(statement, 'get_final_froms', lambda: [])()
        model = froms[0].entity if froms and hasattr(froms[0], 'entity') else None

        if model is None:
            model = getattr(statement, '_from_obj', None)
            if model is not None and hasattr(model, 'entity'):
                model = model.entity

        stmt_text = str(statement).lower()
        if model is User:
            filtered = [user for user in self.store.users.values() if not getattr(user, 'blocked', False)] if 'blocked = false' in stmt_text or 'blocked=false' in stmt_text else list(self.store.users.values())
            if 'blocked is true' in stmt_text or 'blocked=true' in stmt_text:
                filtered = [user for user in self.store.users.values() if getattr(user, 'blocked', False)]
            return len(filtered)

        if model is Deal:
            return len(self.store.deals)

        if model is Balance:
            return len(self.store.balances)

        if model is WithdrawRequest:
            return len(self.store.withdraws)

        if model is Payment:
            return len(self.store.payments)

        if hasattr(first, 'name') and first.name == 'count_1':
            return len(self.store.users)

        if hasattr(first, 'expr') and getattr(first.expr, 'name', None) == 'count_1':
            return len(self.store.users)

        for table_name, store in {
            'users': self.store.users,
            'deals': self.store.deals,
            'balances': self.store.balances,
            'withdraw_requests': self.store.withdraws,
            'payments': self.store.payments,
        }.items():
            if table_name in stmt_text:
                return len(store)

        return None

    def _iter_model_rows(self, model):
        from app.db.models import Balance, Deal, Payment, User, WithdrawRequest

        if model is User:
            return list(self.store.users.values())
        if model is Deal:
            return list(self.store.deals.values())
        if model is Balance:
            return [value for value in self.store.balances.values()]
        if model is Payment:
            return list(self.store.payments.values())
        if model is WithdrawRequest:
            return list(self.store.withdraws.values())
        return []

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
