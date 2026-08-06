from __future__ import annotations
import asyncio
import enum
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from aiogram import Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.filters.state import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    admin_panel_menu,
    buyer_confirm_menu,
    buyer_payment_menu,
    deal_currency_menu,
    deal_type_menu,
    main_menu,
    profile_menu,
    seller_transfer_menu,
    settings_menu,
    stats_period_menu,
    user_action_menu,
    withdraw_confirm_menu,
)
from app.bot.states import (
    AdminUserBroadcastStates,
    BroadcastStates,
    DealCreation,
    ImportDBStates,
    ProfileUpdate,
    SupportStates,
    WithdrawRequestStates,
)
from app.bot.utils import build_payment_comment, format_balance

LANGUAGE_CACHE: dict[int, str] = {}
from app.core import config, logger
from app.db.models import (
    Balance,
    Currency,
    Deal,
    DealStatus,
    Payment,
    PaymentStatus,
    User,
    UserRole,
    WithdrawRequest,
    WithdrawStatus,
)

LOGO_PATH = Path(__file__).resolve().parents[2] / 'img' / 'logo.png'
MIN_DEAL_AMOUNT = 249.0


def logo_file() -> FSInputFile:
    return FSInputFile(str(LOGO_PATH))


from app.db.repository import (
    AdminLogRepository,
    BalanceRepository,
    DealRepository,
    PaymentRepository,
    SettingsRepository,
    UserRepository,
    WithdrawRepository,
)


def get_currency_by_label(label: str) -> Optional[Currency]:
    mapping = {
        '🇷🇺 RUB': Currency.RUB,
        '🇪🇺 EUR': Currency.EUR,
        '🇰🇿 KZT': Currency.KZT,
        '🇺🇿 UZS': Currency.UZS,
        '🇺🇦 UAH': Currency.UAH,
        '🇧🇾 BYN': Currency.BYN,
        '💎 TON': Currency.TON,
        '⭐ Stars': Currency.STARS,
    }
    return mapping.get(label)


def format_deal_status(status: DealStatus) -> str:
    mapping = {
        DealStatus.WAITING_PAYMENT: 'Ожидает оплаты',
        DealStatus.PAYMENT_VERIFICATION: 'Ожидается проверка оплаты',
        DealStatus.AWAITING_TRANSFER: 'Ожидается передача товара',
        DealStatus.AWAITING_CONFIRM: 'Ожидается подтверждение получения',
        DealStatus.COMPLETED: 'Завершена',
        DealStatus.CANCELLED: 'Отменена',
        DealStatus.REJECTED: 'Отклонена',
        DealStatus.CREATED: 'Создана',
    }
    return mapping.get(status, status.value)


def format_all_balances(balances: list[Balance]) -> str:
    balance_map = {balance.currency: balance.amount for balance in balances}
    lines = [f'{currency.value}: {balance_map.get(currency, 0.0):.2f}' for currency in Currency]
    return '\n'.join(lines)


def get_deal_title(deal: Deal) -> str:
    return f'Сделка №{deal.deal_number}'


def get_minimum_amount_for_currency(currency: Currency) -> float:
    minimums = {
        Currency.RUB: 249.0,
        Currency.EUR: 2.69,
        Currency.KZT: 1470.0,
        Currency.UZS: 37160.0,
        Currency.UAH: 139.0,
        Currency.BYN: 9.06,
        Currency.TON: 0.88,
        Currency.STARS: 160.0,
    }
    return minimums.get(currency, 249.0)


def get_minimum_amount_text(currency: Currency) -> str:
    minimums = {
        Currency.RUB: '249 RUB',
        Currency.EUR: '2.69 EUR',
        Currency.KZT: '1 470 KZT',
        Currency.UZS: '37 160 UZS',
        Currency.UAH: '139 UAH',
        Currency.BYN: '9.06 BYN',
        Currency.TON: '0.88 TON',
        Currency.STARS: '160 Stars',
    }
    return minimums.get(currency, '249 RUB')


def build_profile_caption(db_user: User, balances: list[Balance], language: str) -> str:
    not_set = get_localized_text('not_set', language)
    admin_label = ''
    if getattr(db_user, 'role', UserRole.USER) in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        admin_label = '\n👑 Админ'
    return (
        f'{get_localized_text("profile_title", language)}\n'
        f'ID: {db_user.id}\n'
        f'Username: @{db_user.username or not_set}\n'
        f'{get_localized_text("completed_deals", language)}: {db_user.completed_deals or 0}{admin_label}\n\n'
        f'{get_localized_text("balance_title", language)}\n{format_balance(balances) or not_set}\n\n'
        f'{get_localized_text("card_label", language)}: {db_user.card_data or not_set}\n'
        f'{get_localized_text("wallet_label", language)}: {db_user.ton_wallet or not_set}\n'
        f'{get_localized_text("stars_label", language)}: {db_user.stars_recipient or not_set}'
    )


async def get_user_language(session: AsyncSession, user_id: int) -> str:
    cached = LANGUAGE_CACHE.get(user_id)
    if cached:
        return cached
    lang = await SettingsRepository(session).get(f'user_lang:{user_id}')
    resolved = lang or 'ru'
    LANGUAGE_CACHE[user_id] = resolved
    return resolved


async def set_user_language(session: AsyncSession, user_id: int, lang: str) -> None:
    LANGUAGE_CACHE[user_id] = lang
    await SettingsRepository(session).set(f'user_lang:{user_id}', lang)


def get_localized_text(key: str, language: str) -> str:
    texts = {
        'ru': {
            'settings_title': '⚙️ Настройки',
            'settings_text': 'Выберите язык интерфейса.',
            'settings_saved': '✅ Язык интерфейса обновлён.',
            'step3': '💰 <b>Шаг 3/4 — Укажите сумму сделки</b>\n\nВведите только число, без названия валюты.',
            'step4': '📦 <b>Шаг 4/4 — Опишите товар</b>\n\nНапишите, что именно вы передаете покупателю.\n\nЛучше всего — скопируйте ссылку на подарок и используйте ее для описания товара.\n\n<b>Примеры:</b>\n• НФТ Плюшевый Пепе\n• t.me/nft/SnoopDogg-1\n• Редкий BLUR NFT #2847',
            'payment_confirmed_title': '✅ Оплата подтверждена!',
            'payment_confirmed_body': '👤 Покупатель уже оплатил сделку.\n\n📦 Передайте подарок покупателю и нажмите кнопку ниже, когда всё будет готово.',
            'seller_transfer_done': '✅ Вы сообщили о передаче товара.',
            'buyer_transfer_notice': '🎁 Продавец сообщил о передаче товара.\nПроверьте получение.',
            'deal_completed_seller': '✅ Сделка завершена.\n💰 Средства зачислены на ваш баланс.',
            'deal_completed_buyer': '✅ Сделка завершена.\nСпасибо за использование сервиса.',
            'admin_complete_seller': '✅ Сделка одобрена модерацией. Пожалуйста, передайте подарок покупателю.',
            'admin_complete_buyer': '✅ Сделка завершена администратором.',
            'support_prompt': '🆘 Опишите вопрос одним сообщением. Администратор получит уведомление и сможет ответить вам.',
            'support_sent': '✅ Сообщение отправлено в поддержку. Ожидайте ответа.',
            'main_caption': '🔐 <b>NIF TIX</b> — безопасные сделки без лишнего шума.\n\nВыберите действие ниже 👇',
            'create_step1': '🎁 Шаг 1/4 — Выберите тип сделки',
            'create_step2': '🇷🇺 Шаг 2/4 — Выберите валюту',
            'bind_card_prompt': 'Отправьте данные карты, которые будут использоваться для сделок.',
            'bind_wallet_prompt': 'Отправьте TON кошелек, например: EQ...',
            'bind_stars_prompt': 'Отправьте получателя Stars, например: @stars_receiver',
            'card_saved': '✅ Карта сохранена.',
            'wallet_saved': '✅ TON кошелек сохранен.',
            'stars_saved': '✅ Получатель Stars сохранен.',
            'profile_title': '<b>Профиль</b>',
            'completed_deals': 'Завершенных сделок',
            'balance_title': '<b>Баланс</b>',
            'card_label': 'Привязанная карта',
            'wallet_label': 'TON кошелек',
            'stars_label': 'Получатель Stars',
            'not_set': 'не задан',
            'all_balances_title': '<b>Баланс всех валют</b>',
            'back_to_profile_hint': 'Нажмите «Назад», чтобы вернуться к профилю.',
        },
        'en': {
            'settings_title': '⚙️ Settings',
            'settings_text': 'Choose the interface language.',
            'settings_saved': '✅ Interface language updated.',
            'step3': '💰 <b>Step 3/4 — Enter the deal amount</b>\n\nEnter only a number, without the currency name.\n\n<b>Examples:</b>\n• <code>500</code>\n• <code>1500</code>\n• <code>25.5</code>',
            'step4': '📦 <b>Step 4/4 — Describe the item</b>\n\nWrite exactly what you are handing over to the buyer.\n\nBest option — paste the gift link and use it in the description.\n\n<b>Examples:</b>\n• Plush Pepe NFT\n• t.me/nft/SnoopDogg-1\n• Rare BLUR NFT #2847',
            'payment_confirmed_title': '✅ Payment confirmed!',
            'payment_confirmed_body': '👤 The buyer has already paid for the deal.\n\n📦 Please transfer the gift to the buyer and click the button below once it is done.',
            'seller_transfer_done': '✅ You have confirmed that the item was transferred.',
            'buyer_transfer_notice': '🎁 The seller has confirmed the transfer.\nPlease check that you received it.',
            'deal_completed_seller': '✅ The deal is complete.\n💰 Funds have been credited to your balance.',
            'deal_completed_buyer': '✅ The deal is complete.\nThank you for using the service.',
            'admin_complete_seller': '✅ The deal was approved by moderation. Please transfer the gift to the buyer.',
            'admin_complete_buyer': '✅ The deal was completed by the administrator.',
            'support_prompt': '🆘 Describe your issue in one message. An administrator will get a notification and can reply to you.',
            'support_sent': '✅ Your message was sent to support. Please wait for a reply.',
            'main_caption': '🔐 <b>NIF TIX</b> — secure deals without extra noise.\n\nChoose an action below 👇',
            'create_step1': '🎁 Step 1/4 — Choose deal type',
            'create_step2': '🇷🇺 Step 2/4 — Choose currency',
            'bind_card_prompt': 'Send the card details that will be used for deals.',
            'bind_wallet_prompt': 'Send your TON wallet, for example: EQ...',
            'bind_stars_prompt': 'Send the Stars recipient, for example: @stars_receiver',
            'card_saved': '✅ Card saved.',
            'wallet_saved': '✅ TON wallet saved.',
            'stars_saved': '✅ Stars recipient saved.',
            'profile_title': '<b>Profile</b>',
            'completed_deals': 'Completed deals',
            'balance_title': '<b>Balance</b>',
            'card_label': 'Bound card',
            'wallet_label': 'TON wallet',
            'stars_label': 'Stars recipient',
            'not_set': 'not set',
            'all_balances_title': '<b>All currency balances</b>',
            'back_to_profile_hint': 'Press Back to return to your profile.',
        },
    }
    return texts.get(language, texts['ru']).get(key, key)


async def localized_main_menu(session: AsyncSession, user_id: int) -> InlineKeyboardMarkup:
    return main_menu(await get_user_language(session, user_id))


async def localized_profile_menu(session: AsyncSession, user_id: int) -> InlineKeyboardMarkup:
    return profile_menu(await get_user_language(session, user_id))


def admin_user_label(user: User | None, fallback_id: int | None = None) -> str:
    if user and user.username:
        return f'@{user.username}'
    return str(fallback_id if fallback_id is not None else (user.id if user else '-'))


