import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands
from aiogram.utils.backoff import BackoffConfig

from app.bot.handlers import register_handlers
from app.bot.middlewares import DatabaseMiddleware, UserProfileMiddleware
from app.core.config import BOT_TOKEN
from app.core.logger import logger

POLLING_TIMEOUT_SECONDS = 0
POLLING_BACKOFF = BackoffConfig(min_delay=0.25, max_delay=1.0, factor=1.2, jitter=0.0)


async def main() -> None:
    storage = MemoryStorage()
    session = AiohttpSession(timeout=TELEGRAM_API_TIMEOUT_SECONDS)
    session = AiohttpSession(timeout=MAX_BOT_LATENCY_SECONDS)
    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode='HTML'),
    )
    dp = Dispatcher(storage=storage)
    dp.message.middleware(DatabaseMiddleware())
    dp.message.middleware(UserProfileMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(UserProfileMiddleware())

    try:
        await setup_bot_commands(bot)
        await setup_bot_menu(bot)
        await register_handlers(dp)

        polling_timeout_ms = POLLING_TIMEOUT_SECONDS * 1000
        logger.info(f'Запуск бота с polling timeout {polling_timeout_ms} мс...')
        logger.info(
            'Запуск бота с polling timeout %.0f мс...',
            POLLING_TIMEOUT_SECONDS * 1000,
            'Запуск бота с максимальной задержкой %.0f мс...',
            MAX_BOT_LATENCY_SECONDS * 1000,
        )
        await dp.start_polling(bot, polling_timeout=POLLING_TIMEOUT_SECONDS)
    except TelegramNetworkError as exc:
        logger.error('Не удалось подключиться к Telegram API: %s', exc)
        raise
    finally:
        await bot.session.close()


async def setup_bot_commands(bot: Bot) -> None:
    try:
        await bot.delete_my_commands()
    except TelegramNetworkError as exc:
        logger.warning('Не удалось очистить команды бота: %s', exc)


async def setup_bot_menu(bot: Bot) -> None:
    commands = [
        BotCommand(command='start', description='Начать / Start'),
    ]
    try:
        await bot.set_my_commands(commands)
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception as exc:
        logger.warning('Не удалось настроить кнопки меню бота: %s', exc)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
