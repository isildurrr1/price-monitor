# Мониторинг цен на MacBook Air M4

Скрипт раз в день в 14:00 и 19:00 проверяет цену на двух сайтах и шлёт
уведомление в Telegram, если цена упала относительно прошлой проверки.

## Что отслеживается
- `apples116.ru` — MacBook Air M4 13"
- `tatphone.ru` — MacBook Air M4 13.6 2025 16/256 Silver

## Установка на Ubuntu 24.04 LTS

### 1. Создать Telegram-бота

1. Открой [@BotFather](https://t.me/BotFather), команда `/newbot`, придумай имя.
2. Получишь токен вида `1234567890:AAH...` — сохрани.
3. Открой [@userinfobot](https://t.me/userinfobot), команда `/start` —
   получишь свой `chat_id` (число).
4. **ВАЖНО**: напиши своему новому боту любое сообщение (`/start`),
   иначе он не сможет тебе писать.

### 2. Скопировать файлы на VPS

```bash
mkdir -p ~/price_monitor
cd ~/price_monitor
# скопируй сюда: monitor.py, config.py, requirements.txt
```

### 3. Установить зависимости

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv

# Вариант A: через venv (рекомендую — чисто, без конфликтов)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate

# Вариант B: глобально (проще, но не идеально на Ubuntu 24.04)
# pip install -r requirements.txt --break-system-packages
```

### 4. Прописать токен и chat_id

```bash
nano config.py
```
Замени `PASTE_YOUR_BOT_TOKEN_HERE` и `PASTE_YOUR_CHAT_ID_HERE`.

### 5. Тестовый запуск

```bash
cd ~/price_monitor
./venv/bin/python monitor.py     # если использовал venv
# или
python3 monitor.py               # если ставил глобально
```

В консоль выведется лог. В БД (`prices.db`) запишутся текущие цены.
Уведомления при первом запуске **не придут** — это нормально, ему нечего
сравнивать. Чтобы убедиться, что Telegram работает, можно один раз
вручную позвать `send_telegram("Тест")` из python-консоли.

### 6. Настроить cron

```bash
crontab -e
```

Добавь строки (если использовал venv):
```cron
0 14 * * * cd /home/USERNAME/price_monitor && ./venv/bin/python monitor.py >> cron.log 2>&1
0 19 * * * cd /home/USERNAME/price_monitor && ./venv/bin/python monitor.py >> cron.log 2>&1
```

Если ставил pip глобально — замени `./venv/bin/python` на `/usr/bin/python3`.

**Важно про часовой пояс**: cron использует системный TZ. Проверь:
```bash
timedatectl
# Если не Москва/нужный пояс:
sudo timedatectl set-timezone Europe/Moscow
```

### 7. Проверить, что cron работает

```bash
# посмотреть, что cron видит твою задачу
crontab -l

# логи запусков
tail -f ~/price_monitor/cron.log
tail -f ~/price_monitor/monitor.log
```

## Структура файлов

```
price_monitor/
├── monitor.py        — основной скрипт
├── config.py         — настройки (токен, chat_id, URLs)
├── requirements.txt  — зависимости
├── prices.db         — SQLite с историей цен (создаётся автоматически)
├── monitor.log       — лог работы скрипта
└── cron.log          — лог запусков из cron
```

## Что важно знать

- **Уведомление приходит только при падении цены** (как ты просил).
  Если цена выросла или не изменилась — тишина.
- **При новом историческом минимуме** в сообщение добавляется пометка 🔥.
- **Если парсер сломается** (магазин поменял разметку) — придёт
  уведомление об ошибке, чтобы ты не пропустил поломку.
- **БД растёт медленно**: 2 записи в день × 2 сайта = 4 записи. За год
  ~1500 строк, ничтожный размер.

## Если цена не парсится

Магазины могут менять разметку. Парсер использует 3 уровня резерва:
1. JSON-LD (Schema.org) — самый надёжный, его редко трогают
2. CSS-селекторы / `<title>`
3. Regex по сырому HTML

Если все три не сработают — придёт ошибка в Telegram. Тогда нужно открыть
страницу в браузере, посмотреть актуальную разметку и поправить функцию
`parse_apples116` или `parse_tatphone` в `monitor.py`.

## Расширение

- Добавить новый сайт: дописать функцию-парсер, добавить её в `PARSERS`
  и добавить запись в `PRODUCTS` в `config.py`.
- Изменить расписание: правишь cron.
- Хочешь алерт при цене ниже X: после `save_price` добавь проверку
  `if new_price < THRESHOLD: send_telegram(...)`.