async def schedule_background_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)

    def _log_task_result(task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning('Background task failed: %s', exc)

    task.add_done_callback(_log_task_result)
    await asyncio.sleep(0)
    return task


async def send_messages_concurrently(bot, chat_ids: list[int], text: str, **kwargs) -> int:
    if not chat_ids:
        return 0

    async def _send(chat_id: int) -> bool:
        try:
            await bot.send_message(chat_id, text, **kwargs)
            return True
        except Exception as exc:
            logger.warning('Не удалось отправить сообщение %s: %s', chat_id, exc)
            return False

    results = await asyncio.gather(*(_send(chat_id) for chat_id in chat_ids), return_exceptions=True)
    return sum(1 for result in results if result is True)


async def notify_admins(bot, text: str) -> None:
    admin_ids = list(set(config.ADMIN_IDS) | set(config.SUPER_ADMIN_IDS))
    if not admin_ids:
        return

    await send_messages_concurrently(bot, admin_ids, text)


async def notify_deal_participants(
    bot,
    *,
    seller_id: int | None = None,
    buyer_id: int | None = None,
    seller_text: str | None = None,
    buyer_text: str | None = None,
    seller_kwargs: dict | None = None,
    buyer_kwargs: dict | None = None,
) -> None:
    tasks = []
    if seller_id is not None and seller_text is not None:
        tasks.append(bot.send_message(seller_id, seller_text, **(seller_kwargs or {})))
    if buyer_id is not None and buyer_text is not None:
        tasks.append(bot.send_message(buyer_id, buyer_text, **(buyer_kwargs or {})))
    if not tasks:
        return

    await asyncio.gather(*tasks, return_exceptions=True)


async def check_and_notify_timeout(bot, session: AsyncSession, deal) -> None:
    """Check if deal timeout has expired and notify users"""
    from app.bot.utils import check_deal_timeout

    if not check_deal_timeout(deal):
        return

    if deal.status == DealStatus.REJECTED or deal.status == DealStatus.CANCELLED:
        return

    deal.status = DealStatus.CANCELLED
    await session.commit()

    seller_task = UserRepository(session).get(deal.seller_id)
    buyer_task = UserRepository(session).get(deal.buyer_id) if deal.buyer_id else None
    seller, buyer = await asyncio.gather(seller_task, buyer_task) if buyer_task is not None else (await seller_task, None)

    async def _notify_seller() -> None:
        if not seller:
            return
        try:
            await bot.send_message(
                seller.id,
                f'⏰ <b>Сделка отменена</b>\n\n'
                f'Сделка №{deal.deal_number} отменена по причине: истекло время ожидания оплаты (15 минут).\n\n'
                f'Попробуйте создать новую сделку.',
                parse_mode='HTML'
            )
        except Exception as e:
            logger.warning('Не удалось уведомить продавца: %s', e)

    async def _notify_buyer() -> None:
        if not buyer:
            return
        try:
            await bot.send_message(
                buyer.id,
                f'⏰ <b>Сделка отменена</b>\n\n'
                f'Сделка №{deal.deal_number} отменена по причине: истекло время ожидания оплаты (15 минут).\n\n'
                f'Деньги не были списаны.',
                parse_mode='HTML'
            )
        except Exception as e:
            logger.warning('Не удалось уведомить покупателя: %s', e)

    await asyncio.gather(_notify_seller(), _notify_buyer(), return_exceptions=True)


async def ensure_admin(message: Message, is_admin: bool) -> bool:
    if not is_admin:
        await message.answer('⛔ Недостаточно прав.')
        return False
    return True


async def ensure_super_admin(message: Message, is_super_admin: bool) -> bool:
    if not is_super_admin:
        await message.answer('⛔ Недостаточно прав.')
        return False
    return True


def message_equals(text: str, ignore_case: bool = False):
    def _filter(message: Message) -> bool:
        if not message.text:
            return False
        candidate = message.text.strip()
        target = text.strip()
        return candidate.lower() == target.lower() if ignore_case else candidate == target
    return _filter


def callback_data_startswith(prefix: str):
    def _filter(callback: CallbackQuery) -> bool:
        return bool(callback.data and callback.data.startswith(prefix))
    return _filter


def callback_data_equals(data: str):
    def _filter(callback: CallbackQuery) -> bool:
        return callback.data == data
    return _filter


async def send_main_menu(message: Message, session: AsyncSession | None = None, db_user: User | None = None) -> None:
    language = await get_user_language(session, db_user.id) if session and db_user else 'ru'
    is_admin = bool(db_user and getattr(db_user, 'role', UserRole.USER) in {UserRole.ADMIN, UserRole.SUPER_ADMIN})
    try:
        await message.answer_photo(
            photo=logo_file(),
            caption=get_localized_text('main_caption', language),
            reply_markup=main_menu(language, is_admin),
            parse_mode='HTML',
        )
        return
    except Exception:
        await message.answer(
            get_localized_text('main_caption', language),
            reply_markup=main_menu(language, is_admin),
            parse_mode='HTML',
        )


async def language_callback(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    action = callback.data or ''
    if action not in {'set_lang_ru', 'set_lang_en'}:
        await callback.answer()
        return

    language = 'ru' if action == 'set_lang_ru' else 'en'
    await set_user_language(session, db_user.id, language)
    await session.commit()
    await callback.bot.send_message(
        callback.message.chat.id,
        get_localized_text('settings_saved', language),
        reply_markup=settings_menu(language),
        parse_mode='HTML',
    )
    await callback.answer()


async def menu_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, is_admin: bool, is_super_admin: bool) -> None:
    action = callback.data or ''

    async def replace_message_with_text(text: str, reply_markup: InlineKeyboardMarkup | None = None, parse_mode: str | None = None) -> None:
        if callback.message:
            try:
                await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
                return
            except Exception:
                pass
            try:
                await callback.bot.send_message(callback.message.chat.id, text, reply_markup=reply_markup, parse_mode=parse_mode)
            except Exception:
                await callback.answer(text, show_alert=True)
        else:
            await callback.answer(text, show_alert=True)

    async def replace_message_with_photo(caption: str, reply_markup: InlineKeyboardMarkup | None = None, parse_mode: str | None = None) -> None:
        if callback.message:
            try:
                await callback.message.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
                return
            except Exception:
                pass
            try:
                await callback.bot.send_photo(callback.message.chat.id, photo=logo_file(), caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
            except Exception:
                await callback.answer('Произошла ошибка меню.', show_alert=True)
        else:
            await callback.answer('Произошла ошибка меню.', show_alert=True)

    if action in {'set_lang_ru', 'set_lang_en'}:
        language = 'ru' if action == 'set_lang_ru' else 'en'
        await set_user_language(session, db_user.id, language)
        await session.commit()
        await callback.bot.send_message(
            callback.message.chat.id,
            get_localized_text('settings_saved', language),
            reply_markup=settings_menu(language),
            parse_mode='HTML',
        )
        await callback.answer()
        return
    if action == 'menu_create_deal':
        language = await get_user_language(session, db_user.id)
        await replace_message_with_text(get_localized_text('create_step1', language), deal_type_menu(language))
        await state.set_state(DealCreation.choose_type)
        await callback.answer()
        return
    if action == 'menu_deal_type_gift':
        language = await get_user_language(session, db_user.id)
        await replace_message_with_text(get_localized_text('create_step2', language), deal_currency_menu(language))
        await state.set_state(DealCreation.choose_currency)
        await callback.answer()
        return
    if action == 'menu_admin_panel':
        if not (is_admin or is_super_admin or db_user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}):
            await callback.answer('⛔ Недостаточно прав.', show_alert=True)
            return
        await callback.message.answer('🛠 Админ-панель', reply_markup=admin_panel_menu())
        await callback.answer()
        return
    if action.startswith('menu_currency_'):
        currency_key = action.split('_', 2)[2]
        try:
            currency = Currency[currency_key]
        except KeyError:
            await callback.answer('Неподдерживаемая валюта.')
            return
        await state.update_data(currency=currency.value)
        language = await get_user_language(session, db_user.id)
        await replace_message_with_text(get_localized_text('step3', language), parse_mode='HTML')
        await state.set_state(DealCreation.enter_amount)
        await callback.answer()
        return
    if action == 'menu_how_it_works':
        await replace_message_with_photo(
            '1. Продавец создает сделку\n'
            '2. Покупатель оплачивает\n'
            '3. Администратор подтверждает оплату\n'
            '4. Продавец передает NFT\n'
            '5. Покупатель подтверждает получение\n'
            '6. Деньги зачисляются продавцу\n\n'
            '📖 Подробнее: https://telegra.ph/Kak-bezopasno-provodit-sdelki-cherez-NIFTIX-08-02',
            main_menu(await get_user_language(session, db_user.id)),
            parse_mode='HTML',
        )
        await callback.answer(cache_time=0)
        return
    if action == 'menu_support':
        language = await get_user_language(session, db_user.id)
        await replace_message_with_text(get_localized_text('support_prompt', language))
        await state.set_state(SupportStates.enter_message)
        await callback.answer()
        return
    if action == 'menu_channel':
        await replace_message_with_photo('Our channel: https://t.me/your_channel_link' if await get_user_language(session, db_user.id) == 'en' else 'Наш канал: https://t.me/your_channel_link', main_menu(await get_user_language(session, db_user.id)), parse_mode='HTML')
        await callback.answer()
        return
    if action == 'menu_profile':
        balance_repo = BalanceRepository(session)
        balances = await balance_repo.list_balances(db_user.id)
        language = await get_user_language(session, db_user.id)
        await replace_message_with_photo(
            build_profile_caption(db_user, balances, language),
            profile_menu(language, bool(is_admin or is_super_admin or db_user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN})),
            parse_mode='HTML',
        )
        await callback.answer()
        return
    if action == 'menu_balance':
        balance_repo = BalanceRepository(session)
        balances = await balance_repo.list_balances(db_user.id)
        language = await get_user_language(session, db_user.id)
        await replace_message_with_photo(
            (
                f'{get_localized_text("all_balances_title", language)}\n'
                f'{format_all_balances(balances)}\n\n'
                f'{get_localized_text("back_to_profile_hint", language)}'
            ),
            profile_menu(language),
            parse_mode='HTML',
        )
        await callback.answer()
        return
    if action == 'menu_settings':
        language = await get_user_language(session, db_user.id)
        await replace_message_with_photo(
            f'{get_localized_text("settings_title", language)}\n\n{get_localized_text("settings_text", language)}',
            settings_menu(language),
            parse_mode='HTML',
        )
        await callback.answer()
        return
    if action == 'menu_bind_card':
        language = await get_user_language(session, db_user.id)
        await replace_message_with_text(get_localized_text('bind_card_prompt', language))
        await state.set_state(ProfileUpdate.set_card)
        await callback.answer()
        return
    if action == 'menu_bind_wallet':
        language = await get_user_language(session, db_user.id)
        await replace_message_with_text(get_localized_text('bind_wallet_prompt', language))
        await state.set_state(ProfileUpdate.set_wallet)
        await callback.answer()
        return
    if action == 'menu_bind_stars':
        language = await get_user_language(session, db_user.id)
        await replace_message_with_text(get_localized_text('bind_stars_prompt', language))
        await state.set_state(ProfileUpdate.set_stars)
        await callback.answer()
        return
    if action == 'menu_withdraw':
        balance_repo = BalanceRepository(session)
        balances = await balance_repo.list_balances(db_user.id)
        available_balances = [balance for balance in balances if balance.amount > 0]

        if not available_balances:
            await replace_message_with_photo(
                '💸 На вашем балансе нет доступных средств для вывода.',
                profile_menu(),
                parse_mode='HTML',
            )
            await callback.answer()
            return

        created_requests = []
        missing_requisites = []

        for balance in available_balances:
            currency = balance.currency
            if currency in {Currency.RUB, Currency.EUR, Currency.KZT, Currency.UZS, Currency.UAH, Currency.BYN}:
                if not db_user.card_data:
                    missing_requisites.append('💳 Привяжите карту, чтобы выводить рубли/евро/тенге и другие фиатные валюты.')
                    continue
            elif currency == Currency.TON:
                if not db_user.ton_wallet:
                    missing_requisites.append('💎 Привяжите TON-кошелек, чтобы выводить TON.')
                    continue
            elif currency == Currency.STARS:
                if not db_user.stars_recipient:
                    missing_requisites.append('⭐ Укажите получателя Stars, чтобы выводить Stars.')
                    continue

            created_requests.append(await WithdrawRepository(session).create(db_user.id, currency, float(balance.amount)))

        if created_requests:
            await session.commit()
            await replace_message_with_photo(
                (
                    '✅ <b>Заявка на вывод создана</b>\n\n'
                    '💰 Средства будут обработаны и отправлены в течение <b>48–72 часов</b>.\n\n'
                    '⏳ Обычно вывод занимает 2–3 дня, но иногда может занять чуть больше времени.'
                ),
                profile_menu(),
                parse_mode='HTML',
            )
            await notify_admins(
                callback.bot,
                f'Новая заявка на вывод\nПользователь: @{db_user.username or db_user.id}\nСумма: {sum(float(req.amount) for req in created_requests):.2f} (автоматически из профиля)',
            )
            await callback.answer()
            return

        await replace_message_with_photo(
            (
                '⚠️ <b>Вывод невозможен</b>\n\n'
                f'{"\n".join(missing_requisites)}\n\n'
                'Привяжите нужные реквизиты в профиле и попробуйте ещё раз.'
            ),
            profile_menu(),
            parse_mode='HTML',
        )
        await callback.answer()
        return
    if action == 'menu_cancel' or action == 'menu_back':
        await state.clear()
        await replace_message_with_photo(
            get_localized_text('main_caption', await get_user_language(session, db_user.id)),
            main_menu(await get_user_language(session, db_user.id)),
            parse_mode='HTML',
        )
        await callback.answer()
        return
    await callback.answer()


