#!/usr/bin/env python3
"""
Мониторинг цен на MacBook Air M4 16/256 на двух сайтах.
Запускается через cron 2 раза в день (14:00 и 19:00).
Уведомление в Telegram отправляется только если цена УПАЛА.
"""

import json
import logging
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    PRODUCTS,
    DB_PATH,
    LOG_PATH,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

# ---------- Логирование ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("monitor")


# ---------- БД ----------
def init_db():
    """Создаёт таблицу истории цен, если её ещё нет."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prices (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            site      TEXT NOT NULL,
            price     INTEGER NOT NULL,
            checked_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def get_last_price(site: str) -> int | None:
    """Возвращает последнюю сохранённую цену для сайта или None."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT price FROM prices WHERE site = ? ORDER BY id DESC LIMIT 1",
        (site,),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def save_price(site: str, price: int) -> None:
    """Сохраняет новую цену в историю."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO prices (site, price, checked_at) VALUES (?, ?, ?)",
        (site, price, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def get_min_price(site: str) -> int | None:
    """Возвращает исторический минимум цены для сайта."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT MIN(price) FROM prices WHERE site = ?", (site,)
    ).fetchone()
    conn.close()
    return row[0] if row and row[0] else None


# ---------- Парсинг ----------
def parse_price_text(text: str) -> int | None:
    """Извлекает целое число (рубли) из строки вида '85 000 ₽' или '84 490 ₽'."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def fetch_html(url: str) -> str:
    """Скачивает HTML-страницу с нужными заголовками."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text


def parse_apples116(url: str) -> int:
    """
    apples116.ru работает на InSales. Надёжнее всего цену брать из JSON-LD,
    который InSales вшивает в страницу (тег <script type="application/ld+json">).
    Резервный вариант — поиск по тексту 'купить ... за NNN ₽' в <title>.
    """
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    # 1. Пробуем JSON-LD (Schema.org Product)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        # data может быть dict или list
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "Product":
                offers = item.get("offers")
                if isinstance(offers, dict):
                    price = offers.get("price") or offers.get("lowPrice")
                    if price:
                        return int(float(price))
                elif isinstance(offers, list) and offers:
                    # минимальная цена среди всех вариантов
                    prices = [
                        float(o.get("price") or 0) for o in offers if o.get("price")
                    ]
                    if prices:
                        return int(min(p for p in prices if p > 0))

    # 2. Резерв: достаём цену из <title> вида "MacBook Air M4 13" – купить ... за 84 490 ₽"
    title = soup.find("title")
    if title:
        m = re.search(r"за\s+([\d\s]+)\s*₽", title.get_text())
        if m:
            price = parse_price_text(m.group(1))
            if price:
                return price

    raise ValueError("apples116: не удалось найти цену на странице")


def parse_tatphone(url: str) -> int:
    """
    tatphone.ru — WordPress + WooCommerce. Цена лежит в HTML в простом виде,
    но нужно отличать цену основного товара от цен в блоках 'Аксессуары' и т.п.
    Берём первый <p class="price"> или JSON-LD.
    """
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    # 1. JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Product":
                offers = item.get("offers")
                if isinstance(offers, dict):
                    price = offers.get("price") or offers.get("lowPrice")
                    if price:
                        return int(float(price))

    # 2. Резерв: ищем элемент с классом, содержащим 'price', внутри основной карточки
    #    WooCommerce обычно использует <p class="price"> или <span class="woocommerce-Price-amount">
    price_el = soup.select_one(".summary .price, p.price, .woocommerce-Price-amount")
    if price_el:
        price = parse_price_text(price_el.get_text())
        if price:
            return price

    # 3. Совсем грубый резерв: первое вхождение 'NNN NNN ₽' в HTML
    m = re.search(r"(\d{2,3}[\s\u00a0]\d{3})\s*₽", html)
    if m:
        price = parse_price_text(m.group(1))
        if price:
            return price

    raise ValueError("tatphone: не удалось найти цену на странице")


PARSERS = {
    "apples116": parse_apples116,
    "tatphone": parse_tatphone,
}


# ---------- Telegram ----------
def send_telegram(text: str) -> None:
    """Отправляет сообщение в Telegram. Поддерживает HTML-разметку."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
    except Exception as e:
        log.error("Не удалось отправить в Telegram: %s", e)


# ---------- Основной цикл ----------
def check_product(product: dict) -> None:
    site = product["site"]
    name = product["name"]
    url = product["url"]
    parser = PARSERS[site]

    try:
        new_price = parser(url)
    except Exception as e:
        log.error("[%s] Ошибка парсинга: %s", site, e)
        # шлём ошибку в TG, чтобы не пропустить поломку скрипта
        send_telegram(
            f"⚠️ <b>Ошибка мониторинга</b>\n"
            f"Сайт: {site}\nОшибка: <code>{e}</code>"
        )
        return

    last_price = get_last_price(site)
    min_price = get_min_price(site)

    log.info(
        "[%s] цена=%s, прошлая=%s, минимум=%s",
        site, new_price, last_price, min_price,
    )

    save_price(site, new_price)

    # Условие уведомления: цена УПАЛА относительно последней проверки.
    if last_price is not None and new_price < last_price:
        diff = last_price - new_price
        is_new_min = min_price is None or new_price < min_price
        new_min_text = "\n🔥 <b>Это новый минимум за всё время!</b>" if is_new_min else ""

        msg = (
            f"📉 <b>Цена упала!</b>\n\n"
            f"<b>{name}</b>\n"
            f"Сайт: {site}\n\n"
            f"Было:  {last_price:,} ₽\n"
            f"Стало: {new_price:,} ₽\n"
            f"Скидка: −{diff:,} ₽"
            f"{new_min_text}\n\n"
            f"<a href=\"{url}\">Открыть товар</a>"
        ).replace(",", " ")

        send_telegram(msg)
        log.info("[%s] отправлено уведомление о падении цены", site)


def main():
    log.info("=== Запуск мониторинга ===")
    init_db()
    for product in PRODUCTS:
        check_product(product)
    log.info("=== Завершено ===")


if __name__ == "__main__":
    main()
