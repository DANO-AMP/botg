# Telegram Shop Bot

## Project Overview

Python Telegram bot for selling digital products (service accounts and API keys/tokens) with crypto payments via MaxelPay payment gateway.

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** aiogram 3.x (async Telegram bot framework)
- **Database:** SQLite via aiosqlite
- **HTTP Client:** aiohttp (for MaxelPay API + webhook server)
- **Encryption:** cryptography (AES-256-CBC for MaxelPay payloads)
- **Config:** python-dotenv (.env files)

## Project Structure

```
bot/                    # Main package
  main.py              # Entry point, dispatcher setup
  config.py            # Settings from .env
  db.py                # SQLite schema + queries
  handlers/            # Telegram command/callback handlers
    start.py           # /start, main menu
    catalog.py         # Browse categories/products
    purchase.py        # Purchase flow + payment
    deposit.py         # Balance deposit flow
    admin.py           # Admin CRUD operations
    referral.py        # Referral system
  keyboards/
    inline.py          # InlineKeyboardMarkup builders
  services/
    maxelpay.py        # MaxelPay API client (AES-256-CBC encrypted payloads)
    webhook_server.py  # aiohttp server for MaxelPay webhook notifications
    delivery.py        # Product delivery + notifications
    password.py        # Secure password generator
    notifications.py   # Admin notification helper
  middlewares/
    auth.py            # Admin ID check
data/                  # SQLite DB (auto-created, gitignored)
docs/superpowers/specs/ # Design specs
```

## Conventions

- All handlers use aiogram 3.x Router pattern (not Dispatcher directly)
- FSM (Finite State Machine) for multi-step flows (purchase, admin CRUD)
- Callback data format: `action:entity:id` (e.g., `buy:product:5`, `admin:cat:3`)
- All DB queries go through `db.py` -- handlers never import aiosqlite directly
- Keyboards are built by functions in `keyboards/inline.py`, never inline in handlers
- Secrets in `.env` only, loaded via `config.py`
- English only for user-facing text

## Payment Flow (MaxelPay)

1. User initiates purchase/deposit
2. Bot creates MaxelPay checkout (AES-256-CBC encrypted payload)
3. Bot sends payment URL to user via inline button
4. User pays on MaxelPay page
5. MaxelPay sends webhook POST to `WEBHOOK_BASE_URL/webhook/maxelpay`
6. Webhook server processes payment and delivers product / credits balance
7. Expiry timers auto-cancel unpaid orders after `ORDER_TIMEOUT_MINUTES`

- Order IDs sent to MaxelPay use format: `order_{id}` or `deposit_{id}`
- Webhook server runs on `WEBHOOK_PORT` (default 8080)
- Requires a publicly accessible URL for `WEBHOOK_BASE_URL`

## Key Commands

```bash
python -m bot.main          # Run the bot
```

## Database

- SQLite at `data/shop.db` (auto-created on first run)
- 7 tables: users, categories, products, stock_items, orders, referrals, deposits
- Schema initialized in `db.py` on startup

## Security Rules

- NEVER hardcode API keys, tokens, or secrets
- NEVER commit `.env` or `data/` directory
- All MaxelPay payloads encrypted with AES-256-CBC before sending
- Gate all admin handlers with ADMIN_TELEGRAM_ID check