async def send_profile(message: Message, session: AsyncSession, db_user: User) -> None:
    balance_repo = BalanceRepository(session)
    balances = await balance_repo.list_balances(db_user.id)
    language = await get_user_language(session, db_user.id)
    await message.answer_photo(
        photo=logo_file(),
        caption=build_profile_caption(db_user, balances, language),
        reply_markup=profile_menu(language, bool(db_user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN})),
        parse_mode='HTML',
    )

async def show_help_create(message: Message) -> None:
    await message.answer(
        '1. Нажмите «Создать сделку»\n'
        '2. Выберите валюту\n'
        '3. Укажите сумму\n'
        '4. Опишите NFT или подарок\n'
        '5. Отправьте ссылку покупателю\n'
        '6. Дождитесь оплаты\n'
        '7. Передайте товар\n'
        '8. Получите средства на баланс'
    )


async def show_help_flow(message: Message) -> None:
    await message.answer_photo(
        photo=logo_file(),
        caption=(
            '1. Продавец создает сделку\n'
            '2. Покупатель оплачивает\n'
            '3. Администратор подтверждает оплату\n'
            '4. Продавец передает NFT\n'
            '5. Покупатель подтверждает получение\n'
            '6. Деньги зачисляются продавцу\n\n'
            '📖 Подробнее: https://telegra.ph/Kak-bezopasno-provodit-sdelki-cherez-NIFTIX-08-02'
        ),
        parse_mode='HTML',
    )


async def handle_start(message: Message, session: AsyncSession, db_user: User, payload: Optional[int | str]) -> None:
    deal = None
    deal_repo = DealRepository(session)
    if isinstance(payload, int):
        deal = await deal_repo.get_by_number(payload)
    elif isinstance(payload, str):
        if payload.startswith('deal_') and payload[5:].isdigit():
            deal = await deal_repo.get_by_number(int(payload.split('_', 1)[1]))
        else:
            deal = await deal_repo.get_by_code(payload)
    if deal is not None:
        if deal.seller_id == db_user.id:
            await message.answer('Вы продавец этой сделки. Дождитесь покупателя.', reply_markup=main_menu())
            return
        if deal.buyer_id and deal.buyer_id != db_user.id:
            await message.answer('Эта сделка уже занята другим покупателем.')
            return
        if not deal.buyer_id:
            await deal_repo.assign_buyer(deal, db_user.id)
            await session.commit()
            seller = await UserRepository(session).get(deal.seller_id)
            if seller:
                await message.bot.send_photo(
                    seller.id,
                    photo=logo_file(),
                    caption=(
                        f'🤝 <b>{get_deal_title(deal)}</b>\n\n'
                        f'👤 Покупатель: @{db_user.username or "unknown"}\n'
                        f'🆔 ID: <code>{db_user.id}</code>\n\n'
                        f'📦 Сделок покупателя: {db_user.completed_deals or 0}\n'
                        f'💰 Сумма сделок: {(db_user.total_volume or 0.0):.2f} $\n\n'
                        f'💸 Покупатель должен перевести сумму сделки на реквизиты бота в течение <b>15 минут</b>.\n\n'
                        f'После подтверждения оплаты бот отправит вам уведомление — только тогда передавайте подарок покупателю.\n\n'
                        f'🔒 Сделка завершится только после подтверждения получения товара покупателем.'
                    ),
                    parse_mode='HTML'
                )
        seller = await UserRepository(session).get(deal.seller_id)
        await message.answer(
            (
                f'{get_deal_title(deal)}\n'
                f'🟢 Статус: Покупатель присоединился\n'
                f'🎁 Тип сделки: {deal.deal_type}\n'
                f'👤 Вы покупатель\n'
                f'⏳ У вас есть 15 минут на оплату сделки\n'
                f'📌 Продавец: @{seller.username if seller and seller.username else "продавец"}\n'
                f'📦 Вы покупаете:\n{deal.item_description}\n'
                f'💸 Вы отдаете: {deal.amount:.2f} {deal.currency.value}\n'
                f'💳 Реквизиты бота для оплаты:\n{config.PAYMENT_CARD}\n'
                f'💵 Сумма к оплате: {deal.amount:.2f} {deal.currency.value}\n'
                f'🚨 Комментарий к переводу:\n{deal.payment_comment}\n'
                f'‼️ Укажите обязательный комментарий и точную сумму.'
            ),
            reply_markup=buyer_payment_menu(deal.deal_number),
        )
        return
    await send_main_menu(message, session, db_user)


async def start_deal(message: Message, state: FSMContext) -> None:
    await message.answer('🎁 Шаг 1/4 — Выберите тип сделки', reply_markup=deal_type_menu())
    await state.set_state(DealCreation.choose_type)


async def process_deal_type(message: Message, state: FSMContext) -> None:
    if message.text != '🎁 Подарки':
        await message.answer('Выберите тип сделки из кнопок.', reply_markup=deal_type_menu())
        return
    await message.answer('🇷🇺 Шаг 2/4 — Выберите валюту', reply_markup=deal_currency_menu())
    await state.set_state(DealCreation.choose_currency)


async def process_deal_currency(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    currency = get_currency_by_label(message.text)
    if currency is None:
        await message.answer('Выберите валюту через кнопки.', reply_markup=deal_currency_menu())
        return
    await state.update_data(currency=currency.value)
    language = await get_user_language(session, db_user.id)
    minimum_text = get_minimum_amount_text(currency)
    await message.answer(
        (
            '💰 <b>Шаг 3/4 — Укажите сумму сделки</b>\n\n'
            f'Минимально допустимая сумма для {currency.value}: <b>{minimum_text}</b>\n\n'
            'Введите только число, без названия валюты.'
        ),
        parse_mode='HTML',
    )
    await state.set_state(DealCreation.enter_amount)


async def process_deal_amount(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer('Введите корректную сумму, например: 500 или 25.5')
        return

    data = await state.get_data()
    currency = Currency(data.get('currency', Currency.RUB.value))
    minimum_amount = get_minimum_amount_for_currency(currency)
    if amount < minimum_amount:
        await message.answer(
            f'⚠️ Минимальная сумма сделки — {get_minimum_amount_text(currency)}. Ниже этого значения сделку нельзя создать.',
            reply_markup=deal_currency_menu(),
        )
        return

    await state.update_data(amount=amount)
    language = await get_user_language(session, db_user.id)
    await message.answer(get_localized_text('step4', language), parse_mode='HTML')
    await state.set_state(DealCreation.enter_description)


async def process_deal_description(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    data = await state.get_data()
    currency = Currency(data['currency'])
    amount = data['amount']
    description = message.text.strip()
    if not description:
        await message.answer('Опишите товар, чтобы покупателю было понятно, что вы предлагаете.')
        return
    deal_repo = DealRepository(session)
    deal = await deal_repo.create(db_user.id, currency, amount, description, build_payment_comment())
    await session.commit()

    invite_link = f'https://t.me/{config.BOT_USERNAME}?start={deal.deal_code}'
    share_text = 'Перейди по ссылке, чтобы начать безопасную сделку в NIFTIX'
    share_url = f'https://t.me/share/url?url={quote(invite_link)}&text={quote(share_text)}'
    await message.answer(
        (
            f'✅ Сделка успешно создана\n'
            f'{get_deal_title(deal)}\n'
            f'🎁 Тип: {deal.deal_type}\n'
            f'📦 Товар: {deal.item_description}\n'
            f'💰 Получаете: {deal.amount:.2f} {deal.currency.value}\n\n'
            f'🔗 {share_text}:\n{invite_link}'
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='📤 Поделиться сделкой', url=share_url)],
        ]),
    )
    await state.clear()


async def process_profile_text(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    # This handler only runs when no FSM state is active.
    if message.text == '👤 Мой профиль':
        await send_profile(message, session, db_user)
        return
    if message.text == '💳 Привязать карту':
        await message.answer('Отправьте данные карты, которые будут использоваться для сделок.')
        await state.set_state(ProfileUpdate.set_card)
        return
    if message.text == '💎 Привязать TON кошелек':
        await message.answer('Отправьте TON кошелек, например: EQ...')
        await state.set_state(ProfileUpdate.set_wallet)
        return
    if message.text == '⭐ Указать получателя Stars':
        await message.answer('Отправьте получателя Stars, например: @stars_receiver')
        await state.set_state(ProfileUpdate.set_stars)
        return
    if message.text == '💸 Вывести баланс':
        await message.answer('Выберите валюту для вывода.', reply_markup=deal_currency_menu())
        await state.set_state(WithdrawRequestStates.choose_currency)
        return
    if message.text == '📖 Как создать сделку':
        await show_help_create(message)
        return
    if message.text in {'🛡 Как проходит сделка', '❓ Как проходит сделка?'}:
        await show_help_flow(message)
        return
    if message.text == '📢 Наш канал':
        await message.answer('Наш канал: https://t.me/your_channel_link')
        return
    if message.text == '⚙️ Настройки':
        await message.answer(
            (
                '⚙️ Настройки\n'
                '💳 Привязать карту\n'
                '💎 TON кошелек\n'
                '⭐ Получатель Stars\n'
                '🔔 Уведомления\n'
                '🌐 Язык'
            ),
            reply_markup=profile_menu(),
        )
        return
    if message.text == '💼 Создать сделку':
        await start_deal(message, state)
        return
    await message.answer('Выберите действие из меню.', reply_markup=main_menu())


async def support_message(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    text = (message.text or '').strip()
    if not text:
        await message.answer('Отправьте текстовое сообщение для поддержки.')
        return
    language = await get_user_language(session, db_user.id)
    username = f'@{db_user.username}' if db_user.username else 'username не указан'
    admin_text = (
        '🆘 <b>Новое обращение в поддержку</b>\n\n'
        f'Клиент: {username}\n'
        f'ID: <code>{db_user.id}</code>\n\n'
        f'Сообщение:\n{text}'
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='✉️ Ответить', callback_data=f'support_reply:{db_user.id}')
    ]])
    for admin_id in set(config.ADMIN_IDS) | set(config.SUPER_ADMIN_IDS):
        try:
            await message.bot.send_message(admin_id, admin_text, reply_markup=reply_markup, parse_mode='HTML')
        except Exception:
            logger.warning('Не удалось отправить обращение администратору %s', admin_id)
    await message.answer(get_localized_text('support_sent', language), reply_markup=main_menu())
    await state.clear()


