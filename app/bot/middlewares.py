from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from types import SimpleNamespace

from app.bot.utils import parse_start_payload
from app.core.config import ADMIN_IDS, SUPER_ADMIN_IDS
from app.db.repository import UserRepository
from app.db.session import get_session, InMemorySession
from app.db.models import UserRole


class DatabaseMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            async with get_session() as session:
                data['session'] = session
                return await handler(event, data)
        except Exception:
            # If DB is not available, continue with in-memory fallback session
            data['session'] = InMemorySession()
            return await handler(event, data)


class UserProfileMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        session: AsyncSession = data.get('session')
        if session is None:
            # DB not available — create a minimal in-memory user object
            user = None
            if isinstance(event, Message):
                user = event.from_user
            elif isinstance(event, CallbackQuery):
                user = event.from_user

            if user is None:
                return await handler(event, data)

            role = UserRole.SUPER_ADMIN if user.id in SUPER_ADMIN_IDS else UserRole.ADMIN if user.id in ADMIN_IDS else UserRole.USER
            db_user = SimpleNamespace(
                id=user.id,
                username=getattr(user, 'username', None),
                full_name=getattr(user, 'full_name', None),
                registered_at=None,
                card_data=None,
                ton_wallet=None,
                stars_recipient=None,
                completed_deals=0,
                total_volume=0.0,
                blocked=False,
                role=role,
            )
            data['db_user'] = db_user
            data['is_admin'] = user.id in ADMIN_IDS
            data['is_super_admin'] = user.id in SUPER_ADMIN_IDS
            data['payload'] = parse_start_payload(event.text if isinstance(event, Message) else event.message.text if event.message else None)
            return await handler(event, data)

        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user is None:
            return await handler(event, data)

        repo = UserRepository(session)
        try:
            db_user = await repo.create_or_update(user.id, user.username, user.full_name)
        except Exception:
            # If DB operation fails after session creation, fall back to minimal user
            db_user = SimpleNamespace(
                id=user.id,
                username=getattr(user, 'username', None),
                full_name=getattr(user, 'full_name', None),
                registered_at=None,
                card_data=None,
                ton_wallet=None,
                stars_recipient=None,
                completed_deals=0,
                total_volume=0.0,
                blocked=False,
                role=UserRole.USER,
            )
        if user.id in SUPER_ADMIN_IDS:
            db_user.role = UserRole.SUPER_ADMIN
        elif user.id in ADMIN_IDS:
            db_user.role = UserRole.ADMIN

        if getattr(db_user, 'blocked', False):
            if isinstance(event, Message):
                await event.answer('⛔ Ваш аккаунт заблокирован. Обратитесь к администратору.', show_alert=True)
            else:
                await event.answer('⛔ Ваш аккаунт заблокирован. Обратитесь к администратору.', show_alert=True)
            return

        data['db_user'] = db_user
        data['is_admin'] = user.id in ADMIN_IDS
        data['is_super_admin'] = user.id in SUPER_ADMIN_IDS
        data['payload'] = parse_start_payload(event.text if isinstance(event, Message) else event.message.text if event.message else None)
        return await handler(event, data)
