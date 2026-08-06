import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands

from app.bot.handlers import register_handlers
from app.bot.middlewares import DatabaseMiddleware, UserProfileMiddleware
from app.core.config import BOT_TOKEN
from app.core.logger import logger


async def main() -> None:
    storage = MemoryStorage()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher(storage=storage)
    dp.message.middleware(DatabaseMiddleware())
    dp.message.middleware(UserProfileMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(UserProfileMiddleware())

    await bot.delete_my_commands()
    await setup_bot_menu(bot)
    await register_handlers(dp)

    logger.info('Запуск бота...')
    await dp.start_polling(bot, polling_timeout=1)


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