async def support_reply_start(callback: CallbackQuery, state: FSMContext, db_user: User, is_admin: bool, is_super_admin: bool) -> None:
    if not (is_admin or is_super_admin or db_user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}):
        await callback.answer('⛔ Недостаточно прав.')
        return
    _, user_id = parse_callback_data(callback.data or '')
    if not user_id.isdigit():
        await callback.answer('Некорректный пользователь.')
        return
    await state.update_data(support_user_id=int(user_id))
    await callback.message.answer(f'Напишите ответ пользователю {user_id}.')
    await state.set_state(SupportStates.admin_reply)
    await callback.answer()


async def support_reply_send(message: Message, state: FSMContext, db_user: User) -> None:
    if db_user.role not in {UserRole.ADMIN, UserRole.SUPER_ADMIN} and db_user.id not in {*config.ADMIN_IDS, *config.SUPER_ADMIN_IDS}:
        await message.answer('⛔ Недостаточно прав.')
        await state.clear()
        return
    data = await state.get_data()
    user_id = data.get('support_user_id')
    text = (message.text or '').strip()
    if not user_id or not text:
        await message.answer('Ответ не отправлен: нет пользователя или текста.')
        await state.clear()
        return
    await message.bot.send_message(int(user_id), f'🆘 <b>Ответ поддержки</b>\n\n{text}', parse_mode='HTML')
    await message.answer('✅ Ответ отправлен.')
    await state.clear()


