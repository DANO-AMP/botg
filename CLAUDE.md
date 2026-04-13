# Telegram Shop Bot

## Project Overview

Python Telegram bot for selling digital products (service accounts and API keys/tokens) with crypto payments via Bitunix exchange.

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** aiogram 3.x (async Telegram bot framework)
- **Database:** SQLite via aiosqlite
- **HTTP Client:** aiohttp (for Bitunix API)
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
    admin.py           # Admin CRUD operations
    referral.py        # Referral system
  keyboards/
    inline.py          # InlineKeyboardMarkup builders
  services/
    bitunix.py         # Bitunix API client (HMAC-SHA256 auth)
    password.py        # Secure password generator
    payment_checker.py # Async deposit polling
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

## Key Commands

```bash
python -m bot.main          # Run the bot
```

## Database

- SQLite at `data/shop.db` (auto-created on first run)
- 6 tables: users, categories, products, stock_items, orders, referrals
- Schema initialized in `db.py` on startup

## Security Rules

- NEVER hardcode API keys, tokens, or secrets
- NEVER commit `.env` or `data/` directory
- Sign all Bitunix API requests with HMAC-SHA256
- Validate deposit amounts before confirming payment
- Gate all admin handlers with ADMIN_TELEGRAM_ID check
