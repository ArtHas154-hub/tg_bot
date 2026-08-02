import os
from typing import Sequence
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
BOT_USERNAME = os.getenv('BOT_USERNAME', '').strip()
# Normalize BOT_USERNAME: strip leading @ if provided
if BOT_USERNAME.startswith('@'):
    BOT_USERNAME = BOT_USERNAME.lstrip('@')
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@db:5432/nft_escrow')
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
ADMIN_IDS: Sequence[int] = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip().isdigit()]
SUPER_ADMIN_IDS: Sequence[int] = [int(x) for x in os.getenv('SUPER_ADMIN_IDS', '').split(',') if x.strip().isdigit()]
PAYMENT_CARD = os.getenv('PAYMENT_CARD', 'Сбербанк 2202 2020 6392 2833')
TON_WALLET = os.getenv('TON_WALLET', '').strip()
STARS_USERNAME = os.getenv('STARS_USERNAME', '').strip()

if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN is required in environment')

if not BOT_USERNAME:
    raise RuntimeError('BOT_USERNAME is required in environment')