async def save_card(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    value = (message.text or '').strip()
    if not value:
        await message.answer('Отправьте непустые реквизиты карты.')
        return
    updated_user = await UserRepository(session).update_requisites(db_user.id, card_data=value)
    if updated_user is not None:
        db_user.card_data = updated_user.card_data
    await session.commit()
    language = await get_user_language(session, db_user.id)
    await message.answer(get_localized_text('card_saved', language), reply_markup=profile_menu(language))
    await state.clear()


async def cancel_fsm(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_main_menu(message)


async def save_wallet(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    value = (message.text or '').strip()
    if not value:
        await message.answer('Отправьте непустой TON кошелек.')
        return
    updated_user = await UserRepository(session).update_requisites(db_user.id, ton_wallet=value)
    if updated_user is not None:
        db_user.ton_wallet = updated_user.ton_wallet
    await session.commit()
    language = await get_user_language(session, db_user.id)
    await message.answer(get_localized_text('wallet_saved', language), reply_markup=profile_menu(language))
    await state.clear()


async def save_stars(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    value = (message.text or '').strip()
    if not value:
        await message.answer('Отправьте непустого получателя Stars.')
        return
    updated_user = await UserRepository(session).update_requisites(db_user.id, stars_recipient=value)
    if updated_user is not None:
        db_user.stars_recipient = updated_user.stars_recipient
    await session.commit()
    language = await get_user_language(session, db_user.id)
    await message.answer(get_localized_text('stars_saved', language), reply_markup=profile_menu(language))
    await state.clear()


async def process_withdraw_currency(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    currency = get_currency_by_label(message.text)
    if currency is None:
        await message.answer('Выберите валюту из меню.', reply_markup=deal_currency_menu())
        return
    balance_repo = BalanceRepository(session)
    balance = await balance_repo.get_balance(db_user.id, currency)
    if not balance or balance.amount <= 0:
        await message.answer('У вас нет средств в этой валюте.', reply_markup=profile_menu())
        await state.clear()
        return
    if currency in {Currency.RUB, Currency.EUR, Currency.KZT, Currency.UZS, Currency.UAH, Currency.BYN} and not db_user.card_data:
        await message.answer('⛔ Чтобы вывести эту валюту, сначала привяжите карту в профиле.', reply_markup=profile_menu())
        await state.clear()
        return
    if currency == Currency.TON and not db_user.ton_wallet:
        await message.answer('⛔ Чтобы вывести TON, сначала привяжите TON кошелек в профиле.', reply_markup=profile_menu())
        await state.clear()
        return
    if currency == Currency.STARS and not db_user.stars_recipient:
        await message.answer('⛔ Чтобы вывести Stars, сначала укажите получателя Stars в профиле.', reply_markup=profile_menu())
        await state.clear()
        return
    await state.update_data(currency=currency.value)
    await message.answer(f'Введите сумму вывода в {currency.value}. Доступно: {balance.amount:.2f}')
    await state.set_state(WithdrawRequestStates.enter_amount)


async def process_withdraw_amount(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    data = await state.get_data()
    currency = Currency(data['currency'])
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer('Введите корректную сумму для вывода.')
        return
    balance_repo = BalanceRepository(session)
    balance = await balance_repo.get_balance(db_user.id, currency)
    if not balance or amount > balance.amount:
        await message.answer('Недостаточно средств для вывода.')
        return
    
    # Show credentials based on currency
    if currency == Currency.TON:
        credentials_text = f'💎 TON кошелек:\n<code>{db_user.ton_wallet}</code>'
    elif currency == Currency.STARS:
        credentials_text = f'⭐ Получатель Stars:\n<code>{db_user.stars_recipient}</code>'
    else:
        # For fiat currencies
        credentials_text = f'💳 Карта:\n<code>{db_user.card_data}</code>'
    
    withdrawal_text = (
        f'<b>Проверьте реквизиты вывода:</b>\n\n'
        f'{credentials_text}\n\n'
        f'<b>Сумма:</b> {amount:.2f} {currency.value}\n\n'
        f'<b>Статус:</b> ⏳ В обработке (24-48 часов)\n\n'
        f'Если реквизиты неверные, отмените и обновите их в профиле.'
    )
    
    await state.update_data(amount=amount, credentials_text=credentials_text)
    await message.answer(withdrawal_text, parse_mode='HTML', reply_markup=withdraw_confirm_menu())
    await state.set_state(WithdrawRequestStates.confirm_withdrawal)


def parse_callback_data(data: str) -> tuple[str, str]:
    parts = data.split(':', 1)
    return parts[0], parts[1] if len(parts) > 1 else ''


async def buyer_paid(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    _, number = parse_callback_data(callback.data)
    deal = await DealRepository(session).get_by_number(int(number))
    if not deal:
        await callback.answer('Сделка не найдена.')
        return
    if deal.status != DealStatus.WAITING_PAYMENT:
        await callback.answer('Невозможно отметить оплату в текущем статусе.')
        return
    payment_repo = PaymentRepository(session)
    await payment_repo.create(deal.id, db_user.id, deal.amount, deal.currency, deal.payment_comment)
    deal.status = DealStatus.PAYMENT_VERIFICATION
    await session.commit()
    await callback.answer('✅ Оплата отмечена. Ожидается проверка.', show_alert=True)
    await schedule_background_task(notify_admins(
        callback.bot,
        f'Новая заявка на проверку оплаты\nСделка №{deal.deal_number}\nПокупатель: @{db_user.username or db_user.id}\nСумма: {deal.amount:.2f} {deal.currency.value}\nКомментарий: {deal.payment_comment}',
    ))


async def seller_transferred(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    _, number = parse_callback_data(callback.data)
    deal = await DealRepository(session).get_by_number(int(number))
    if not deal or deal.seller_id != db_user.id:
        await callback.answer('Сделка не найдена или вы не продавец.')
        return
    if deal.status != DealStatus.AWAITING_TRANSFER:
        await callback.answer('Невозможно передать товар в текущем статусе.')
        return
    deal.status = DealStatus.AWAITING_CONFIRM
    await session.commit()
    seller_lang = await get_user_language(session, deal.seller_id)
    buyer = await UserRepository(session).get(deal.buyer_id)
    await callback.answer(get_localized_text('seller_transfer_done', seller_lang), show_alert=True)
    if buyer:
        await schedule_background_task(notify_deal_participants(
            callback.bot,
            buyer_id=buyer.id,
            buyer_text=get_localized_text('buyer_transfer_notice', await get_user_language(session, buyer.id)),
            buyer_kwargs={'reply_markup': buyer_confirm_menu(deal.deal_number)},
        ))


async def buyer_confirmed(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    _, number = parse_callback_data(callback.data)
    deal = await DealRepository(session).get_by_number(int(number))
    if not deal or deal.buyer_id != db_user.id:
        await callback.answer('Сделка не найдена или вы не покупатель.')
        return
    if deal.status != DealStatus.AWAITING_CONFIRM:
        await callback.answer('Невозможно подтвердить получение в текущем статусе.')
        return
    deal.status = DealStatus.COMPLETED
    seller = await UserRepository(session).get(deal.seller_id)
    if seller:
        await BalanceRepository(session).change(seller.id, deal.currency, deal.amount)
        seller.completed_deals = (seller.completed_deals or 0) + 1
        seller.total_volume = (seller.total_volume or 0.0) + deal.amount
    await session.commit()
    await callback.answer('✅ Сделка завершена.', show_alert=True)
    if seller:
        seller_lang = await get_user_language(session, seller.id)
        await schedule_background_task(callback.bot.send_message(seller.id, get_localized_text('deal_completed_seller', seller_lang)))
    buyer_lang = await get_user_language(session, db_user.id)
    await schedule_background_task(callback.bot.send_message(db_user.id, get_localized_text('deal_completed_buyer', buyer_lang)))


async def confirm_payment(callback: CallbackQuery, session: AsyncSession, db_user: User, is_admin: bool, is_super_admin: bool) -> None:
    if not (is_admin or is_super_admin or db_user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}):
        await callback.answer('⛔ Недостаточно прав.')
        return
    _, payment_id = parse_callback_data(callback.data)
    payment = await session.get(Payment, int(payment_id))
    if not payment:
        await callback.answer('Платеж не найден.')
        return

    deal = getattr(payment, 'deal', None)
    if deal is None and getattr(payment, 'deal_id', None) is not None:
        deal = await session.get(Deal, payment.deal_id)
    if deal is None:
        await callback.answer('Платеж связан с несуществующей сделкой.')
        return

    payment.deal = deal
    payment.deal_id = deal.id

    await check_and_notify_timeout(callback.bot, session, deal)

    if deal.status == DealStatus.CANCELLED:
        await callback.answer('❌ Эта сделка отменена по причине истечения времени ожидания.', show_alert=True)
        return

    if payment.status == PaymentStatus.CONFIRMED:
        deal.status = DealStatus.AWAITING_TRANSFER
        await session.commit()
        await callback.answer('Оплата уже подтверждена.', show_alert=True)
        return

    payment.status = PaymentStatus.CONFIRMED
    deal.status = DealStatus.AWAITING_TRANSFER
    await session.commit()
    seller = await UserRepository(session).get(deal.seller_id)
    buyer = await UserRepository(session).get(payment.buyer_id)
    await callback.answer('Оплата подтверждена.', show_alert=True)
    if seller:
        seller_lang = await get_user_language(session, seller.id)
        await schedule_background_task(callback.bot.send_photo(
            seller.id,
            photo=logo_file(),
            caption=(
                f'✅ <b>{get_localized_text("payment_confirmed_title", seller_lang)}</b>\n\n'
                f'👤 Покупатель: @{buyer.username if buyer and buyer.username else payment.buyer_id}\n'
                f'💰 Сумма: {payment.amount:.2f} {payment.currency.value}\n\n'
                f'{get_localized_text("payment_confirmed_body", seller_lang)}'
            ),
            reply_markup=seller_transfer_menu(deal.deal_number),
            parse_mode='HTML'
        ))


async def reject_payment(callback: CallbackQuery, session: AsyncSession, db_user: User, is_admin: bool, is_super_admin: bool) -> None:
    if not (is_admin or is_super_admin or db_user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}):
        await callback.answer('⛔ Недостаточно прав.')
        return
    _, payment_id = parse_callback_data(callback.data)
    payment = await session.get(Payment, int(payment_id))
    if not payment:
        await callback.answer('Платеж не найден.')
        return
    if not getattr(payment, 'deal', None):
        await callback.answer('Платеж связан с несуществующей сделкой.')
        return
    payment.status = PaymentStatus.REJECTED
    payment.deal.status = DealStatus.REJECTED
    await session.commit()
    await callback.answer('Оплата отклонена.')
    buyer = await UserRepository(session).get(payment.buyer_id)
    if buyer:
        await schedule_background_task(callback.bot.send_message(buyer.id, '⛔ Оплата отклонена администрацией. Проверьте реквизиты и попробуйте снова.'))


async def withdraw_ok(callback: CallbackQuery, session: AsyncSession, db_user: User, is_admin: bool, is_super_admin: bool) -> None:
    if not (is_admin or is_super_admin or db_user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}):
        await callback.answer('⛔ Недостаточно прав.')
        return
    _, request_id = parse_callback_data(callback.data)
    request = await session.get(WithdrawRequest, int(request_id))
    if not request:
        await callback.answer('Заявка не найдена.')
        return
    request.status = WithdrawStatus.COMPLETED
    request.admin_id = db_user.id
    request.processed_at = datetime.utcnow()
    await BalanceRepository(session).change(request.user_id, request.currency, -request.amount)
    await session.commit()
    await callback.answer('Заявка выполнена.')
    user = await UserRepository(session).get(request.user_id)
    if user:
        await schedule_background_task(callback.bot.send_message(user.id, '✅ Заявка на вывод выполнена.'))


async def withdraw_reject(callback: CallbackQuery, session: AsyncSession, db_user: User, is_admin: bool, is_super_admin: bool) -> None:
    if not (is_admin or is_super_admin or db_user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}):
        await callback.answer('⛔ Недостаточно прав.')
        return
    _, request_id = parse_callback_data(callback.data)
    request = await session.get(WithdrawRequest, int(request_id))
    if not request:
        await callback.answer('Заявка не найдена.')
        return
    request.status = WithdrawStatus.REJECTED
    request.admin_id = db_user.id
    request.processed_at = datetime.utcnow()
    await session.commit()
    await callback.answer('Заявка отклонена.')
    user = await UserRepository(session).get(request.user_id)
    if user:
        await schedule_background_task(callback.bot.send_message(user.id, '⛔ Ваша заявка на вывод отклонена.'))


async def confirm_withdraw(callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    data = await state.get_data()
    currency_str = data.get('currency')
    amount = data.get('amount')
    
    if not currency_str or not amount:
        await callback.answer('❌ Ошибка. Попробуйте снова.')
        await state.clear()
        return
    
    try:
        currency = Currency(currency_str)
    except ValueError:
        await callback.answer('❌ Неподдерживаемая валюта.')
        await state.clear()
        return
    
    # Create withdraw request
    withdraw_repo = WithdrawRepository(session)
    request = await withdraw_repo.create(db_user.id, currency, amount)
    await session.commit()
    
    await callback.answer('✅ Заявка принята!', show_alert=True)
    await schedule_background_task(notify_admins(
        callback.bot,
        f'Заявка на вывод\nПользователь: @{db_user.username or db_user.id}\nВалюта: {currency.value}\nСумма: {amount:.2f}',
    ))
    await callback.message.edit_text(
        '✅ Ваша заявка на вывод принята!\n\n'
        '💬 Обработка: 24-48 часов (в редких случаях до 72 часов)\n'
        '🔔 Мы отправим уведомление когда вывод будет завершен.',
        reply_markup=None,
        parse_mode='HTML'
    )
    
    await state.clear()
    


async def cancel_withdraw(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer('❌ Вывод отменен.', show_alert=True)
    await callback.message.delete()


async def admin_panel(message: Message, is_admin: bool) -> None:
    if not await ensure_admin(message, is_admin):
        return
    await message.answer_photo(
        photo=logo_file(),
        caption='Админ-панель',
        reply_markup=admin_panel_menu(),
    )


async def list_deals(message: Message, is_admin: bool, session: AsyncSession) -> None:
    if not await ensure_admin(message, is_admin):
        return
    deals = await DealRepository(session).list_recent(20)
    if not deals:
        await message.answer('Сделок пока нет.')
        return
    await message.answer('\n'.join(f'№{deal.deal_number} ({deal.deal_code}) | {format_deal_status(deal.status)}' for deal in deals))


async def show_deal(message: Message, is_admin: bool, session: AsyncSession) -> None:
    if not await ensure_admin(message, is_admin):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer('Используйте /deal ID')
        return
    deal = await DealRepository(session).get_by_number(int(parts[1]))
    if not deal:
        await message.answer('Сделка не найдена.')
        return
    seller = await UserRepository(session).get(deal.seller_id)
    buyer = await UserRepository(session).get(deal.buyer_id) if deal.buyer_id else None
    await message.answer(
        (
            f'№{deal.deal_number} ({deal.deal_code})\n'
            f'Продавец: @{seller.username if seller and seller.username else deal.seller_id}\n'
            f'Покупатель: @{buyer.username if buyer and buyer.username else deal.buyer_id or "не задан"}\n'
            f'\nСумма: {deal.amount:.2f} {deal.currency.value}\n'
            f'Описание: {deal.item_description}\n'
            f'Статус: {format_deal_status(deal.status)}\n'
            f'Дата: {deal.created_at.strftime("%Y-%m-%d %H:%M:%S")}'
        )
    )


async def list_payments(message: Message, is_admin: bool, session: AsyncSession) -> None:
    if not await ensure_admin(message, is_admin):
        return
    payments = await PaymentRepository(session).list_waiting()
    if not payments:
        await message.answer('Нет оплат на проверку.')
        return
    for payment in payments:
        # Check if deal has timed out
        await check_and_notify_timeout(message.bot, session, payment.deal)
        
        # Skip if deal was cancelled due to timeout
        if payment.deal.status == DealStatus.CANCELLED:
            continue
        
        buyer = await UserRepository(session).get(payment.buyer_id)
        await message.answer(
            (
                f'Оплата #{payment.id}\n'
                f'Сделка: {payment.deal.deal_number}\n'
                f'Покупатель: @{buyer.username if buyer and buyer.username else payment.buyer_id}\n'
                f'Сумма: {payment.amount:.2f} {payment.currency.value}\n'
                f'Комментарий: {payment.comment}'
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='✅ Подтвердить оплату', callback_data=f'confirm_payment:{payment.id}')],
                [InlineKeyboardButton(text='❌ Отклонить оплату', callback_data=f'reject_payment:{payment.id}')],
            ]),
        )


async def list_withdraws(message: Message, is_admin: bool, session: AsyncSession) -> None:
    if not await ensure_admin(message, is_admin):
        return
    requests = await WithdrawRepository(session).list_pending()
    if not requests:
        await message.answer('Нет заявок на вывод.')
        return
    for request in requests:
        user = await UserRepository(session).get(request.user_id)
        await message.answer(
            (
                f'Вывод #{request.id}\n'
                f'Пользователь: @{user.username if user and user.username else request.user_id}\n'
                f'Валюта: {request.currency.value}\n'
                f'Сумма: {request.amount:.2f}'
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='✅ Выполнено', callback_data=f'withdraw_ok:{request.id}')],
                [InlineKeyboardButton(text='❌ Отклонено', callback_data=f'withdraw_reject:{request.id}')],
            ]),
        )


async def list_users(message: Message, is_admin: bool, session: AsyncSession) -> None:
    if not await ensure_admin(message, is_admin):
        return
    users = await session.execute(select(User).limit(20))
    items = users.scalars().all()
    if not items:
        await message.answer('Пользователей нет.')
        return
    await message.answer('\n'.join(f'{user.id} | @{user.username or "-"} | {user.completed_deals} сделок' for user in items))


async def show_user(message: Message, is_admin: bool, session: AsyncSession) -> None:
    if not await ensure_admin(message, is_admin):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer('Используйте /user USER_ID')
        return
    user = await UserRepository(session).get(int(parts[1]))
    if not user:
        await message.answer('Пользователь не найден.')
        return
    balance_repo = BalanceRepository(session)
    balances = await balance_repo.list_balances(user.id)
    await message.answer(
        (
            f'ID: {user.id}\n'
            f'Username: @{user.username or "-"}\n'
            f'Дата регистрации: {user.registered_at.strftime("%Y-%m-%d %H:%M:%S")}\n'
            f'Количество сделок: {user.completed_deals}\n'
            f'Сумма сделок: {user.total_volume:.2f}\n'
            f'Баланс:\n{format_balance(balances)}\n'
            f'Статус: {"Заблокирован" if user.blocked else "Активен"}'
        )
    )


async def stats(message: Message, is_admin: bool, session: AsyncSession) -> None:
    if not await ensure_admin(message, is_admin):
        return
    total_users = await session.scalar(select(func.count()).select_from(User))
    active_users = await session.scalar(select(func.count()).select_from(User).where(User.blocked == False))
    total_deals = await session.scalar(select(func.count()).select_from(Deal))
    completed_deals = await session.scalar(select(func.count()).select_from(Deal).where(Deal.status == DealStatus.COMPLETED))
    withdraw_count = await session.scalar(select(func.count()).select_from(WithdrawRequest))
    rows = await session.execute(select(User.id, User.registered_at, User.completed_deals, User.total_volume).limit(10))
    recent_users = rows.all()
    await message.answer(
        (
            '📊 <b>Статистика</b>\n'
            '━━━━━━━━━━━━━━━━━━━━━━\n'
            f'👥 Пользователей: <b>{total_users or 0}</b>\n'
            f'🟢 Активных: <b>{active_users or 0}</b>\n'
            f'🧾 Сделок: <b>{total_deals or 0}</b>\n'
            f'✅ Завершено: <b>{completed_deals or 0}</b>\n'
            f'💸 Выводов: <b>{withdraw_count or 0}</b>\n\n'
            '<b>🔝 Новые пользователи</b>\n' +
            '\n'.join(f'{user_id} • {registered_at.strftime("%d.%m.%Y")}' for user_id, registered_at, *_ in recent_users) +
            '\n\n' +
            '⏱️ Выберите период в кнопках ниже.'
        ),
        reply_markup=stats_period_menu(),
        parse_mode='HTML',
    )


async def block_user(message: Message, is_admin: bool, session: AsyncSession) -> None:
    if not await ensure_admin(message, is_admin):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer('Используйте /block USER_ID')
        return
    await UserRepository(session).block(int(parts[1]), blocked=True)
    await session.commit()
    await message.answer(f'Пользователь {parts[1]} заблокирован.')


async def unblock_user(message: Message, is_admin: bool, session: AsyncSession) -> None:
    if not await ensure_admin(message, is_admin):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer('Используйте /unblock USER_ID')
        return
    await UserRepository(session).block(int(parts[1]), blocked=False)
    await session.commit()
    await message.answer(f'Пользователь {parts[1]} разблокирован.')


async def logs(message: Message, is_admin: bool, session: AsyncSession) -> None:
    if not await ensure_admin(message, is_admin):
        return
    rows = await AdminLogRepository(session).recent(20)
    if not rows:
        await message.answer('Логов нет.')
        return
    await message.answer('\n'.join(f'{row.created_at.strftime("%Y-%m-%d %H:%M")}: {row.action}' for row in rows))


async def cancel_deal(message: Message, is_admin: bool, session: AsyncSession) -> None:
    if not await ensure_admin(message, is_admin):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer('Используйте /canceldeal DEAL_ID')
        return
    deal = await DealRepository(session).get_by_number(int(parts[1]))
    if not deal:
        await message.answer('Сделка не найдена.')
        return
    deal.status = DealStatus.CANCELLED
    await session.commit()
    await message.answer(f'Сделка №{deal.deal_number} отменена.')


async def finish_deal(message: Message, is_admin: bool, session: AsyncSession) -> None:
    if not await ensure_admin(message, is_admin):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer('Используйте /finishdeal DEAL_ID')
        return
    deal = await DealRepository(session).get_by_number(int(parts[1]))
    if not deal:
        await message.answer('Сделка не найдена.')
        return
    if deal.status == DealStatus.COMPLETED:
        await message.answer('Сделка уже завершена.')
        return
    seller = await UserRepository(session).get(deal.seller_id)
    if seller:
        await BalanceRepository(session).change(seller.id, deal.currency, deal.amount)
        seller.completed_deals = (seller.completed_deals or 0) + 1
        seller.total_volume = (seller.total_volume or 0.0) + deal.amount
    deal.status = DealStatus.COMPLETED
    await session.commit()
    await message.answer(f'Сделка №{deal.deal_number} принудительно завершена.')


async def add_admin(message: Message, is_super_admin: bool, session: AsyncSession) -> None:
    if not await ensure_super_admin(message, is_super_admin):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer('Используйте /addadmin USER_ID')
        return
    await UserRepository(session).set_role(int(parts[1]), UserRole.ADMIN)
    await session.commit()
    await message.answer(f'Пользователь {parts[1]} назначен администратором.')


async def remove_admin(message: Message, is_super_admin: bool, session: AsyncSession) -> None:
    if not await ensure_super_admin(message, is_super_admin):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer('Используйте /removeadmin USER_ID')
        return
    await UserRepository(session).set_role(int(parts[1]), UserRole.USER)
    await session.commit()
    await message.answer(f'Пользователь {parts[1]} удален из администраторов.')


async def add_balance_to_user(message: Message, is_admin: bool, is_super_admin: bool, session: AsyncSession, db_user: User) -> None:
    if not (is_admin or is_super_admin or db_user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}):
        await message.answer('⛔ Недостаточно прав.')
        return

    parts = (message.text or '').split()
    if not parts:
        await message.answer('Используйте: /addbalance USER_ID CURRENCY AMOUNT или /selfbalance CURRENCY AMOUNT')
        return

    target_id = db_user.id
    currency_token = None
    amount_token = None

    if parts[0].lower() in {'/addbalance', '/selfbalance'}:
        if parts[0].lower() == '/selfbalance':
            if len(parts) < 3:
                await message.answer('Используйте: /selfbalance CURRENCY AMOUNT')
                return
            currency_token = parts[1]
            amount_token = parts[2]
        else:
            if len(parts) < 4:
                await message.answer('Используйте: /addbalance USER_ID CURRENCY AMOUNT')
                return
            if not parts[1].isdigit():
                await message.answer('USER_ID должен быть числом.')
                return
            target_id = int(parts[1])
            currency_token = parts[2]
            amount_token = parts[3]
    else:
        if len(parts) < 3:
            await message.answer('Используйте: /addbalance USER_ID CURRENCY AMOUNT или /selfbalance CURRENCY AMOUNT')
            return
        if parts[0].isdigit():
            target_id = int(parts[0])
            currency_token = parts[1]
            amount_token = parts[2]
        else:
            currency_token = parts[0]
            amount_token = parts[1]

    try:
        currency = Currency[currency_token.upper()]
    except KeyError:
        alias = currency_token.upper()
        if alias == 'STARS':
            currency = Currency.STARS
        else:
            await message.answer('Неподдерживаемая валюта. Примеры: RUB, EUR, TON, STARS.')
            return

    try:
        amount = float(amount_token.replace(',', '.'))
    except ValueError:
        await message.answer('Сумма должна быть числом.')
        return

    if amount <= 0:
        await message.answer('Сумма должна быть больше нуля.')
        return

    user = await UserRepository(session).get(target_id)
    if user is None:
        user = await UserRepository(session).create_or_update(target_id, None, None)

    await BalanceRepository(session).change(target_id, currency, amount)
    await session.commit()
    await message.answer(
        f'✅ Баланс обновлён: пользователь {target_id} получил +{amount:.2f} {currency.value}.',
        reply_markup=main_menu(),
    )


