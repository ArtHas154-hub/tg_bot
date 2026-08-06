from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(language: str = 'ru', is_admin: bool = False) -> InlineKeyboardMarkup:
    texts = {
        'ru': ('💼 Создать сделку', '❓ Как проходит сделка?', '📢 Наш канал', '🆘 Поддержка', '👤 Мой профиль', '⚙️ Настройки'),
        'en': ('💼 Create deal', '❓ How does a deal work?', '📢 Our channel', '🆘 Support', '👤 My profile', '⚙️ Settings'),
    }.get(language, {
        'ru': ('💼 Создать сделку', '❓ Как проходит сделка?', '📢 Наш канал', '🆘 Поддержка', '👤 Мой профиль', '⚙️ Настройки'),
    }['ru'])
    rows = [
        [InlineKeyboardButton(text=texts[0], callback_data='menu_create_deal')],
        [InlineKeyboardButton(text=texts[1], url='https://telegra.ph/Kak-bezopasno-provodit-sdelki-cherez-NIFTIX-08-02')],
        [InlineKeyboardButton(text=texts[2], callback_data='menu_channel')],
        [InlineKeyboardButton(text=texts[3], callback_data='menu_support')],
        [InlineKeyboardButton(text=texts[4], callback_data='menu_profile')],
        [InlineKeyboardButton(text=texts[5], callback_data='menu_settings')],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text='🛠 Админ-панель', callback_data='menu_admin_panel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_menu(language: str = 'ru', is_admin: bool = False) -> InlineKeyboardMarkup:
    texts = {
        'ru': ('💰 Баланс', '💳 Привязать карту', '💎 Привязать TON кошелек', '⭐ Указать получателя Stars', '💸 Вывести баланс', '⬅️ Назад'),
        'en': ('💰 Balance', '💳 Bind card', '💎 Bind TON wallet', '⭐ Set Stars recipient', '💸 Withdraw balance', '⬅️ Back'),
    }.get(language, {
        'ru': ('💰 Баланс', '💳 Привязать карту', '💎 Привязать TON кошелек', '⭐ Указать получателя Stars', '💸 Вывести баланс', '⬅️ Назад'),
    }['ru'])
    rows = [
        [InlineKeyboardButton(text=texts[0], callback_data='menu_balance')],
        [InlineKeyboardButton(text=texts[1], callback_data='menu_bind_card')],
        [InlineKeyboardButton(text=texts[2], callback_data='menu_bind_wallet')],
        [InlineKeyboardButton(text=texts[3], callback_data='menu_bind_stars')],
        [InlineKeyboardButton(text=texts[4], callback_data='menu_withdraw')],
        [InlineKeyboardButton(text=texts[5], callback_data='menu_back')],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text='🛠 Админ-панель', callback_data='menu_admin_panel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_menu(language: str = 'ru') -> InlineKeyboardMarkup:
    back_text = '⬅️ Back' if language == 'en' else '⬅️ Назад'
    current_ru = ' ✅' if language == 'ru' else ''
    current_en = ' ✅' if language == 'en' else ''
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'🇷🇺 Русский{current_ru}', callback_data='set_lang_ru')],
        [InlineKeyboardButton(text=f'🇬🇧 English{current_en}', callback_data='set_lang_en')],
        [InlineKeyboardButton(text=back_text, callback_data='menu_back')],
    ])


def deal_type_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎁 Подарки', callback_data='menu_deal_type_gift')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='menu_back'), InlineKeyboardButton(text='❌ Отмена', callback_data='menu_cancel')],
    ])


def deal_currency_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🇷🇺 RUB', callback_data='menu_currency_RUB'), InlineKeyboardButton(text='🇪🇺 EUR', callback_data='menu_currency_EUR'), InlineKeyboardButton(text='🇰🇿 KZT', callback_data='menu_currency_KZT')],
        [InlineKeyboardButton(text='🇺🇿 UZS', callback_data='menu_currency_UZS'), InlineKeyboardButton(text='🇺🇦 UAH', callback_data='menu_currency_UAH'), InlineKeyboardButton(text='🇧🇾 BYN', callback_data='menu_currency_BYN')],
        [InlineKeyboardButton(text='💎 TON', callback_data='menu_currency_TON'), InlineKeyboardButton(text='⭐ Stars', callback_data='menu_currency_STARS')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='menu_back'), InlineKeyboardButton(text='❌ Отмена', callback_data='menu_cancel')],
    ])


def buyer_payment_menu(deal_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💳 Я оплатил', callback_data=f'buyer_paid:{deal_number}')],
    ])


def seller_transfer_menu(deal_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📦 Я передал товар', callback_data=f'seller_transferred:{deal_number}')],
    ])


def buyer_confirm_menu(deal_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Я получил товар', callback_data=f'buyer_confirmed:{deal_number}')],
    ])


def withdraw_confirm_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Подтвердить вывод', callback_data='confirm_withdraw')],
        [InlineKeyboardButton(text='❌ Отменить', callback_data='cancel_withdraw')],
    ])


def admin_panel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📊 Статистика', callback_data='admin_stats:7d')],
        [InlineKeyboardButton(text='💼 Завершение сделок', callback_data='admin_finish_deals')],
        [InlineKeyboardButton(text='✅ Проверка оплат', callback_data='admin_payments')],
        [InlineKeyboardButton(text='📢 Рассылка', callback_data='admin_broadcast')],
        [InlineKeyboardButton(text='💸 Заявки на вывод', callback_data='admin_withdraws')],
        [InlineKeyboardButton(text='👥 Пользователи', callback_data='admin_users')],
        [InlineKeyboardButton(text='💰 Балансы', callback_data='admin_balances')],
        [InlineKeyboardButton(text='🚫 Заблокированные', callback_data='admin_blocked')],
        [InlineKeyboardButton(text='📦 Выгрузить DB', callback_data='admin_export_db')],
        [InlineKeyboardButton(text='📥 Импорт DB', callback_data='admin_import_db')],
        [InlineKeyboardButton(text='⚙️ Настройки', callback_data='admin_settings')],
    ])


def stats_period_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='7 дней', callback_data='admin_stats:7d'), InlineKeyboardButton(text='30 дней', callback_data='admin_stats:30d')],
        [InlineKeyboardButton(text='90 дней', callback_data='admin_stats:90d'), InlineKeyboardButton(text='Все время', callback_data='admin_stats:all')],
    ])


def user_action_menu(user_id: int, is_blocked: bool = False) -> InlineKeyboardMarkup:
    block_text = '🔓 Разблокировать' if is_blocked else '🔒 Заблокировать'
    block_value = 'user_action:unblock' if is_blocked else 'user_action:block'
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📈 Активность', callback_data=f'user_action:activity:{user_id}')],
        [InlineKeyboardButton(text='💰 +100 RUB', callback_data=f'user_action:add_money:{user_id}:RUB:100'), InlineKeyboardButton(text='💰 +500 RUB', callback_data=f'user_action:add_money:{user_id}:RUB:500')],
        [InlineKeyboardButton(text='💸 +100 TON', callback_data=f'user_action:add_money:{user_id}:TON:100'), InlineKeyboardButton(text='⭐ +100 Stars', callback_data=f'user_action:add_money:{user_id}:Stars:100')],
        [InlineKeyboardButton(text='📣 Написать пользователю', callback_data=f'user_action:broadcast:{user_id}')],
        [InlineKeyboardButton(text=block_text, callback_data=f'{block_value}:{user_id}')],
    ])
