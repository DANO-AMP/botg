# Telegram Shop Bot -- Design Spec

**Date:** 2026-04-13
**Status:** Approved

## Overview

A Telegram bot that sells digital products (service accounts and API keys/tokens) with crypto payments via Bitunix exchange. Built in Python with aiogram 3.x and SQLite.

## Requirements Summary

- **Language:** Python (aiogram 3.x async framework)
- **Database:** SQLite via aiosqlite
- **Payments:** Bitunix API (crypto), prices defined in USD and converted at payment time
- **Admin:** Single admin, managed entirely via Telegram inline buttons
- **Language (UI):** English only
- **Extras:** Referral system ($10 mutual bonus on first purchase)

## Product Types

### Type "account"
- User provides their email address
- Bot generates a random secure password
- After payment confirmation, bot delivers the password to the user
- Admin receives notification to create the account on the target service

### Type "string"
- Pre-loaded stock of strings (API keys, tokens, etc.)
- Admin loads stock via bot (one item per line)
- After payment confirmation, bot delivers one item from stock and marks it sold

## Database Schema

### users
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Telegram user ID |
| username | TEXT | @username |
| balance | REAL DEFAULT 0.0 | Referral balance in USD |
| referred_by | INTEGER | ID of referrer |
| created_at | TIMESTAMP | |

### categories
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| name | TEXT NOT NULL | |
| description | TEXT | |
| is_active | INTEGER DEFAULT 1 | |
| sort_order | INTEGER DEFAULT 0 | |

### products
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| category_id | INTEGER FK | References categories(id) |
| name | TEXT NOT NULL | |
| description | TEXT | |
| price_usd | REAL NOT NULL | |
| type | TEXT NOT NULL | 'account' or 'string' |
| is_active | INTEGER DEFAULT 1 | |

### stock_items
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| product_id | INTEGER FK | References products(id) |
| value | TEXT NOT NULL | The API key / token / string |
| is_sold | INTEGER DEFAULT 0 | |
| sold_to | INTEGER FK | References users(id) |
| sold_at | TIMESTAMP | |

### orders
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| user_id | INTEGER FK | References users(id) |
| product_id | INTEGER FK | References products(id) |
| email | TEXT | Only for type 'account' |
| generated_password | TEXT | Only for type 'account' |
| delivered_value | TEXT | What was delivered |
| amount_usd | REAL | |
| amount_crypto | REAL | |
| crypto_currency | TEXT | BTC, USDT, ETH, etc. |
| deposit_address | TEXT | |
| status | TEXT DEFAULT 'pending' | pending/paid/delivered/expired/cancelled |
| created_at | TIMESTAMP | |
| paid_at | TIMESTAMP | |

### referrals
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| referrer_id | INTEGER FK | References users(id) |
| referred_id | INTEGER FK | References users(id) |
| bonus_applied | INTEGER DEFAULT 0 | 0=pending, 1=both received $10 |
| created_at | TIMESTAMP | |

## User Flow

### Start
- `/start` shows main menu: [Browse Products] [My Orders] [My Balance] [Referral Link]
- `/start ref_<id>` registers referral relationship

### Browsing
1. [Browse Products] -> list of active categories (inline buttons)
2. Click category -> list of products with prices
3. Click product -> detail view with [Buy Now] [Back]

### Purchase (type "account")
1. [Buy Now] -> "Enter your email:"
2. User types email
3. "Choose payment crypto:" [BTC] [USDT] [ETH]
4. Order summary with converted amount + deposit address
5. Bot polls Bitunix every 30s for deposit
6. Payment confirmed -> deliver generated password + notify admin
7. 30 min timeout -> order expires

### Purchase (type "string")
Same flow but no email step. Delivers stock item after payment.

### Balance usage
- If balance >= price: pay entirely with balance, no crypto needed
- If 0 < balance < price: pay difference in crypto, deduct full balance
- If balance == 0: normal crypto flow

## Admin Panel

Access via `/admin` (restricted to ADMIN_TELEGRAM_ID).

### Menu
[Manage Categories] [Manage Products] [Add Stock] [View Orders] [Stats] [Broadcast]

### Manage Categories
- List categories + [Add New]
- Per category: [Edit Name] [Toggle Active] [Delete] [Back]

### Manage Products
- Select category first
- List products + [Add New]
- Per product: [Edit Name] [Edit Price] [Edit Description] [Toggle Active] [View Stock] [Delete]
- Add new: choose type (account/string) -> name -> price -> description

### Add Stock (string products only)
- Select string-type product
- Send items one per line
- Confirmation with count

### View Orders
- Filter by status: [Pending] [Paid] [Delivered] [All]
- List with user, product, amount, date
- Click for full detail

### Broadcast
- Enter message -> confirm with user count -> send in batches (rate limited)

## Bitunix Integration

### API Client Methods
- `get_price(symbol)` -- current market price for a trading pair
- `create_deposit_address(currency)` -- new deposit address per order
- `check_deposit(address, expected_amount)` -- verify deposit arrived
- `get_usd_to_crypto(usd_amount, crypto)` -- USD to crypto conversion

### Authentication
- HMAC-SHA256 signing: concatenate timestamp + method + path + body
- Sign with Secret Key, send in request headers

### Payment Monitoring
- `asyncio.create_task` per pending order
- Poll Bitunix every 30s for deposit confirmation
- Max 3 concurrent pending orders per user
- 30 minute timeout per order

## Referral System

### Mechanics
1. Each user gets unique link: `t.me/botname?start=ref_<user_id>`
2. New user opens bot with link -> relationship saved
3. Bonus triggers on referred user's FIRST completed purchase
4. Both referrer and referred receive $10 USD balance
5. Notification sent to both

### Protections
- A user can only be referred once
- Cannot refer yourself
- Bonus only activates after real purchase (prevents farming)

## Project Structure

```
botg/
  bot/
    __init__.py
    main.py              # Entry point, dispatcher setup
    config.py            # Settings from .env
    db.py                # SQLite connection + schema init
    handlers/
      __init__.py
      start.py           # /start, main menu
      catalog.py         # Browse categories/products
      purchase.py        # Purchase flow + payment
      admin.py           # CRUD categories/products/stock
      referral.py        # Referral system
    keyboards/
      __init__.py
      inline.py          # All InlineKeyboardMarkup builders
    services/
      __init__.py
      bitunix.py         # Bitunix API client
      password.py        # Password generator
      payment_checker.py # Deposit polling tasks
    middlewares/
      __init__.py
      auth.py            # Admin verification
  data/
    shop.db              # Created automatically
  .env
  .env.example
  .gitignore
  requirements.txt
  CLAUDE.md
```

## Dependencies

```
aiogram>=3.10
aiosqlite>=0.20
aiohttp>=3.9
python-dotenv>=1.0
```

## Configuration (.env)

```
TELEGRAM_BOT_TOKEN=
BITUNIX_API_KEY=
BITUNIX_SECRET_KEY=
ADMIN_TELEGRAM_ID=
REFERRAL_BONUS_USD=10.0
ORDER_TIMEOUT_MINUTES=30
PAYMENT_CHECK_INTERVAL_SECONDS=30
DB_PATH=data/shop.db
```

## Security Considerations

- All secrets in `.env`, never in code
- `.env` excluded via `.gitignore`
- HMAC-SHA256 signed requests to Bitunix
- Validate deposit amount >= expected (protect against partial payments)
- Rate limit: max 3 pending orders per user
- Generated passwords: 12 chars, mixed case + digits + special chars
- Admin commands gated by Telegram user ID check