async def export_db_file(session: AsyncSession) -> Path:
    import json
    from tempfile import gettempdir

    def _clean_value(value):
        if isinstance(value, enum.Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def _row_to_dict(row) -> dict:
        return {
            column.name: _clean_value(getattr(row, column.name))
            for column in row.__table__.columns
        }

    data = {}
    for model in [User, Deal, Payment, WithdrawRequest, Balance]:
        if hasattr(session, 'store'):
            rows = list(session._iter_model_rows(model))
        else:
            result = await session.execute(select(model))
            rows = result.scalars().all()
        data[model.__tablename__] = [_row_to_dict(row) for row in rows]
    filename = Path(gettempdir()) / f'db_export_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.json'

    def _write_json(path: Path, payload: dict) -> None:
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, default=str, ensure_ascii=False, indent=2)

    await asyncio.to_thread(_write_json, filename, data)
    return filename


async def export_db(message: Message, is_super_admin: bool, session: AsyncSession) -> None:
    if not await ensure_super_admin(message, is_super_admin):
        return
    filename = await export_db_file(session)
    await message.answer_document(FSInputFile(str(filename)), caption='📦 Выгрузка базы данных')


async def whoami(message: Message, session: AsyncSession, db_user: User, is_admin: bool, is_super_admin: bool) -> None:
    """Return numeric id, username and admin flags for the caller."""
    await message.answer(
        (
            f'Ваш id: {db_user.id}\n'
            f'Username: @{db_user.username or "не указан"}\n'
            f'Роль: {getattr(db_user, "role", "user")}\n'
            f'В админах: {bool(is_admin)}\n'
            f'В суперадминах: {bool(is_super_admin)}'
        ),
        reply_markup=main_menu(),
    )


async def broadcast_text(message: Message, state: FSMContext, db_user: User) -> None:
    if db_user.role not in {UserRole.ADMIN, UserRole.SUPER_ADMIN} and db_user.id not in {*config.ADMIN_IDS, *config.SUPER_ADMIN_IDS}:
        await message.answer('⛔ Недостаточно прав.')
        await state.clear()
        return
    await state.update_data(broadcast_text=message.text)
    await message.answer('Текст принят. Напишите Да для подтверждения.')
    await state.set_state(BroadcastStates.confirm)


