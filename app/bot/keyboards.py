from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💼 Создать сделку', callback_data='menu_create_deal')],
        [InlineKeyboardButton(text='❓ Как проходит сделка?', callback_data='menu_how_it_works')],
        [InlineKeyboardButton(text='📢 Наш канал', callback_data='menu_channel')],
        [InlineKeyboardButton(text='👤 Мой профиль', callback_data='menu_profile')],
        [InlineKeyboardButton(text='⚙️ Настройки', callback_data='menu_settings')],
    ])


def profile_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💰 Баланс', callback_data='menu_balance')],
        [InlineKeyboardButton(text='💳 Привязать карту', callback_data='menu_bind_card')],
        [InlineKeyboardButton(text='💎 Привязать TON кошелек', callback_data='menu_bind_wallet')],
        [InlineKeyboardButton(text='⭐ Указать получателя Stars', callback_data='menu_bind_stars')],
        [InlineKeyboardButton(text='💸 Вывести баланс', callback_data='menu_withdraw')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='menu_back')],
    ])


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🇷🇺 Русский', callback_data='set_lang_ru')],
        [InlineKeyboardButton(text='🇬🇧 English', callback_data='set_lang_en')],
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='menu_back')],
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
        [InlineKeyboardButton(text='📊 Статистика', callback_data='admin_stats')],
        [InlineKeyboardButton(text='💼 Завершение сделок', callback_data='admin_finish_deals')],
        [InlineKeyboardButton(text='✅ Проверка оплат', callback_data='admin_payments')],
        [InlineKeyboardButton(text='� Рассылка', callback_data='admin_broadcast')],
        [InlineKeyboardButton(text='�💸 Заявки на вывод', callback_data='admin_withdraws')],
        [InlineKeyboardButton(text='👥 Пользователи', callback_data='admin_users')],
        [InlineKeyboardButton(text='💰 Балансы', callback_data='admin_balances')],
        [InlineKeyboardButton(text='🚫 Заблокированные', callback_data='admin_blocked')],
        [InlineKeyboardButton(text='⚙️ Настройки', callback_data='admin_settings')],
    ])
