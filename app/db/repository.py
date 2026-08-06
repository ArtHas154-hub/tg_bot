from __future__ import annotations
import random
from datetime import datetime
from typing import Any
from sqlalchemy import select, update, func, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Balance,
    Currency,
    Deal,
    DealStatus,
    Payment,
    PaymentStatus,
    Setting,
    User,
    UserRole,
    WithdrawRequest,
    WithdrawStatus,
    AdminLog,
)
from app.bot.utils import build_deal_code
from app.db.session import InMemorySession, IN_MEMORY_STORE


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _use_memory(self) -> bool:
        return isinstance(self.session, InMemorySession)

    async def get(self, user_id: int) -> User | None:
        if self._use_memory():
            return IN_MEMORY_STORE.users.get(user_id)
        result = await self.session.execute(select(User).where(User.id == user_id))
        if result is None:
            return None
        if hasattr(result, 'scalar_one_or_none'):
            return result.scalar_one_or_none()
        if hasattr(result, 'scalars'):
            return result.scalars().first()
        return None

    async def create_or_update(self, user_id: int, username: str | None, full_name: str | None) -> User:
        user = await self.get(user_id)
        if user is None:
            user = User(id=user_id, username=username, full_name=full_name)
            self.session.add(user)
            await self.session.flush()
            return user

        changed = False
        if username is not None and user.username != username:
            user.username = username
            changed = True
        if full_name is not None and user.full_name != full_name:
            user.full_name = full_name
            changed = True
        if changed:
            await self.session.flush()
        return user

    async def set_role(self, user_id: int, role: UserRole) -> None:
        if self._use_memory():
            user = IN_MEMORY_STORE.users.get(user_id)
            if user:
                user.role = role
            return
        await self.session.execute(update(User).where(User.id == user_id).values(role=role))
        await self.session.flush()

    async def block(self, user_id: int, blocked: bool = True) -> None:
        if self._use_memory():
            user = IN_MEMORY_STORE.users.get(user_id)
            if user:
                user.blocked = blocked
            return
        await self.session.execute(update(User).where(User.id == user_id).values(blocked=blocked))
        await self.session.flush()

    async def search(self, query: str, limit: int = 20) -> list[User]:
        if self._use_memory():
            query_lower = query.lower()
            return [
                user for user in IN_MEMORY_STORE.users.values()
                if query_lower in (user.username or '').lower()
                or query_lower in (user.full_name or '').lower()
                or query_lower in str(user.id)
            ][:limit]
        stmt = select(User).where(
            (User.username.ilike(f'%{query}%'))
            | (User.full_name.ilike(f'%{query}%'))
            | (func.cast(User.id, String).ilike(f'%{query}%'))
        ).limit(limit)
        result = await self.session.execute(stmt)
        if result is None:
            return []
        if hasattr(result, 'scalars'):
            return result.scalars().all()
        return []


    async def update_requisites(
        self,
        user_id: int,
        *,
        card_data: str | None = None,
        ton_wallet: str | None = None,
        stars_recipient: str | None = None,
    ) -> User | None:
        user = await self.get(user_id)
        if user is None:
            return None
        values = {}
        if card_data is not None:
            user.card_data = card_data
            values['card_data'] = card_data
        if ton_wallet is not None:
            user.ton_wallet = ton_wallet
            values['ton_wallet'] = ton_wallet
        if stars_recipient is not None:
            user.stars_recipient = stars_recipient
            values['stars_recipient'] = stars_recipient
        if values and not self._use_memory():
            await self.session.execute(update(User).where(User.id == user_id).values(**values))
        await self.session.flush()
        return user


class BalanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _use_memory(self) -> bool:
        return isinstance(self.session, InMemorySession)

    async def get_balance(self, user_id: int, currency: Currency) -> Balance | None:
        if self._use_memory():
            return IN_MEMORY_STORE.balances.get((user_id, currency))
        result = await self.session.execute(
            select(Balance).where(Balance.user_id == user_id, Balance.currency == currency)
        )
        if result is None:
            return None
        if hasattr(result, 'scalar_one_or_none'):
            return result.scalar_one_or_none()
        if hasattr(result, 'scalars'):
            return result.scalars().first()
        return None

    async def ensure_balance(self, user_id: int, currency: Currency) -> Balance:
        balance = await self.get_balance(user_id, currency)
        if balance is None:
            balance = Balance(user_id=user_id, currency=currency, amount=0.0)
            self.session.add(balance)
            await self.session.flush()
            if self._use_memory():
                IN_MEMORY_STORE.balances[(user_id, currency)] = balance
        return balance

    async def change(self, user_id: int, currency: Currency, delta: float) -> Balance:
        balance = await self.ensure_balance(user_id, currency)
        balance.amount = max(float(balance.amount) + float(delta), 0.0)
        await self.session.flush()
        return balance

    async def list_balances(self, user_id: int) -> list[Balance]:
        if self._use_memory():
            return [balance for key, balance in IN_MEMORY_STORE.balances.items() if key[0] == user_id]
        result = await self.session.execute(select(Balance).where(Balance.user_id == user_id))
        if result is None:
            return []
        if hasattr(result, 'scalars'):
            return result.scalars().all()
        return []


class DealRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _use_memory(self) -> bool:
        return isinstance(self.session, InMemorySession)

    async def next_deal_number(self) -> int:
        if self._use_memory():
            while True:
                number = random.randint(1000, 99999)
                if number not in IN_MEMORY_STORE.deals:
                    return number

        result = await self.session.execute(select(func.max(Deal.deal_number)))
        last = None
        if result is not None and hasattr(result, 'scalar_one_or_none'):
            last = result.scalar_one_or_none()
        if last is None:
            candidate = random.randint(1000, 99999)
            while True:
                existing = await self.get_by_number(candidate)
                if existing is None:
                    return candidate
                candidate = random.randint(1000, 99999)
        candidate = random.randint(1000, 99999)
        while True:
            existing = await self.get_by_number(candidate)
            if existing is None:
                return candidate
            candidate = random.randint(1000, 99999)

    async def create(self, seller_id: int, currency: Currency, amount: float, item_description: str, payment_comment: str) -> Deal:
        deal_number = await self.next_deal_number()
        deal_code = build_deal_code(8)
        while await self.get_by_code(deal_code):
            deal_code = build_deal_code(8)
        deal = Deal(
            deal_number=deal_number,
            deal_code=deal_code,
            seller_id=seller_id,
            deal_type='Подарки',
            currency=currency,
            amount=amount,
            item_description=item_description,
            status=DealStatus.WAITING_PAYMENT,
            payment_comment=payment_comment,
        )
        self.session.add(deal)
        await self.session.flush()
        return deal

    async def get_by_number(self, deal_number: int) -> Deal | None:
        if self._use_memory():
            return IN_MEMORY_STORE.deals.get(deal_number)
        result = await self.session.execute(select(Deal).where(Deal.deal_number == deal_number))
        if result is None:
            return None
        if hasattr(result, 'scalar_one_or_none'):
            return result.scalar_one_or_none()
        if hasattr(result, 'scalars'):
            return result.scalars().first()
        return None

    async def get_by_code(self, deal_code: str) -> Deal | None:
        if self._use_memory():
            for deal in IN_MEMORY_STORE.deals.values():
                if deal.deal_code == deal_code:
                    return deal
            return None
        result = await self.session.execute(select(Deal).where(Deal.deal_code == deal_code))
        if result is None:
            return None
        if hasattr(result, 'scalar_one_or_none'):
            return result.scalar_one_or_none()
        if hasattr(result, 'scalars'):
            return result.scalars().first()
        return None

    async def list_recent(self, limit: int = 20) -> list[Deal]:
        if self._use_memory():
            return sorted(IN_MEMORY_STORE.deals.values(), key=lambda deal: deal.created_at, reverse=True)[:limit]
        result = await self.session.execute(select(Deal).order_by(Deal.created_at.desc()).limit(limit))
        if result is None:
            return []
        if hasattr(result, 'scalars'):
            return result.scalars().all()
        return []

    async def list_active(self) -> list[Deal]:
        if self._use_memory():
            return sorted(
                [
                    deal for deal in IN_MEMORY_STORE.deals.values()
                    if deal.status in {
                        DealStatus.WAITING_PAYMENT,
                        DealStatus.PAYMENT_VERIFICATION,
                        DealStatus.AWAITING_TRANSFER,
                        DealStatus.AWAITING_CONFIRM,
                    }
                ],
                key=lambda deal: deal.created_at,
                reverse=True,
            )
        result = await self.session.execute(
            select(Deal).where(Deal.status.in_([
                DealStatus.WAITING_PAYMENT,
                DealStatus.PAYMENT_VERIFICATION,
                DealStatus.AWAITING_TRANSFER,
                DealStatus.AWAITING_CONFIRM,
            ])).order_by(Deal.created_at.desc())
        )
        if result is None:
            return []
        if hasattr(result, 'scalars'):
            return result.scalars().all()
        return []

    async def update_status(self, deal: Deal, status: DealStatus) -> None:
        deal.status = status
        deal.updated_at = datetime.utcnow()
        await self.session.flush()

    async def assign_buyer(self, deal: Deal, buyer_id: int) -> None:
        deal.buyer_id = buyer_id
        await self.session.flush()


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, deal_id: int, buyer_id: int, amount: float, currency: Currency, comment: str) -> Payment:
        payment = Payment(
            deal_id=deal_id,
            buyer_id=buyer_id,
            amount=amount,
            currency=currency,
            comment=comment,
            status=PaymentStatus.WAITING,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def list_waiting(self) -> list[Payment]:
        if isinstance(self.session, InMemorySession):
            return [payment for payment in IN_MEMORY_STORE.payments.values() if payment.status == PaymentStatus.WAITING]
        result = await self.session.execute(select(Payment).where(Payment.status == PaymentStatus.WAITING))
        if result is None:
            return []
        if hasattr(result, 'scalars'):
            return result.scalars().all()
        return []

    async def update_status(self, payment: Payment, status: PaymentStatus, admin_id: int | None = None) -> None:
        payment.status = status
        payment.admin_id = admin_id
        await self.session.flush()


class WithdrawRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: int, currency: Currency, amount: float) -> WithdrawRequest:
        request = WithdrawRequest(user_id=user_id, currency=currency, amount=amount, status=WithdrawStatus.PENDING)
        self.session.add(request)
        await self.session.flush()
        if isinstance(self.session, InMemorySession):
            IN_MEMORY_STORE.withdraws[len(IN_MEMORY_STORE.withdraws) + 1] = request
        return request

    async def list_pending(self) -> list[WithdrawRequest]:
        if isinstance(self.session, InMemorySession):
            return [request for request in IN_MEMORY_STORE.withdraws.values() if request.status == WithdrawStatus.PENDING]
        result = await self.session.execute(select(WithdrawRequest).where(WithdrawRequest.status == WithdrawStatus.PENDING))
        if result is None:
            return []
        if hasattr(result, 'scalars'):
            return result.scalars().all()
        return []

    async def update_status(self, request: WithdrawRequest, status: WithdrawStatus, admin_id: int, note: str | None = None) -> None:
        request.status = status
        request.admin_id = admin_id
        request.processed_at = datetime.utcnow()
        request.note = note
        await self.session.flush()


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> str | None:
        if isinstance(self.session, InMemorySession):
            setting = IN_MEMORY_STORE.settings.get(key)
            return setting.value if setting else None
        result = await self.session.execute(select(Setting).where(Setting.key == key))
        if result is None:
            return None
        if hasattr(result, 'scalar_one_or_none'):
            setting = result.scalar_one_or_none()
        elif hasattr(result, 'scalars'):
            setting = result.scalars().first()
        else:
            setting = None
        return setting.value if setting else None

    async def set(self, key: str, value: str) -> Setting:
        if isinstance(self.session, InMemorySession):
            setting = IN_MEMORY_STORE.settings.get(key)
            if setting is None:
                setting = Setting(key=key, value=value)
                IN_MEMORY_STORE.settings[key] = setting
            else:
                setting.value = value
            return setting
        setting = await self._get_model(key)
        if setting is None:
            setting = Setting(key=key, value=value)
            self.session.add(setting)
        else:
            setting.value = value
        await self.session.flush()
        return setting

    async def _get_model(self, key: str) -> Setting | None:
        result = await self.session.execute(select(Setting).where(Setting.key == key))
        if result is None:
            return None
        if hasattr(result, 'scalar_one_or_none'):
            return result.scalar_one_or_none()
        if hasattr(result, 'scalars'):
            return result.scalars().first()
        return None


class AdminLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(self, user_id: int | None, action: str, target_type: str | None = None, target_id: str | None = None, note: str | None = None) -> AdminLog:
        record = AdminLog(user_id=user_id, action=action, target_type=target_type, target_id=target_id, note=note)
        self.session.add(record)
        await self.session.flush()
        return record

    async def recent(self, limit: int = 20) -> list[AdminLog]:
        if isinstance(self.session, InMemorySession):
            return sorted(IN_MEMORY_STORE.admin_logs, key=lambda item: item.created_at, reverse=True)[:limit]
        result = await self.session.execute(select(AdminLog).order_by(AdminLog.created_at.desc()).limit(limit))
        if result is None:
            return []
        if hasattr(result, 'scalars'):
            return result.scalars().all()
        return []
