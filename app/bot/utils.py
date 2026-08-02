import random
import string
from datetime import datetime, timedelta
from typing import Any

from aiogram.types import Message


def build_payment_comment() -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))


def build_deal_code(length: int = 8) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def format_balance(balances: list[Any]) -> str:
    if not balances:
        return 'Баланс отсутствует.'
    lines = [f'{item.currency.value} — {item.amount:.2f}' for item in balances]
    return '\n'.join(lines)


def parse_start_payload(text: str | None) -> int | str | None:
    if not text:
        return None
    parts = text.split()
    if len(parts) < 1:
        return None
    token = parts[-1]
    if token == '/start':
        return None
    if token.startswith('deal_') and token[5:].isdigit():
        return int(token[5:])
    if token.isdigit():
        return int(token)
    if token.startswith('/start'):
        payload = token[len('/start'):].strip()
        return payload or None
    return token


def get_message_text(message: Message) -> str:
    return message.text or message.caption or ''


def check_deal_timeout(deal) -> bool:
    """Check if deal has exceeded 15 minute timeout for payment verification"""
    if deal.status.value not in ['waiting_payment', 'payment_verification']:
        return False

    if not getattr(deal, 'created_at', None):
        return False

    timeout_minutes = 15
    elapsed = datetime.utcnow() - deal.created_at
    return elapsed > timedelta(minutes=timeout_minutes)
