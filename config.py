"""
Конфигурация мониторинга цен.
Секреты берутся из .env (не коммитить его в git).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------- Telegram ----------
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ---------- Товары для мониторинга ----------
PRODUCTS = [
    {
        "site": "apples116",
        "name": "MacBook Air M4 13\" 16/256",
        "url": "https://apples116.ru/product/macbook-air-m4-13",
    },
    {
        "site": "tatphone",
        "name": "MacBook Air M4 13.6 2025 16/256 Silver",
        "url": "https://tatphone.ru/apple-macbook-air-m4-136-2025-16-256gb-silver",
    },
]

# ---------- Технические настройки ----------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "prices.db"
LOG_PATH = BASE_DIR / "monitor.log"

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