async def broadcast_confirm(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    if db_user.role not in {UserRole.ADMIN, UserRole.SUPER_ADMIN} and db_user.id not in {*config.ADMIN_IDS, *config.SUPER_ADMIN_IDS}:
        await message.answer('⛔ Недостаточно прав.')
        await state.clear()
        return

    confirmation = (message.text or '').strip().lower()
    if confirmation not in {'да', 'yes', 'y', 'confirm'}:
        await message.answer('Для подтверждения напишите «Да» или «Yes».')
        return

    data = await state.get_data()
    text = data.get('broadcast_text')
    if not text:
        await message.answer('Нет текста для рассылки.')
        await state.clear()
        return

    rows = await session.execute(select(User))
    users = rows.scalars().all()
    recipients = []
    for user in users:
        blocked_value = getattr(user, 'blocked', False)
        if isinstance(blocked_value, str):
            blocked_value = blocked_value.strip().lower() in {'1', 'true', 'yes', 'y'}
        if blocked_value:
            continue
        recipients.append(int(user.id))
    recipients = sorted(set(recipients))
    sent = await send_messages_concurrently(message.bot, recipients, text)
    await message.answer(f'✅ Рассылка отправлена {sent} пользователям.')
    await state.clear()


async def direct_user_broadcast(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    if db_user.role not in {UserRole.ADMIN, UserRole.SUPER_ADMIN} and db_user.id not in {*config.ADMIN_IDS, *config.SUPER_ADMIN_IDS}:
        await message.answer('⛔ Недостаточно прав.')
        await state.clear()
        return
    data = await state.get_data()
    target_user_id = data.get('target_user_id')
    if not target_user_id:
        await message.answer('Тема сообщения не найдена. Повторите попытку.')
        await state.clear()
        return
    text = message.text or ''
    try:
        await message.bot.send_message(target_user_id, f'📣 <b>Сообщение от администрации</b>\n\n{text}', parse_mode='HTML')
    except Exception:
        await message.answer('Не удалось отправить сообщение этому пользователю.')
        await state.clear()
        return
    await message.answer(f'✅ Сообщение отправлено пользователю #{target_user_id}.')
    await state.clear()


async def is_user_online(session: AsyncSession, user_id: int, window_seconds: int = 180) -> bool:
    seen_value = await SettingsRepository(session).get(f'user_seen:{user_id}')
    if not seen_value:
        return False
    try:
        seen_at = datetime.fromisoformat(seen_value)
    except ValueError:
        return False
    return (datetime.utcnow() - seen_at).total_seconds() <= window_seconds


async def import_db_payload(session: AsyncSession, payload: dict) -> dict[str, int]:
    def _enum(enum_cls, value):
        if isinstance(value, enum_cls):
            return value
        if value in enum_cls.__members__:
            return enum_cls[value]
        return enum_cls(value)

    def _dt(value):
        if not value or isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    counts = {'users': 0, 'deals': 0, 'payments': 0, 'withdraw_requests': 0, 'balances': 0}
    for key, rows in (payload or {}).items():
        if key == 'users':
            for row in rows:
                user_id = int(row.get('id'))
                existing = await UserRepository(session).get(user_id)
                if existing is None:
                    existing = User(id=user_id)
                    session.add(existing)
                existing.username = row.get('username')
                existing.full_name = row.get('full_name')
                existing.card_data = row.get('card_data')
                existing.ton_wallet = row.get('ton_wallet')
                existing.stars_recipient = row.get('stars_recipient')
                existing.completed_deals = int(row.get('completed_deals') or 0)
                existing.total_volume = float(row.get('total_volume') or 0.0)
                existing.blocked = bool(row.get('blocked'))
                role_value = row.get('role')
                if role_value == 'super_admin':
                    existing.role = UserRole.SUPER_ADMIN
                elif role_value == 'admin':
                    existing.role = UserRole.ADMIN
                else:
                    existing.role = UserRole.USER
                registered_at = _dt(row.get('registered_at'))
                if registered_at:
                    existing.registered_at = registered_at
                counts['users'] += 1
        elif key == 'deals':
            for row in rows:
                deal_id = row.get('id')
                deal = await session.get(Deal, int(deal_id)) if deal_id is not None else None
                if deal is None and row.get('deal_number') is not None:
                    existing = await DealRepository(session).get_by_number(int(row.get('deal_number')))
                    deal = existing
                if deal is None:
                    deal = Deal()
                    if deal_id is not None:
                        deal.id = int(deal_id)
                    session.add(deal)
                deal.deal_number = int(row.get('deal_number') or deal.id or 0)
                deal.deal_code = row.get('deal_code') or ''
                deal.seller_id = int(row.get('seller_id'))
                deal.buyer_id = int(row.get('buyer_id')) if row.get('buyer_id') is not None else None
                deal.deal_type = row.get('deal_type') or 'gift'
                deal.currency = _enum(Currency, row.get('currency'))
                deal.amount = float(row.get('amount') or 0.0)
                deal.item_description = row.get('item_description') or ''
                deal.status = _enum(DealStatus, row.get('status') or DealStatus.CREATED.value)
                deal.payment_comment = row.get('payment_comment')
                deal.created_at = _dt(row.get('created_at')) or datetime.utcnow()
                deal.updated_at = _dt(row.get('updated_at')) or datetime.utcnow()
                counts['deals'] += 1
        elif key == 'payments':
            for row in rows:
                payment_id = row.get('id')
                payment = await session.get(Payment, int(payment_id)) if payment_id is not None else None
                if payment is None:
                    payment = Payment()
                    if payment_id is not None:
                        payment.id = int(payment_id)
                    session.add(payment)
                payment.deal_id = int(row.get('deal_id'))
                payment.buyer_id = int(row.get('buyer_id'))
                payment.amount = float(row.get('amount') or 0.0)
                payment.currency = _enum(Currency, row.get('currency'))
                payment.comment = row.get('comment') or ''
                payment.status = _enum(PaymentStatus, row.get('status') or PaymentStatus.WAITING.value)
                payment.admin_id = int(row.get('admin_id')) if row.get('admin_id') is not None else None
                payment.created_at = _dt(row.get('created_at')) or datetime.utcnow()
                counts['payments'] += 1
        elif key == 'withdraw_requests':
            for row in rows:
                request_id = row.get('id')
                request = await session.get(WithdrawRequest, int(request_id)) if request_id is not None else None
                if request is None:
                    request = WithdrawRequest()
                    if request_id is not None:
                        request.id = int(request_id)
                    session.add(request)
                request.user_id = int(row.get('user_id'))
                request.currency = _enum(Currency, row.get('currency'))
                request.amount = float(row.get('amount') or 0.0)
                request.status = _enum(WithdrawStatus, row.get('status') or WithdrawStatus.PENDING.value)
                request.admin_id = int(row.get('admin_id')) if row.get('admin_id') is not None else None
                request.created_at = _dt(row.get('created_at')) or datetime.utcnow()
                request.processed_at = _dt(row.get('processed_at'))
                request.note = row.get('note')
                counts['withdraw_requests'] += 1
        elif key == 'balances':
            for row in rows:
                user_id = int(row.get('user_id'))
                currency = _enum(Currency, row.get('currency'))
                balance = await BalanceRepository(session).get_balance(user_id, currency)
                if balance is None:
                    balance = Balance(user_id=user_id, currency=currency, amount=0.0)
                    if row.get('id') is not None:
                        balance.id = int(row.get('id'))
                    session.add(balance)
                balance.amount = float(row.get('amount') or 0.0)
                counts['balances'] += 1
    await session.commit()
    return counts


async def import_db_from_message(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    if db_user.role not in {UserRole.ADMIN, UserRole.SUPER_ADMIN} and db_user.id not in {*config.ADMIN_IDS, *config.SUPER_ADMIN_IDS}:
        await message.answer('⛔ Недостаточно прав.')
        await state.clear()
        return
    if not message.document:
        await message.answer('📥 Пришлите файл JSON с экспортом базы данных.')
        return

    try:
        file = await message.bot.get_file(message.document.file_id)
        raw = await message.bot.download_file(file.file_path)
        if hasattr(raw, 'read'):
            raw = await asyncio.to_thread(raw.read)
        if isinstance(raw, str):
            decoded = raw
        else:
            decoded = await asyncio.to_thread(bytes(raw).decode, 'utf-8-sig')
        payload = await asyncio.to_thread(__import__('json').loads, decoded)
    except Exception:
        await message.answer('❌ Файл должен быть корректным JSON-экспортом базы данных.')
        await state.clear()
        return

    normalized = payload if isinstance(payload, dict) else {}
    if not isinstance(normalized, dict):
        await message.answer('❌ Файл не является корректным экспортом базы данных. Используйте экспорт из этого бота.')
        await state.clear()
        return

    valid_export = False
    for key in ('users', 'balances', 'deals', 'payments', 'withdraw_requests'):
        if key in normalized and isinstance(normalized.get(key), list):
            valid_export = True
            break
    if not valid_export:
        for nested in (normalized.get('data'), normalized.get('export'), normalized.get('records')):
            if isinstance(nested, dict):
                for key in ('users', 'balances', 'deals', 'payments', 'withdraw_requests'):
                    if key in nested and isinstance(nested.get(key), list):
                        normalized[key] = nested[key]
                        valid_export = True
                        break
            if valid_export:
                break

    if not valid_export:
        await message.answer('❌ Файл не является корректным экспортом базы данных. Используйте экспорт из этого бота.')
        await state.clear()
        return

    counts = await import_db_payload(session, normalized)
    await message.answer(
        '✅ Импорт базы данных выполнен успешно: '
        f'пользователей {counts.get("users", 0)}, '
        f'сделок {counts.get("deals", 0)}, '
        f'оплат {counts.get("payments", 0)}, '
        f'заявок на вывод {counts.get("withdraw_requests", 0)}, '
        f'балансов {counts.get("balances", 0)}.'
    )
    await state.clear()


async def admin_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, is_admin: bool, is_super_admin: bool) -> None:
    # Handle admin panel inline buttons
    if not (is_admin or is_super_admin or db_user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}):
        await callback.answer('⛔ Недостаточно прав.')
        return
    data = callback.data or ''

    if data.startswith('admin_stats:'):
        period = data.split(':', 1)[1]
        cutoff = None
        if period == '7d':
            cutoff = datetime.utcnow() - timedelta(days=7)
        elif period == '30d':
            cutoff = datetime.utcnow() - timedelta(days=30)
        elif period == '90d':
            cutoff = datetime.utcnow() - timedelta(days=90)

        total_users = await session.scalar(select(func.count()).select_from(User))
        active_users = await session.scalar(select(func.count()).select_from(User).where(User.blocked == False))
        total_deals = await session.scalar(select(func.count()).select_from(Deal))
        completed_deals = await session.scalar(select(func.count()).select_from(Deal).where(Deal.status == DealStatus.COMPLETED))
        withdraw_count = await session.scalar(select(func.count()).select_from(WithdrawRequest))
        if cutoff is not None:
            new_users = await session.scalar(select(func.count()).select_from(User).where(User.registered_at >= cutoff))
            new_deals = await session.scalar(select(func.count()).select_from(Deal).where(Deal.created_at >= cutoff))
            new_payments = await session.scalar(select(func.count()).select_from(Payment).where(Payment.created_at >= cutoff))
        else:
            new_users = total_users
            new_deals = total_deals
            new_payments = await session.scalar(select(func.count()).select_from(Payment))

        await callback.message.answer(
            '📊 <b>Статистика</b>\n'
            '━━━━━━━━━━━━━━━━━━━━━━\n'
            f'👥 Пользователей: <b>{total_users or 0}</b>\n'
            f'🟢 Активных: <b>{active_users or 0}</b>\n'
            f'🧾 Сделок: <b>{total_deals or 0}</b>\n'
            f'✅ Завершено: <b>{completed_deals or 0}</b>\n'
            f'💸 Выводов: <b>{withdraw_count or 0}</b>\n'
            f'🔥 Новые за период: <b>{new_users or 0}</b>\n'
            f'🆕 Сделки за период: <b>{new_deals or 0}</b>\n'
            f'💳 Платежей за период: <b>{new_payments or 0}</b>',
            parse_mode='HTML',
            reply_markup=stats_period_menu(),
        )
        await callback.answer()
        return
    if data == 'admin_users':
        users = list(await UserRepository(session).search('', limit=30))
        if not users:
            await callback.message.answer('👥 Пользователей нет.\nПроверьте, что бот видит аккаунты в текущей сессии и БД.')
        else:
            lines = []
            for user in users:
                badge = '🟢' if await is_user_online(session, user.id) else '🔴'
                status = 'заблок.' if getattr(user, 'blocked', False) else 'онлайн' if badge == '🟢' else 'офлайн'
                action_text = f'{badge} {user.id} | @{user.username or "-"} | {user.completed_deals or 0} сделок | {status}'
                lines.append(action_text)
            await callback.message.answer('👥 <b>Пользователи</b>\n' + '\n'.join(lines), parse_mode='HTML', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🛠️ Управление пользователями', callback_data='admin_users_manage')]]))
        await callback.answer()
        return
    if data == 'admin_users_manage':
        users = list(await UserRepository(session).search('', limit=30))
        if not users:
            await callback.message.answer('Пользователей нет.')
            await callback.answer()
            return
        keyboard_rows = []
        for user in users:
            keyboard_rows.append([InlineKeyboardButton(text=f'{"🔴" if user.blocked else "🟢"} {user.username or user.id}', callback_data=f'user_profile_action:{user.id}')])
        await callback.message.answer('👥 Выберите пользователя для действий:', reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
        await callback.answer()
        return
    if data.startswith('user_profile_action:'):
        target_id = int(data.split(':', 1)[1])
        user = await UserRepository(session).get(target_id)
        if not user:
            await callback.answer('Пользователь не найден.', show_alert=True)
            return
        await callback.message.answer(
            f'👤 Пользователь #{user.id}\n@{user.username or "-"}\nСтатус: {"заблокирован" if user.blocked else "активен"}',
            reply_markup=user_action_menu(user.id, bool(user.blocked)),
        )
        await callback.answer()
        return
    if data.startswith('user_action:'):
        parts = data.split(':')
        if len(parts) < 3:
            await callback.answer('Некорректная команда.', show_alert=True)
            return
        action = parts[1]
        target_id = int(parts[2])
        target_user = await UserRepository(session).get(target_id)
        if target_user is None:
            await callback.answer('Пользователь не найден.', show_alert=True)
            return

        if action == 'block':
            await UserRepository(session).block(target_id, True)
            await session.commit()
            await callback.message.answer(f'🔒 Пользователь {target_id} заблокирован.')
            await callback.answer('Пользователь заблокирован.')
            return
        if action == 'unblock':
            await UserRepository(session).block(target_id, False)
            await session.commit()
            await callback.message.answer(f'🔓 Пользователь {target_id} разблокирован.')
            await callback.answer('Пользователь разблокирован.')
            return
        if action == 'activity':
            seen = await SettingsRepository(session).get(f'user_seen:{target_id}')
            if not seen:
                last_seen = 'никогда'
            else:
                try:
                    last_seen = datetime.fromisoformat(seen).strftime('%d.%m.%Y %H:%M')
                except ValueError:
                    last_seen = seen
            stats_text = (
                f'📈 Активность пользователя #{target_id}\n'
                f'@{target_user.username or "-"}\n'
                f'Последняя активность: {last_seen}\n'
                f'Сделок завершено: {target_user.completed_deals or 0}\n'
                f'Общий объём: {(target_user.total_volume or 0.0):.2f}'
            )
            await callback.message.answer(stats_text)
            await callback.answer()
            return
        if action == 'broadcast':
            await state.update_data(target_user_id=target_id)
            await callback.message.answer('📣 Напишите сообщение, которое будет отправлено этому пользователю.')
            await state.set_state(AdminUserBroadcastStates.wait_message)
            await callback.answer()
            return
        if action == 'add_money':
            if len(parts) < 5:
                await callback.answer('Неверные параметры.', show_alert=True)
                return
            currency_name = parts[3]
            amount_value = float(parts[4])
            try:
                currency = Currency[currency_name.upper()]
            except KeyError:
                currency = Currency.STARS if currency_name.upper() == 'STARS' else Currency.RUB
            await BalanceRepository(session).change(target_id, currency, amount_value)
            await session.commit()
            await callback.message.answer(f'✅ Пользователю {target_id} начислено {amount_value:.2f} {currency.value}.')
            await callback.answer('Средства начислены.')
            return
    if data == 'admin_balances':
        result = await session.execute(select(Balance).limit(50))
        balances = result.scalars().all()
        if not balances:
            await callback.message.answer('Балансы отсутствуют.')
        else:
            lines = []
            for balance in balances:
                user = await UserRepository(session).get(balance.user_id)
                lines.append(f'{admin_user_label(user, balance.user_id)} | {balance.amount:.2f} {balance.currency.value}')
            await callback.message.answer('💰 <b>Балансы</b>\n' + '\n'.join(lines), parse_mode='HTML')
        await callback.answer()
        return
    if data == 'admin_blocked':
        result = await session.execute(select(User).where(User.blocked.is_(True)).limit(50))
        users = result.scalars().all()
        if not users:
            await callback.message.answer('Заблокированных пользователей нет.')
        else:
            await callback.message.answer('🚫 <b>Заблокированные</b>\n' + '\n'.join(
                f'{user.id} | @{user.username or "-"}' for user in users
            ), parse_mode='HTML')
        await callback.answer()
        return
    if data == 'admin_settings':
        await callback.message.answer(
            '⚙️ <b>Админ-настройки</b>\n\n'
            '/addadmin USER_ID — добавить админа\n'
            '/removeadmin USER_ID — удалить админа\n'
            '/block USER_ID — заблокировать\n'
            '/unblock USER_ID — разблокировать\n'
            '/exportdb — выгрузить базу данных',
            parse_mode='HTML',
        )
        await callback.answer()
        return
    if data == 'admin_payments':
        payments = await PaymentRepository(session).list_waiting()
        if not payments:
            await callback.message.answer('Нет оплат на проверку.')
            await callback.answer()
            return
        for payment in payments:
            buyer = await UserRepository(session).get(payment.buyer_id)
            deal_info = 'N/A'
            deal = getattr(payment, 'deal', None)
            if deal is None and getattr(payment, 'deal_id', None) is not None:
                deal = await session.get(Deal, payment.deal_id)
            if deal is not None:
                deal_info = f'{deal.deal_number} ({deal.deal_code})'
            await callback.message.answer(
                (
                    f'Оплата #{payment.id}\n'
                    f'Сделка: {deal_info}\n'
                    f'Покупатель: @{buyer.username if buyer and buyer.username else payment.buyer_id}\n'
                    f'Сумма: {payment.amount:.2f} {payment.currency.value}\n'
                    f'Комментарий: {payment.comment}'
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='✅ Подтвердить оплату', callback_data=f'confirm_payment:{payment.id}')],
                    [InlineKeyboardButton(text='❌ Отклонить оплату', callback_data=f'reject_payment:{payment.id}')],
                ]),
            )
        await callback.answer()
        return
    if data == 'admin_export_db':
        if not (is_admin or is_super_admin or db_user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN} or db_user.id in {*config.ADMIN_IDS, *config.SUPER_ADMIN_IDS}):
            await callback.answer('⛔ Недостаточно прав.', show_alert=True)
        if not (is_super_admin or db_user.role == UserRole.SUPER_ADMIN or db_user.id in config.SUPER_ADMIN_IDS):
            await callback.answer('⛔ Только суперадминистратор может выгружать DB.', show_alert=True)
            return
        filename = await export_db_file(session)
        await callback.message.answer_document(FSInputFile(str(filename)), caption='📦 Выгрузка базы данных')
        await callback.answer()
        return
    if data == 'admin_import_db':
        if not (is_super_admin or db_user.role == UserRole.SUPER_ADMIN or db_user.id in config.SUPER_ADMIN_IDS):
            await callback.answer('⛔ Только суперадминистратор может импортировать DB.', show_alert=True)
            return
        await callback.message.answer('📥 Отправьте JSON-файл экспорта базы данных.')
        await state.set_state(ImportDBStates.wait_file)
        await callback.answer()
        return
    if data == 'admin_broadcast':
        await callback.message.answer('📢 Напишите текст для рассылки. После этого отправьте «Да» для подтверждения.')
        await state.set_state(BroadcastStates.enter_text)
        await callback.answer()
        return
    if data == 'admin_finish_deals':
        deals = await DealRepository(session).list_active()
        if not deals:
            await callback.message.answer('Активных сделок нет.')
            await callback.answer()
            return
        for deal in deals:
            seller = await UserRepository(session).get(deal.seller_id)
            buyer = await UserRepository(session).get(deal.buyer_id) if deal.buyer_id else None
            await callback.message.answer(
                (
                    f'Сделка: {deal.deal_number} ({deal.deal_code})\n'
                    f'Статус: {format_deal_status(deal.status)}\n'
                    f'Продавец: @{seller.username if seller and seller.username else deal.seller_id}\n'
                    f'Покупатель: @{buyer.username if buyer and buyer.username else deal.buyer_id or "не задан"}\n'
                    f'\nСумма: {deal.amount:.2f} {deal.currency.value}\n'
                    f'Описание: {deal.item_description}'
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='✅ Подтвердить завершение сделки', callback_data=f'admin_complete_deal:{deal.deal_number}')],
                ]),
            )
        await callback.answer()
        return
    if data == 'admin_withdraws':
        requests = await WithdrawRepository(session).list_pending()
        if not requests:
            await callback.message.answer('Нет заявок на вывод.')
            await callback.answer()
            return
        for request in requests:
            user = await UserRepository(session).get(request.user_id)
            await callback.message.answer(
                (
                    f'Вывод #{request.id}\n'
                    f'Пользователь: @{user.username if user and user.username else request.user_id}\n'
                    f'Валюта: {request.currency.value}\n'
                    f'Сумма: {request.amount:.2f}'
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='✅ Выполнено', callback_data=f'withdraw_ok:{request.id}')],
                    [InlineKeyboardButton(text='❌ Отклонено', callback_data=f'withdraw_reject:{request.id}')],
                ]),
            )
        await callback.answer()
        return
    if data.startswith('admin_complete_deal:'):
        # admin_complete_deal uses deal_number (not DB id) to support in-memory store
        deal_number = int(data.split(':', 1)[1])
        deal = await DealRepository(session).get_by_number(deal_number)
        if not deal:
            await callback.answer('Сделка не найдена.')
            return
        if deal.status == DealStatus.COMPLETED:
            await callback.answer('Сделка уже завершена.')
            return
        seller = await UserRepository(session).get(deal.seller_id)
        if seller:
            await BalanceRepository(session).change(seller.id, deal.currency, deal.amount)
            seller.completed_deals = (seller.completed_deals or 0) + 1
            seller.total_volume = (seller.total_volume or 0.0) + deal.amount
        # mark completed and commit
        deal.status = DealStatus.COMPLETED
        await session.commit()
        await callback.answer('Сделка принудительно завершена.')
        # Notify seller that moderation approved and request to transfer gift
        if seller:
            seller_lang = await get_user_language(session, seller.id)
            try:
                await callback.bot.send_message(
                    seller.id,
                    f'{get_localized_text("admin_complete_seller", seller_lang)}\n\nСделка №{deal.deal_number}'
                )
            except Exception:
                pass
            try:
                await callback.bot.send_message(seller.id, f'💰 Средства зачислены: {deal.amount:.2f} {deal.currency.value}')
            except Exception:
                pass
        if deal.buyer_id:
            buyer_lang = await get_user_language(session, deal.buyer_id)
            try:
                await callback.bot.send_message(deal.buyer_id, f'{get_localized_text("admin_complete_buyer", buyer_lang)}\n\nСделка №{deal.deal_number}')
            except Exception:
                pass
        return
    # Fallback: acknowledge
    await callback.answer()


async def register_handlers(dp: Dispatcher) -> None:
    dp.message.register(handle_start, CommandStart())
    dp.message.register(admin_panel, Command('admin'))
    dp.message.register(list_deals, Command('deals'))
    dp.message.register(show_deal, Command('deal'))
    dp.message.register(list_payments, Command('payments'))
    dp.message.register(list_withdraws, Command('withdraws'))
    dp.message.register(list_users, Command('users'))
    dp.message.register(show_user, Command('user'))
    dp.message.register(stats, Command('stats'))
    dp.message.register(block_user, Command('block'))
    dp.message.register(unblock_user, Command('unblock'))
    dp.message.register(logs, Command('logs'))
    dp.message.register(cancel_deal, Command('canceldeal'))
    dp.message.register(finish_deal, Command('finishdeal'))
    dp.message.register(add_admin, Command('addadmin'))
    dp.message.register(remove_admin, Command('removeadmin'))
    dp.message.register(add_balance_to_user, Command('addbalance'))
    dp.message.register(add_balance_to_user, Command('selfbalance'))
    dp.message.register(export_db, Command('exportdb'))
    dp.message.register(import_db_from_message, ImportDBStates.wait_file)
    dp.message.register(import_db_from_message, Command('importdb'))
    dp.message.register(whoami, Command('whoami'))
    dp.message.register(process_deal_type, DealCreation.choose_type)
    dp.message.register(cancel_fsm, StateFilter('*'), message_equals('❌ Отмена'))
    dp.message.register(cancel_fsm, StateFilter('*'), message_equals('⬅️ Назад'))
    # Explicit profile handler so button always opens profile when no FSM state is active
    dp.message.register(send_profile, StateFilter(None), message_equals('👤 Мой профиль'))
    dp.message.register(support_message, SupportStates.enter_message)
    dp.message.register(support_reply_send, SupportStates.admin_reply)
    dp.message.register(process_profile_text, StateFilter(None))
    dp.message.register(start_deal, message_equals('💼 Создать сделку'))
    dp.message.register(show_help_create, message_equals('📖 Как создать сделку'))
    dp.message.register(show_help_flow, message_equals('🛡 Как проходит сделка'))
    dp.message.register(show_help_flow, message_equals('❓ Как проходит сделка?'))
    dp.message.register(process_deal_type, message_equals('🎁 Подарки'))
    dp.message.register(process_deal_currency, DealCreation.choose_currency)
    dp.message.register(process_deal_amount, DealCreation.enter_amount)
    dp.message.register(process_deal_description, DealCreation.enter_description)
    dp.message.register(save_card, ProfileUpdate.set_card)
    dp.message.register(save_wallet, ProfileUpdate.set_wallet)
    dp.message.register(save_stars, ProfileUpdate.set_stars)
    dp.message.register(process_withdraw_currency, WithdrawRequestStates.choose_currency)
    dp.message.register(process_withdraw_amount, WithdrawRequestStates.enter_amount)
    dp.callback_query.register(confirm_withdraw, callback_data_equals('confirm_withdraw'), WithdrawRequestStates.confirm_withdrawal)
    dp.callback_query.register(cancel_withdraw, callback_data_equals('cancel_withdraw'), WithdrawRequestStates.confirm_withdrawal)
    dp.message.register(broadcast_text, Command('broadcast'))
    dp.message.register(broadcast_text, BroadcastStates.enter_text)
    dp.message.register(broadcast_confirm, BroadcastStates.confirm, message_equals('Да', ignore_case=True))
    dp.message.register(direct_user_broadcast, AdminUserBroadcastStates.wait_message)
    dp.message.register(send_main_menu, message_equals('⬅️ Назад'))
    dp.callback_query.register(language_callback, callback_data_startswith('set_lang_'))
    dp.callback_query.register(menu_callback, callback_data_startswith('menu_'))
    dp.callback_query.register(buyer_paid, callback_data_startswith('buyer_paid:'))
    dp.callback_query.register(seller_transferred, callback_data_startswith('seller_transferred:'))
    dp.callback_query.register(buyer_confirmed, callback_data_startswith('buyer_confirmed:'))
    dp.callback_query.register(confirm_payment, callback_data_startswith('confirm_payment:'))
    dp.callback_query.register(reject_payment, callback_data_startswith('reject_payment:'))
    dp.callback_query.register(withdraw_ok, callback_data_startswith('withdraw_ok:'))
    dp.callback_query.register(withdraw_reject, callback_data_startswith('withdraw_reject:'))
    dp.callback_query.register(support_reply_start, callback_data_startswith('support_reply:'))
    dp.callback_query.register(admin_callback, callback_data_startswith('admin_'))
    dp.callback_query.register(admin_callback, callback_data_startswith('user_profile_action:'))
    dp.callback_query.register(admin_callback, callback_data_startswith('user_action:'))
