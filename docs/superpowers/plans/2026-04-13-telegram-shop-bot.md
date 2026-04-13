# Telegram Shop Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python Telegram bot that sells digital products (service accounts and API keys) with crypto payments via Bitunix exchange API.

**Architecture:** aiogram 3.x handles Telegram interactions through modular Routers with FSM for multi-step flows. SQLite (aiosqlite) stores all data. The Bitunix client signs requests with double-SHA256 and polls `/api/spot/v1/deposit/page` to confirm payments. Each pending order runs as an asyncio background task.

**Tech Stack:** Python 3.11+, aiogram 3.10+, aiosqlite 0.20+, aiohttp 3.9+, python-dotenv 1.0+, pytest + pytest-asyncio + pytest-mock (tests)

---

## File Map

```
botg/
  bot/
    __init__.py
    main.py              # Dispatcher setup, bot startup
    config.py            # Loads .env into Config dataclass
    db.py                # All SQLite queries (aiosqlite, module-level connection)
    handlers/
      __init__.py
      start.py           # /start, main menu, my orders, balance
      catalog.py         # Browse categories and products
      purchase.py        # FSM purchase flow: email -> crypto -> pay -> deliver
      admin.py           # Admin CRUD: categories, products, stock, orders, broadcast
      referral.py        # Show referral link and stats
    keyboards/
      __init__.py
      inline.py          # All InlineKeyboardMarkup builders + CallbackData factories
    services/
      __init__.py
      bitunix.py         # Bitunix API client (HMAC-SHA256 signing)
      password.py        # Secure password generator
      payment_checker.py # Per-order asyncio polling tasks
    middlewares/
      __init__.py
      auth.py            # Admin-only middleware (checks ADMIN_TELEGRAM_ID)
  tests/
    __init__.py
    test_password.py
    test_bitunix.py
    test_db.py
  data/                  # Auto-created, gitignored
  .env
  .env.example
  .gitignore
  requirements.txt
  requirements-dev.txt
```

---

### Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `.env.example`
- Create all `__init__.py` stubs and `data/` placeholder

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p bot/handlers bot/keyboards bot/services bot/middlewares tests data
touch bot/__init__.py bot/handlers/__init__.py bot/keyboards/__init__.py
touch bot/services/__init__.py bot/middlewares/__init__.py tests/__init__.py
touch data/.gitkeep
```

- [ ] **Step 2: Write requirements.txt**

```
aiogram>=3.10.0
aiosqlite>=0.20.0
aiohttp>=3.9.0
python-dotenv>=1.0.0
```

- [ ] **Step 3: Write requirements-dev.txt**

```
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-mock>=3.12.0
```

- [ ] **Step 4: Write .gitignore**

```
.env
data/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
.venv/
venv/
```

- [ ] **Step 5: Write .env.example**

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

- [ ] **Step 6: Commit**

```bash
git add requirements.txt requirements-dev.txt .gitignore .env.example bot/ tests/ data/
git commit -m "chore: project scaffold"
```

---

### Task 2: Config module and database schema

**Files:**
- Create: `bot/config.py`
- Create: `bot/db.py`

- [ ] **Step 1: Write bot/config.py**

```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    telegram_token: str
    bitunix_api_key: str
    bitunix_secret_key: str
    admin_telegram_id: int
    referral_bonus_usd: float
    order_timeout_minutes: int
    payment_check_interval: int
    db_path: str


def load_config() -> Config:
    return Config(
        telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
        bitunix_api_key=os.environ["BITUNIX_API_KEY"],
        bitunix_secret_key=os.environ["BITUNIX_SECRET_KEY"],
        admin_telegram_id=int(os.environ["ADMIN_TELEGRAM_ID"]),
        referral_bonus_usd=float(os.getenv("REFERRAL_BONUS_USD", "10.0")),
        order_timeout_minutes=int(os.getenv("ORDER_TIMEOUT_MINUTES", "30")),
        payment_check_interval=int(os.getenv("PAYMENT_CHECK_INTERVAL_SECONDS", "30")),
        db_path=os.getenv("DB_PATH", "data/shop.db"),
    )
```

- [ ] **Step 2: Write bot/db.py — schema and connection**

```python
import aiosqlite
import os
from typing import Any

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    balance REAL DEFAULT 0.0,
    referred_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    price_usd REAL NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('account', 'string')),
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS stock_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    value TEXT NOT NULL,
    is_sold INTEGER DEFAULT 0,
    sold_to INTEGER REFERENCES users(id),
    sold_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    email TEXT,
    generated_password TEXT,
    delivered_value TEXT,
    amount_usd REAL NOT NULL,
    amount_crypto REAL,
    crypto_currency TEXT,
    deposit_address TEXT,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending','paid','delivered','expired','cancelled')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at_ms INTEGER NOT NULL,
    paid_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER NOT NULL REFERENCES users(id),
    referred_id INTEGER NOT NULL REFERENCES users(id),
    bonus_applied INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


async def connect(db_path: str) -> None:
    global _db
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.commit()


async def close() -> None:
    if _db:
        await _db.close()


def _row(row: aiosqlite.Row | None) -> dict | None:
    return dict(row) if row else None


def _rows(rows: list[aiosqlite.Row]) -> list[dict]:
    return [dict(r) for r in rows]
```

- [ ] **Step 3: Commit**

```bash
git add bot/config.py bot/db.py
git commit -m "feat: config module and database schema"
```

---

### Task 3: DB — user and referral queries

**Files:**
- Modify: `bot/db.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_db.py`:

```python
import pytest
import pytest_asyncio
import aiosqlite
from bot import db


@pytest_asyncio.fixture
async def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    await db.connect(db_path)
    yield
    await db.close()


@pytest.mark.asyncio
async def test_get_or_create_user_new(test_db):
    user = await db.get_or_create_user(123, "alice", None)
    assert user["id"] == 123
    assert user["username"] == "alice"
    assert user["balance"] == 0.0


@pytest.mark.asyncio
async def test_get_or_create_user_idempotent(test_db):
    await db.get_or_create_user(123, "alice", None)
    user = await db.get_or_create_user(123, "alice_updated", None)
    assert user["id"] == 123  # same user, not duplicated


@pytest.mark.asyncio
async def test_update_user_balance(test_db):
    await db.get_or_create_user(123, "alice", None)
    await db.update_user_balance(123, 10.0)
    user = await db.get_user(123)
    assert user["balance"] == 10.0


@pytest.mark.asyncio
async def test_referral_bonus_only_once(test_db):
    await db.get_or_create_user(100, "referrer", None)
    await db.get_or_create_user(200, "referred", 100)
    await db.add_referral(100, 200)
    applied = await db.apply_referral_bonus_if_first_purchase(200, 10.0)
    assert applied is True
    applied_again = await db.apply_referral_bonus_if_first_purchase(200, 10.0)
    assert applied_again is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_db.py -v
```

Expected: FAIL with `AttributeError: module 'bot.db' has no attribute 'get_or_create_user'`

- [ ] **Step 3: Implement user and referral queries in bot/db.py**

Append to `bot/db.py`:

```python
async def get_or_create_user(user_id: int, username: str | None, referred_by: int | None = None) -> dict:
    async with _db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    if row:
        return dict(row)
    await _db.execute(
        "INSERT INTO users (id, username, referred_by) VALUES (?, ?, ?)",
        (user_id, username, referred_by),
    )
    await _db.commit()
    async with _db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
        return dict(await cur.fetchone())


async def get_user(user_id: int) -> dict | None:
    async with _db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
        return _row(await cur.fetchone())


async def update_user_balance(user_id: int, delta: float) -> None:
    await _db.execute(
        "UPDATE users SET balance = balance + ? WHERE id = ?", (delta, user_id)
    )
    await _db.commit()


async def get_all_users() -> list[dict]:
    async with _db.execute("SELECT * FROM users") as cur:
        return _rows(await cur.fetchall())


async def add_referral(referrer_id: int, referred_id: int) -> None:
    await _db.execute(
        "INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
        (referrer_id, referred_id),
    )
    await _db.commit()


async def apply_referral_bonus_if_first_purchase(user_id: int, bonus_usd: float) -> bool:
    """Returns True if bonus applied (i.e. this is the user's first purchase)."""
    async with _db.execute(
        "SELECT * FROM referrals WHERE referred_id = ? AND bonus_applied = 0",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return False
    referrer_id = row["referrer_id"]
    referral_id = row["id"]
    await _db.execute(
        "UPDATE referrals SET bonus_applied = 1 WHERE id = ?", (referral_id,)
    )
    await _db.execute(
        "UPDATE users SET balance = balance + ? WHERE id = ?", (bonus_usd, user_id)
    )
    await _db.execute(
        "UPDATE users SET balance = balance + ? WHERE id = ?", (bonus_usd, referrer_id)
    )
    await _db.commit()
    return True


async def get_referral_stats(user_id: int) -> dict:
    async with _db.execute(
        "SELECT COUNT(*) as count FROM referrals WHERE referrer_id = ?", (user_id,)
    ) as cur:
        count_row = await cur.fetchone()
    async with _db.execute(
        "SELECT COUNT(*) as earned FROM referrals WHERE referrer_id = ? AND bonus_applied = 1",
        (user_id,),
    ) as cur:
        earned_row = await cur.fetchone()
    bonus_per_referral = 10.0
    return {
        "count": count_row["count"],
        "total_earned": earned_row["earned"] * bonus_per_referral,
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_db.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/db.py tests/test_db.py
git commit -m "feat: db user and referral queries"
```

---

### Task 4: DB — category, product, stock queries

**Files:**
- Modify: `bot/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Add tests to tests/test_db.py**

```python
@pytest.mark.asyncio
async def test_category_crud(test_db):
    cat_id = await db.add_category("AI Services", "AI tools")
    cats = await db.get_active_categories()
    assert len(cats) == 1
    assert cats[0]["name"] == "AI Services"
    await db.toggle_category(cat_id)
    cats = await db.get_active_categories()
    assert len(cats) == 0


@pytest.mark.asyncio
async def test_product_crud(test_db):
    cat_id = await db.add_category("AI", "")
    prod_id = await db.add_product(cat_id, "Gemini Pro", "desc", 5.0, "account")
    prod = await db.get_product(prod_id)
    assert prod["name"] == "Gemini Pro"
    assert prod["price_usd"] == 5.0
    await db.update_product_field(prod_id, "price_usd", 7.0)
    prod = await db.get_product(prod_id)
    assert prod["price_usd"] == 7.0


@pytest.mark.asyncio
async def test_stock_items(test_db):
    cat_id = await db.add_category("Keys", "")
    prod_id = await db.add_product(cat_id, "API Key", "", 3.0, "string")
    added = await db.add_stock_items(prod_id, ["key1", "key2", "key3"])
    assert added == 3
    counts = await db.get_stock_count(prod_id)
    assert counts["total"] == 3
    assert counts["available"] == 3
    await db.get_or_create_user(1, "u", None)
    item = await db.get_available_stock_item(prod_id)
    await db.mark_stock_sold(item["id"], 1)
    counts = await db.get_stock_count(prod_id)
    assert counts["available"] == 2
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/test_db.py::test_category_crud tests/test_db.py::test_product_crud tests/test_db.py::test_stock_items -v
```

Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement in bot/db.py**

Append to `bot/db.py`:

```python
# --- Categories ---

async def get_active_categories() -> list[dict]:
    async with _db.execute(
        "SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order, name"
    ) as cur:
        return _rows(await cur.fetchall())


async def get_all_categories() -> list[dict]:
    async with _db.execute("SELECT * FROM categories ORDER BY sort_order, name") as cur:
        return _rows(await cur.fetchall())


async def get_category(cat_id: int) -> dict | None:
    async with _db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)) as cur:
        return _row(await cur.fetchone())


async def add_category(name: str, description: str = "") -> int:
    cur = await _db.execute(
        "INSERT INTO categories (name, description) VALUES (?, ?)", (name, description)
    )
    await _db.commit()
    return cur.lastrowid


async def update_category_name(cat_id: int, name: str) -> None:
    await _db.execute("UPDATE categories SET name = ? WHERE id = ?", (name, cat_id))
    await _db.commit()


async def toggle_category(cat_id: int) -> None:
    await _db.execute(
        "UPDATE categories SET is_active = 1 - is_active WHERE id = ?", (cat_id,)
    )
    await _db.commit()


async def delete_category(cat_id: int) -> None:
    await _db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    await _db.commit()


# --- Products ---

async def get_products_by_category(cat_id: int, active_only: bool = True) -> list[dict]:
    if active_only:
        async with _db.execute(
            "SELECT * FROM products WHERE category_id = ? AND is_active = 1", (cat_id,)
        ) as cur:
            return _rows(await cur.fetchall())
    async with _db.execute(
        "SELECT * FROM products WHERE category_id = ?", (cat_id,)
    ) as cur:
        return _rows(await cur.fetchall())


async def get_product(product_id: int) -> dict | None:
    async with _db.execute("SELECT * FROM products WHERE id = ?", (product_id,)) as cur:
        return _row(await cur.fetchone())


async def add_product(cat_id: int, name: str, description: str, price_usd: float, type_: str) -> int:
    cur = await _db.execute(
        "INSERT INTO products (category_id, name, description, price_usd, type) VALUES (?, ?, ?, ?, ?)",
        (cat_id, name, description, price_usd, type_),
    )
    await _db.commit()
    return cur.lastrowid


async def update_product_field(product_id: int, field: str, value: Any) -> None:
    allowed = {"name", "description", "price_usd"}
    if field not in allowed:
        raise ValueError(f"Cannot update field: {field}")
    await _db.execute(f"UPDATE products SET {field} = ? WHERE id = ?", (value, product_id))
    await _db.commit()


async def toggle_product(product_id: int) -> None:
    await _db.execute(
        "UPDATE products SET is_active = 1 - is_active WHERE id = ?", (product_id,)
    )
    await _db.commit()


async def delete_product(product_id: int) -> None:
    await _db.execute("DELETE FROM products WHERE id = ?", (product_id,))
    await _db.commit()


# --- Stock ---

async def add_stock_items(product_id: int, values: list[str]) -> int:
    await _db.executemany(
        "INSERT INTO stock_items (product_id, value) VALUES (?, ?)",
        [(product_id, v) for v in values],
    )
    await _db.commit()
    return len(values)


async def get_available_stock_item(product_id: int) -> dict | None:
    async with _db.execute(
        "SELECT * FROM stock_items WHERE product_id = ? AND is_sold = 0 LIMIT 1",
        (product_id,),
    ) as cur:
        return _row(await cur.fetchone())


async def mark_stock_sold(item_id: int, user_id: int) -> None:
    await _db.execute(
        "UPDATE stock_items SET is_sold = 1, sold_to = ?, sold_at = CURRENT_TIMESTAMP WHERE id = ?",
        (user_id, item_id),
    )
    await _db.commit()


async def get_stock_count(product_id: int) -> dict:
    async with _db.execute(
        "SELECT COUNT(*) as total, SUM(CASE WHEN is_sold = 0 THEN 1 ELSE 0 END) as available "
        "FROM stock_items WHERE product_id = ?",
        (product_id,),
    ) as cur:
        row = await cur.fetchone()
        return {"total": row["total"] or 0, "available": row["available"] or 0}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_db.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/db.py tests/test_db.py
git commit -m "feat: db category, product, and stock queries"
```

---

### Task 5: DB — order queries

**Files:**
- Modify: `bot/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Add tests**

```python
@pytest.mark.asyncio
async def test_order_lifecycle(test_db):
    import time
    await db.get_or_create_user(1, "u", None)
    cat_id = await db.add_category("Cat", "")
    prod_id = await db.add_product(cat_id, "Prod", "", 5.0, "account")
    order_id = await db.create_order(
        user_id=1, product_id=prod_id, email="a@b.com",
        generated_password="pass123", amount_usd=5.0,
        amount_crypto=5.003, crypto_currency="USDT",
        deposit_address="TXabc123", created_at_ms=int(time.time() * 1000),
    )
    order = await db.get_order(order_id)
    assert order["status"] == "pending"
    assert order["email"] == "a@b.com"
    await db.update_order_status(order_id, "delivered", {"delivered_value": "pass123"})
    order = await db.get_order(order_id)
    assert order["status"] == "delivered"
    assert order["delivered_value"] == "pass123"
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/test_db.py::test_order_lifecycle -v
```

Expected: FAIL.

- [ ] **Step 3: Implement in bot/db.py**

```python
# --- Orders ---

async def create_order(
    user_id: int,
    product_id: int,
    email: str | None,
    generated_password: str | None,
    amount_usd: float,
    amount_crypto: float,
    crypto_currency: str,
    deposit_address: str,
    created_at_ms: int,
) -> int:
    cur = await _db.execute(
        """INSERT INTO orders
           (user_id, product_id, email, generated_password, amount_usd,
            amount_crypto, crypto_currency, deposit_address, created_at_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, product_id, email, generated_password, amount_usd,
         amount_crypto, crypto_currency, deposit_address, created_at_ms),
    )
    await _db.commit()
    return cur.lastrowid


async def get_order(order_id: int) -> dict | None:
    async with _db.execute(
        """SELECT o.*, p.name as product_name, p.type as product_type
           FROM orders o JOIN products p ON o.product_id = p.id
           WHERE o.id = ?""",
        (order_id,),
    ) as cur:
        return _row(await cur.fetchone())


async def update_order_status(order_id: int, status: str, extra: dict | None = None) -> None:
    extra = extra or {}
    fields = ["status = ?"]
    values = [status]
    for k, v in extra.items():
        fields.append(f"{k} = ?")
        values.append(v)
    if status == "delivered":
        fields.append("paid_at = CURRENT_TIMESTAMP")
    values.append(order_id)
    await _db.execute(
        f"UPDATE orders SET {', '.join(fields)} WHERE id = ?", values
    )
    await _db.commit()


async def get_user_orders(user_id: int) -> list[dict]:
    async with _db.execute(
        """SELECT o.*, p.name as product_name
           FROM orders o JOIN products p ON o.product_id = p.id
           WHERE o.user_id = ?
           ORDER BY o.created_at DESC LIMIT 20""",
        (user_id,),
    ) as cur:
        return _rows(await cur.fetchall())


async def get_orders_by_status(status: str) -> list[dict]:
    if status == "all":
        async with _db.execute(
            """SELECT o.*, p.name as product_name, u.username
               FROM orders o
               JOIN products p ON o.product_id = p.id
               JOIN users u ON o.user_id = u.id
               ORDER BY o.created_at DESC LIMIT 50"""
        ) as cur:
            return _rows(await cur.fetchall())
    async with _db.execute(
        """SELECT o.*, p.name as product_name, u.username
           FROM orders o
           JOIN products p ON o.product_id = p.id
           JOIN users u ON o.user_id = u.id
           WHERE o.status = ?
           ORDER BY o.created_at DESC LIMIT 50""",
        (status,),
    ) as cur:
        return _rows(await cur.fetchall())


async def get_pending_orders() -> list[dict]:
    async with _db.execute(
        "SELECT * FROM orders WHERE status = 'pending'"
    ) as cur:
        return _rows(await cur.fetchall())


async def get_admin_stats() -> dict:
    async with _db.execute(
        "SELECT COUNT(*) as total, SUM(amount_usd) as revenue FROM orders WHERE status = 'delivered'"
    ) as cur:
        row = await cur.fetchone()
    async with _db.execute("SELECT COUNT(*) as users FROM users") as cur:
        users_row = await cur.fetchone()
    return {
        "total_orders": row["total"] or 0,
        "revenue": row["revenue"] or 0.0,
        "total_users": users_row["users"] or 0,
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_db.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/db.py tests/test_db.py
git commit -m "feat: db order queries"
```

---

### Task 6: Password service

**Files:**
- Create: `bot/services/password.py`
- Create: `tests/test_password.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_password.py
from bot.services.password import generate_password


def test_length():
    assert len(generate_password(12)) == 12
    assert len(generate_password(16)) == 16


def test_complexity():
    pwd = generate_password(12)
    assert any(c.isupper() for c in pwd)
    assert any(c.islower() for c in pwd)
    assert any(c.isdigit() for c in pwd)
    assert any(c in "!@#$%^&*" for c in pwd)


def test_unique():
    passwords = {generate_password() for _ in range(100)}
    assert len(passwords) == 100
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/test_password.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement bot/services/password.py**

```python
import secrets
import string

_UPPER = string.ascii_uppercase
_LOWER = string.ascii_lowercase
_DIGITS = string.digits
_SPECIAL = "!@#$%^&*"
_ALPHABET = _UPPER + _LOWER + _DIGITS + _SPECIAL


def generate_password(length: int = 12) -> str:
    while True:
        pwd = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if (
            any(c in _UPPER for c in pwd)
            and any(c in _LOWER for c in pwd)
            and any(c in _DIGITS for c in pwd)
            and any(c in _SPECIAL for c in pwd)
        ):
            return pwd
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_password.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/services/password.py tests/test_password.py
git commit -m "feat: password generator service"
```

---

### Task 7: Bitunix API client

**Files:**
- Create: `bot/services/bitunix.py`
- Create: `tests/test_bitunix.py`

**Note on endpoints:** Base URL is `https://api.bitunix.com`. Verify `/api/spot/v1/market/ticker` and `/api/spot/v1/deposit/address` against current Bitunix docs if they return 404; the deposit page at `/api/spot/v1/deposit/page` and signing algorithm are confirmed.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bitunix.py
import pytest
from bot.services.bitunix import BitunixClient


def test_sort_params():
    client = BitunixClient("key", "secret")
    result = client._sort_params({"coin": "BTC", "network": "TRC20", "limit": "10"})
    assert result == "coin=BTC&limit=10&network=TRC20"


def test_make_headers_fields():
    client = BitunixClient("mykey", "mysecret")
    headers = client._make_headers()
    assert headers["api-key"] == "mykey"
    assert "nonce" in headers
    assert "timestamp" in headers
    assert "sign" in headers
    assert len(headers["nonce"]) == 32


def test_signing_determinism():
    client = BitunixClient("k", "s")
    h1 = client._make_headers_with_values("testnonce", "1000", "", "")
    h2 = client._make_headers_with_values("testnonce", "1000", "", "")
    assert h1["sign"] == h2["sign"]


@pytest.mark.asyncio
async def test_check_deposit_found(mocker):
    client = BitunixClient("k", "s")
    mocker.patch.object(client, "_post", return_value={
        "data": {"resultList": [{"status": "success", "amount": "5.003"}]}
    })
    result = await client.check_deposit("USDT", 5.003, 0)
    assert result is True


@pytest.mark.asyncio
async def test_check_deposit_not_found(mocker):
    client = BitunixClient("k", "s")
    mocker.patch.object(client, "_post", return_value={
        "data": {"resultList": []}
    })
    result = await client.check_deposit("USDT", 5.003, 0)
    assert result is False


@pytest.mark.asyncio
async def test_check_deposit_wrong_amount(mocker):
    client = BitunixClient("k", "s")
    mocker.patch.object(client, "_post", return_value={
        "data": {"resultList": [{"status": "success", "amount": "5.999"}]}
    })
    result = await client.check_deposit("USDT", 5.003, 0)
    assert result is False
```

- [ ] **Step 2: Run to verify fail**

```bash
pytest tests/test_bitunix.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement bot/services/bitunix.py**

```python
import hashlib
import json
import random
import time
import uuid
import aiohttp
from typing import Any

BASE_URL = "https://api.bitunix.com"

CRYPTO_NETWORKS: dict[str, str] = {
    "USDT": "TRC20",
    "BTC": "BTC",
    "ETH": "ERC20",
}

TICKER_SYMBOLS: dict[str, str | None] = {
    "USDT": None,   # stablecoin, 1:1 with USD
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}


class BitunixClient:
    def __init__(self, api_key: str, secret_key: str):
        self._api_key = api_key
        self._secret_key = secret_key
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(base_url=BASE_URL)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _sort_params(self, params: dict) -> str:
        return "&".join(f"{k}={v}" for k, v in sorted(params.items()))

    def _make_headers_with_values(self, nonce: str, timestamp: str, query_str: str, body_str: str) -> dict:
        message = nonce + timestamp + self._api_key + query_str + body_str
        digest = hashlib.sha256(message.encode()).hexdigest()
        sign = hashlib.sha256((digest + self._secret_key).encode()).hexdigest()
        return {
            "api-key": self._api_key,
            "nonce": nonce,
            "timestamp": timestamp,
            "sign": sign,
            "Content-Type": "application/json",
        }

    def _make_headers(self, query_str: str = "", body_str: str = "") -> dict:
        nonce = uuid.uuid4().hex[:32]
        timestamp = str(int(time.time() * 1000))
        return self._make_headers_with_values(nonce, timestamp, query_str, body_str)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        session = await self._get_session()
        query_str = self._sort_params(params) if params else ""
        headers = self._make_headers(query_str=query_str)
        url = f"{path}?{query_str}" if query_str else path
        async with session.get(url, headers=headers) as resp:
            return await resp.json()

    async def _post(self, path: str, body: dict | None = None) -> dict:
        session = await self._get_session()
        body = body or {}
        body_str = json.dumps(body, separators=(",", ":"))
        headers = self._make_headers(body_str=body_str)
        async with session.post(path, headers=headers, data=body_str) as resp:
            return await resp.json()

    async def get_ticker_price(self, symbol: str) -> float:
        data = await self._get("/api/spot/v1/market/ticker", {"symbol": symbol})
        return float(data["data"]["close"])

    async def get_deposit_address(self, crypto: str) -> str:
        network = CRYPTO_NETWORKS.get(crypto, crypto)
        data = await self._get(
            "/api/spot/v1/deposit/address", {"coin": crypto, "network": network}
        )
        return data["data"]["address"]

    async def get_crypto_amount(self, usd_amount: float, crypto: str) -> float:
        """Convert USD to crypto with small unique increment for order identification."""
        symbol = TICKER_SYMBOLS.get(crypto)
        if symbol is None:
            base = usd_amount
        else:
            price = await self.get_ticker_price(symbol)
            base = usd_amount / price
        increment = random.uniform(0.001, 0.009)
        return round(base + increment, 8)

    async def check_deposit(self, coin: str, expected_amount: float, since_ms: int) -> bool:
        data = await self._post("/api/spot/v1/deposit/page", {
            "coin": coin,
            "type": "deposit",
            "startTime": since_ms,
            "limit": 100,
        })
        for item in (data.get("data") or {}).get("resultList", []):
            if item.get("status") == "success":
                if abs(float(item["amount"]) - expected_amount) < 0.0001:
                    return True
        return False
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_bitunix.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/services/bitunix.py tests/test_bitunix.py
git commit -m "feat: Bitunix API client with HMAC-SHA256 signing"
```

---

### Task 8: Payment checker service

**Files:**
- Create: `bot/services/payment_checker.py`

- [ ] **Step 1: Implement bot/services/payment_checker.py**

```python
import asyncio
import logging
import time
from aiogram import Bot
from bot import db
from bot.services.bitunix import BitunixClient

logger = logging.getLogger(__name__)
_tasks: dict[int, asyncio.Task] = {}


async def start_monitor(
    order_id: int,
    bot: Bot,
    client: BitunixClient,
    timeout_minutes: int,
    check_interval: int,
    admin_id: int,
) -> None:
    task = asyncio.create_task(
        _monitor_loop(order_id, bot, client, timeout_minutes, check_interval, admin_id)
    )
    _tasks[order_id] = task


def stop_monitor(order_id: int) -> None:
    task = _tasks.pop(order_id, None)
    if task:
        task.cancel()


async def restore_monitors(
    bot: Bot, client: BitunixClient, timeout_minutes: int, check_interval: int, admin_id: int
) -> None:
    pending = await db.get_pending_orders()
    now_ms = int(time.time() * 1000)
    for order in pending:
        deadline_ms = order["created_at_ms"] + timeout_minutes * 60 * 1000
        if now_ms < deadline_ms:
            await start_monitor(order["id"], bot, client, timeout_minutes, check_interval, admin_id)
        else:
            await db.update_order_status(order["id"], "expired")


async def _monitor_loop(
    order_id: int,
    bot: Bot,
    client: BitunixClient,
    timeout_minutes: int,
    check_interval: int,
    admin_id: int,
) -> None:
    deadline = time.time() + timeout_minutes * 60
    while time.time() < deadline:
        await asyncio.sleep(check_interval)
        order = await db.get_order(order_id)
        if not order or order["status"] != "pending":
            _tasks.pop(order_id, None)
            return
        try:
            found = await client.check_deposit(
                coin=order["crypto_currency"],
                expected_amount=order["amount_crypto"],
                since_ms=order["created_at_ms"],
            )
        except Exception as e:
            logger.warning("Bitunix check failed for order %s: %s", order_id, e)
            continue
        if found:
            await _deliver_and_notify(order_id, order, bot, admin_id)
            _tasks.pop(order_id, None)
            return

    order = await db.get_order(order_id)
    if order and order["status"] == "pending":
        await db.update_order_status(order_id, "expired")
        try:
            await bot.send_message(
                order["user_id"],
                "Your order has expired (no payment received in time).\n"
                "Start a new order if you still want to purchase.",
            )
        except Exception:
            pass
    _tasks.pop(order_id, None)


async def _deliver_and_notify(order_id: int, order: dict, bot: Bot, admin_id: int) -> None:
    from bot.services.password import generate_password

    product = await db.get_product(order["product_id"])

    if product["type"] == "account":
        delivered_value = order["generated_password"]
        user_text = (
            f"Payment confirmed!\n\n"
            f"Email: {order['email']}\n"
            f"Password: {delivered_value}\n\n"
            f"Save these credentials now."
        )
        admin_extra = f"\nEmail: {order['email']}\nPassword: {delivered_value}"
    else:
        stock_item = await db.get_available_stock_item(order["product_id"])
        if not stock_item:
            await db.update_user_balance(order["user_id"], order["amount_usd"])
            await db.update_order_status(order_id, "cancelled")
            try:
                await bot.send_message(
                    order["user_id"],
                    f"Payment received but product is out of stock.\n"
                    f"${order['amount_usd']:.2f} credited to your balance.",
                )
            except Exception:
                pass
            return
        await db.mark_stock_sold(stock_item["id"], order["user_id"])
        delivered_value = stock_item["value"]
        user_text = (
            f"Payment confirmed!\n\n"
            f"Product: {product['name']}\n"
            f"Your item:\n{delivered_value}\n\n"
            f"Keep this safe."
        )
        admin_extra = f"\nDelivered: {delivered_value}"

    await db.update_order_status(order_id, "delivered", {"delivered_value": delivered_value})

    bonus_applied = await db.apply_referral_bonus_if_first_purchase(
        order["user_id"], bonus_usd=10.0
    )
    if bonus_applied:
        user_text += "\n\nYou received a $10 referral bonus!"

    try:
        await bot.send_message(order["user_id"], user_text)
    except Exception:
        pass

    try:
        await bot.send_message(
            admin_id,
            f"Order #{order_id} DELIVERED\n"
            f"User: {order['user_id']} (@{order.get('username', '?')})\n"
            f"Product: {product['name']}\n"
            f"Amount: ${order['amount_usd']:.2f} "
            f"({order['amount_crypto']:.8f} {order['crypto_currency']})"
            f"{admin_extra}",
        )
    except Exception:
        pass
```

- [ ] **Step 2: Commit**

```bash
git add bot/services/payment_checker.py
git commit -m "feat: async payment monitoring service"
```

---

### Task 9: Inline keyboards

**Files:**
- Create: `bot/keyboards/inline.py`

- [ ] **Step 1: Implement bot/keyboards/inline.py**

```python
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder


class NavCallback(CallbackData, prefix="nav"):
    to: str
    id: int = 0


class PurchaseCallback(CallbackData, prefix="buy"):
    action: str
    id: int = 0


class CryptoCallback(CallbackData, prefix="csel"):
    crypto: str
    product_id: int


class AdminCallback(CallbackData, prefix="adm"):
    action: str
    id: int = 0
    field: str = ""


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="Browse Products", callback_data=NavCallback(to="categories").pack()),
        InlineKeyboardButton(text="My Orders", callback_data=NavCallback(to="my_orders").pack()),
    )
    b.row(
        InlineKeyboardButton(text="My Balance", callback_data=NavCallback(to="balance").pack()),
        InlineKeyboardButton(text="Referral Link", callback_data=NavCallback(to="referral").pack()),
    )
    return b.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="Main Menu", callback_data=NavCallback(to="main").pack()))
    return b.as_markup()


def categories_kb(categories: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat in categories:
        b.row(InlineKeyboardButton(
            text=cat["name"],
            callback_data=NavCallback(to="products", id=cat["id"]).pack(),
        ))
    b.row(InlineKeyboardButton(text="Back", callback_data=NavCallback(to="main").pack()))
    return b.as_markup()


def products_kb(products: list[dict], category_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in products:
        suffix = "" if p["type"] == "account" else f" ({p.get('stock_count', 0)} left)"
        b.row(InlineKeyboardButton(
            text=f"{p['name']} — ${p['price_usd']:.2f}{suffix}",
            callback_data=NavCallback(to="product_detail", id=p["id"]).pack(),
        ))
    b.row(InlineKeyboardButton(
        text="Back", callback_data=NavCallback(to="categories").pack()
    ))
    return b.as_markup()


def product_detail_kb(product_id: int, category_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text="Buy Now",
        callback_data=PurchaseCallback(action="start", id=product_id).pack(),
    ))
    b.row(InlineKeyboardButton(
        text="Back", callback_data=NavCallback(to="products", id=category_id).pack()
    ))
    return b.as_markup()


def crypto_select_kb(product_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for crypto in ["USDT", "BTC", "ETH"]:
        b.row(InlineKeyboardButton(
            text=crypto,
            callback_data=CryptoCallback(crypto=crypto, product_id=product_id).pack(),
        ))
    b.row(InlineKeyboardButton(text="Cancel", callback_data=NavCallback(to="main").pack()))
    return b.as_markup()


def payment_pending_kb(order_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(
        text="Check Payment",
        callback_data=PurchaseCallback(action="check", id=order_id).pack(),
    ))
    b.row(InlineKeyboardButton(
        text="Cancel",
        callback_data=PurchaseCallback(action="cancel", id=order_id).pack(),
    ))
    return b.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="Categories", callback_data=AdminCallback(action="cats").pack()),
        InlineKeyboardButton(text="Products", callback_data=AdminCallback(action="prods_cat").pack()),
    )
    b.row(
        InlineKeyboardButton(text="Add Stock", callback_data=AdminCallback(action="stock_cat").pack()),
        InlineKeyboardButton(text="Orders", callback_data=AdminCallback(action="orders_filter").pack()),
    )
    b.row(
        InlineKeyboardButton(text="Stats", callback_data=AdminCallback(action="stats").pack()),
        InlineKeyboardButton(text="Broadcast", callback_data=AdminCallback(action="broadcast").pack()),
    )
    return b.as_markup()


def admin_categories_kb(categories: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat in categories:
        label = cat["name"] + ("" if cat["is_active"] else " [OFF]")
        b.row(InlineKeyboardButton(
            text=label,
            callback_data=AdminCallback(action="cat_view", id=cat["id"]).pack(),
        ))
    b.row(InlineKeyboardButton(text="+ Add", callback_data=AdminCallback(action="cat_add").pack()))
    b.row(InlineKeyboardButton(text="Back", callback_data=AdminCallback(action="menu").pack()))
    return b.as_markup()


def admin_cat_actions_kb(cat_id: int, is_active: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="Edit Name", callback_data=AdminCallback(action="cat_edit_name", id=cat_id).pack()),
        InlineKeyboardButton(
            text="Deactivate" if is_active else "Activate",
            callback_data=AdminCallback(action="cat_toggle", id=cat_id).pack(),
        ),
    )
    b.row(InlineKeyboardButton(text="Delete", callback_data=AdminCallback(action="cat_delete_confirm", id=cat_id).pack()))
    b.row(InlineKeyboardButton(text="Back", callback_data=AdminCallback(action="cats").pack()))
    return b.as_markup()


def admin_products_kb(products: list[dict], cat_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in products:
        label = f"{p['name']} ${p['price_usd']:.2f}" + ("" if p["is_active"] else " [OFF]")
        b.row(InlineKeyboardButton(
            text=label,
            callback_data=AdminCallback(action="prod_view", id=p["id"]).pack(),
        ))
    b.row(InlineKeyboardButton(text="+ Add Product", callback_data=AdminCallback(action="prod_add", id=cat_id).pack()))
    b.row(InlineKeyboardButton(text="Back", callback_data=AdminCallback(action="cats").pack()))
    return b.as_markup()


def admin_prod_actions_kb(prod_id: int, is_active: bool, prod_type: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="Edit Name", callback_data=AdminCallback(action="prod_edit", id=prod_id, field="name").pack()),
        InlineKeyboardButton(text="Edit Price", callback_data=AdminCallback(action="prod_edit", id=prod_id, field="price_usd").pack()),
    )
    b.row(InlineKeyboardButton(text="Edit Description", callback_data=AdminCallback(action="prod_edit", id=prod_id, field="description").pack()))
    b.row(
        InlineKeyboardButton(
            text="Deactivate" if is_active else "Activate",
            callback_data=AdminCallback(action="prod_toggle", id=prod_id).pack(),
        ),
        InlineKeyboardButton(text="Delete", callback_data=AdminCallback(action="prod_delete_confirm", id=prod_id).pack()),
    )
    if prod_type == "string":
        b.row(InlineKeyboardButton(text="View Stock", callback_data=AdminCallback(action="prod_stock", id=prod_id).pack()))
    b.row(InlineKeyboardButton(text="Back", callback_data=AdminCallback(action="prods_cat").pack()))
    return b.as_markup()


def admin_orders_filter_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for status in ["pending", "paid", "delivered", "all"]:
        b.row(InlineKeyboardButton(
            text=status.capitalize(),
            callback_data=AdminCallback(action=f"orders_{status}").pack(),
        ))
    b.row(InlineKeyboardButton(text="Back", callback_data=AdminCallback(action="menu").pack()))
    return b.as_markup()


def confirm_delete_kb(action: str, item_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="Yes, delete", callback_data=AdminCallback(action=f"{action}_yes", id=item_id).pack()),
        InlineKeyboardButton(text="Cancel", callback_data=AdminCallback(action="menu").pack()),
    )
    return b.as_markup()


def prod_type_kb(cat_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="Account (email+pass)", callback_data=AdminCallback(action="prod_type_account", id=cat_id).pack()),
        InlineKeyboardButton(text="String (API key etc)", callback_data=AdminCallback(action="prod_type_string", id=cat_id).pack()),
    )
    b.row(InlineKeyboardButton(text="Cancel", callback_data=AdminCallback(action="menu").pack()))
    return b.as_markup()


def admin_stock_cats_kb(categories: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for cat in categories:
        b.row(InlineKeyboardButton(
            text=cat["name"],
            callback_data=AdminCallback(action="stock_cat_prods", id=cat["id"]).pack(),
        ))
    b.row(InlineKeyboardButton(text="Back", callback_data=AdminCallback(action="menu").pack()))
    return b.as_markup()


def admin_stock_prods_kb(products: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in products:
        b.row(InlineKeyboardButton(
            text=p["name"],
            callback_data=AdminCallback(action="stock_add", id=p["id"]).pack(),
        ))
    b.row(InlineKeyboardButton(text="Back", callback_data=AdminCallback(action="stock_cat").pack()))
    return b.as_markup()
```

- [ ] **Step 2: Commit**

```bash
git add bot/keyboards/inline.py
git commit -m "feat: inline keyboard builders"
```

---

### Task 10: Admin middleware

**Files:**
- Create: `bot/middlewares/auth.py`

- [ ] **Step 1: Implement bot/middlewares/auth.py**

```python
from typing import Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from bot.config import Config


class AdminMiddleware(BaseMiddleware):
    def __init__(self, config: Config) -> None:
        self._admin_id = config.admin_telegram_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id != self._admin_id:
            if isinstance(event, CallbackQuery):
                await event.answer("Access denied.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("Access denied.")
            return
        return await handler(event, data)
```

- [ ] **Step 2: Commit**

```bash
git add bot/middlewares/auth.py
git commit -m "feat: admin-only middleware"
```

---

### Task 11: Start handler

**Files:**
- Create: `bot/handlers/start.py`

- [ ] **Step 1: Implement bot/handlers/start.py**

```python
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot import db
from bot.keyboards.inline import main_menu_kb, back_to_main_kb, NavCallback

router = Router()

WELCOME = "Welcome to the Store!\n\nBrowse products and pay with crypto."


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    args = message.text.split(maxsplit=1)
    referred_by: int | None = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1][4:])
            if ref_id != message.from_user.id:
                referred_by = ref_id
        except ValueError:
            pass

    await db.get_or_create_user(message.from_user.id, message.from_user.username, referred_by)

    if referred_by:
        existing_ref = await db.get_user(referred_by)
        if existing_ref:
            # Only add referral record if referred user is new (no prior referral)
            user = await db.get_user(message.from_user.id)
            if user and user.get("referred_by") == referred_by:
                await db.add_referral(referred_by, message.from_user.id)

    await message.answer(WELCOME, reply_markup=main_menu_kb())


@router.callback_query(NavCallback.filter(F.to == "main"))
async def show_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(WELCOME, reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(NavCallback.filter(F.to == "my_orders"))
async def show_my_orders(callback: CallbackQuery) -> None:
    orders = await db.get_user_orders(callback.from_user.id)
    if not orders:
        text = "You have no orders yet."
    else:
        lines = [f"#{o['id']} {o['status'].upper()} — {o['product_name']} ${o['amount_usd']:.2f}" for o in orders]
        text = "Your orders:\n\n" + "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=back_to_main_kb())
    await callback.answer()


@router.callback_query(NavCallback.filter(F.to == "balance"))
async def show_balance(callback: CallbackQuery) -> None:
    user = await db.get_user(callback.from_user.id)
    balance = user["balance"] if user else 0.0
    await callback.message.edit_text(
        f"Your balance: ${balance:.2f} USD\n\nUsed automatically when you buy products.",
        reply_markup=back_to_main_kb(),
    )
    await callback.answer()
```

- [ ] **Step 2: Commit**

```bash
git add bot/handlers/start.py
git commit -m "feat: start handler and main menu"
```

---

### Task 12: Catalog handler

**Files:**
- Create: `bot/handlers/catalog.py`

- [ ] **Step 1: Implement bot/handlers/catalog.py**

```python
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot import db
from bot.keyboards.inline import (
    NavCallback, categories_kb, products_kb, product_detail_kb, back_to_main_kb
)

router = Router()


@router.callback_query(NavCallback.filter(F.to == "categories"))
async def show_categories(callback: CallbackQuery) -> None:
    categories = await db.get_active_categories()
    if not categories:
        await callback.answer("No categories available yet.", show_alert=True)
        return
    await callback.message.edit_text("Choose a category:", reply_markup=categories_kb(categories))
    await callback.answer()


@router.callback_query(NavCallback.filter(F.to == "products"))
async def show_products(callback: CallbackQuery, callback_data: NavCallback) -> None:
    cat_id = callback_data.id
    cat = await db.get_category(cat_id)
    if not cat:
        await callback.answer("Category not found.", show_alert=True)
        return
    products = await db.get_products_by_category(cat_id)
    for p in products:
        if p["type"] == "string":
            counts = await db.get_stock_count(p["id"])
            p["stock_count"] = counts["available"]
    if not products:
        await callback.answer("No products in this category.", show_alert=True)
        return
    await callback.message.edit_text(
        f"{cat['name']}\n\nChoose a product:",
        reply_markup=products_kb(products, cat_id),
    )
    await callback.answer()


@router.callback_query(NavCallback.filter(F.to == "product_detail"))
async def show_product_detail(callback: CallbackQuery, callback_data: NavCallback) -> None:
    product = await db.get_product(callback_data.id)
    if not product:
        await callback.answer("Product not found.", show_alert=True)
        return
    if product["type"] == "string":
        counts = await db.get_stock_count(product["id"])
        stock_line = f"In stock: {counts['available']}"
        if counts["available"] == 0:
            stock_line += " (out of stock)"
    else:
        stock_line = "Available"
    desc = product["description"] or ""
    text = f"{product['name']}\n\n{desc}\n\nPrice: ${product['price_usd']:.2f}\n{stock_line}".strip()
    await callback.message.edit_text(
        text,
        reply_markup=product_detail_kb(product["id"], product["category_id"]),
    )
    await callback.answer()
```

- [ ] **Step 2: Commit**

```bash
git add bot/handlers/catalog.py
git commit -m "feat: catalog browsing handler"
```

---

### Task 13: Purchase handler

**Files:**
- Create: `bot/handlers/purchase.py`

- [ ] **Step 1: Implement bot/handlers/purchase.py**

```python
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot import db
from bot.keyboards.inline import (
    PurchaseCallback, CryptoCallback, NavCallback,
    crypto_select_kb, payment_pending_kb, back_to_main_kb,
)
from bot.services.bitunix import BitunixClient
from bot.services.password import generate_password
from bot.services.payment_checker import start_monitor, stop_monitor
from bot.config import Config

router = Router()


class PurchaseStates(StatesGroup):
    waiting_email = State()


@router.callback_query(PurchaseCallback.filter(F.action == "start"))
async def buy_start(callback: CallbackQuery, callback_data: PurchaseCallback, state: FSMContext) -> None:
    product = await db.get_product(callback_data.id)
    if not product or not product["is_active"]:
        await callback.answer("Product not available.", show_alert=True)
        return
    if product["type"] == "string":
        counts = await db.get_stock_count(product["id"])
        if counts["available"] == 0:
            await callback.answer("Out of stock.", show_alert=True)
            return
        await state.clear()
        await callback.message.edit_text(
            f"Choose payment method for {product['name']} (${product['price_usd']:.2f}):",
            reply_markup=crypto_select_kb(product["id"]),
        )
    else:
        await state.set_state(PurchaseStates.waiting_email)
        await state.update_data(product_id=product["id"])
        await callback.message.edit_text(
            f"Buying: {product['name']} — ${product['price_usd']:.2f}\n\nPlease enter your email address:"
        )
    await callback.answer()


@router.message(PurchaseStates.waiting_email)
async def receive_email(message: Message, state: FSMContext) -> None:
    email = message.text.strip()
    if "@" not in email or "." not in email:
        await message.answer("Invalid email. Please enter a valid email address:")
        return
    data = await state.get_data()
    product_id = data["product_id"]
    product = await db.get_product(product_id)
    await state.update_data(email=email)
    await state.clear()
    await message.answer(
        f"Email: {email}\nProduct: {product['name']} — ${product['price_usd']:.2f}\n\n"
        f"Choose payment crypto:",
        reply_markup=crypto_select_kb(product_id),
    )


@router.callback_query(CryptoCallback.filter())
async def select_crypto(
    callback: CallbackQuery,
    callback_data: CryptoCallback,
    state: FSMContext,
    bitunix: BitunixClient,
    config: Config,
) -> None:
    product = await db.get_product(callback_data.product_id)
    if not product:
        await callback.answer("Product not found.", show_alert=True)
        return

    user = await db.get_user(callback.from_user.id)
    balance = user["balance"] if user else 0.0
    price = product["price_usd"]
    crypto = callback_data.crypto

    # Balance deduction
    use_balance = min(balance, price)
    crypto_needed = price - use_balance

    try:
        if crypto_needed > 0:
            amount_crypto = await bitunix.get_crypto_amount(crypto_needed, crypto)
            deposit_address = await bitunix.get_deposit_address(crypto)
        else:
            amount_crypto = 0.0
            deposit_address = ""
    except Exception as e:
        await callback.answer("Error contacting payment API. Try again.", show_alert=True)
        return

    # Get email from FSM data (None for string products)
    fsm_data = await state.get_data()
    email = fsm_data.get("email")
    generated_password = generate_password() if product["type"] == "account" else None

    order_id = await db.create_order(
        user_id=callback.from_user.id,
        product_id=product["id"],
        email=email,
        generated_password=generated_password,
        amount_usd=price,
        amount_crypto=amount_crypto,
        crypto_currency=crypto,
        deposit_address=deposit_address,
        created_at_ms=int(time.time() * 1000),
    )

    if use_balance > 0:
        await db.update_user_balance(callback.from_user.id, -use_balance)

    if crypto_needed <= 0:
        # Fully paid with balance
        from bot.services.payment_checker import _deliver_and_notify
        order = await db.get_order(order_id)
        await db.update_order_status(order_id, "paid")
        await _deliver_and_notify(order_id, order, callback.bot, config.admin_telegram_id)
        await callback.message.edit_text("Payment complete! Check your messages above.")
        await callback.answer()
        return

    text = (
        f"Order #{order_id}\n\n"
        f"Product: {product['name']}\n"
        f"Price: ${price:.2f}"
    )
    if use_balance > 0:
        text += f"\nBalance used: -${use_balance:.2f}"
    text += (
        f"\nTo pay: {amount_crypto:.8f} {crypto}\n\n"
        f"Send to:\n`{deposit_address}`\n\n"
        f"You have 30 minutes. Press Check Payment after sending."
    )

    await start_monitor(
        order_id, callback.bot, bitunix,
        config.order_timeout_minutes, config.payment_check_interval,
        config.admin_telegram_id,
    )

    await callback.message.edit_text(
        text, reply_markup=payment_pending_kb(order_id), parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(PurchaseCallback.filter(F.action == "check"))
async def check_payment(callback: CallbackQuery, callback_data: PurchaseCallback) -> None:
    order = await db.get_order(callback_data.id)
    if not order:
        await callback.answer("Order not found.", show_alert=True)
        return
    status_msg = {
        "pending": "Payment not confirmed yet. Please wait or send the exact amount.",
        "delivered": "Your order has been delivered!",
        "expired": "This order has expired.",
        "cancelled": "This order was cancelled.",
    }
    await callback.answer(status_msg.get(order["status"], order["status"]), show_alert=True)


@router.callback_query(PurchaseCallback.filter(F.action == "cancel"))
async def cancel_order(callback: CallbackQuery, callback_data: PurchaseCallback) -> None:
    order = await db.get_order(callback_data.id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Order not found.", show_alert=True)
        return
    if order["status"] != "pending":
        await callback.answer("Cannot cancel this order.", show_alert=True)
        return
    stop_monitor(callback_data.id)
    await db.update_order_status(callback_data.id, "cancelled")
    await callback.message.edit_text("Order cancelled.", reply_markup=back_to_main_kb())
    await callback.answer()
```

- [ ] **Step 2: Commit**

```bash
git add bot/handlers/purchase.py
git commit -m "feat: purchase flow handler with FSM"
```

---

### Task 14: Admin handler — categories and products

**Files:**
- Create: `bot/handlers/admin.py`

- [ ] **Step 1: Implement bot/handlers/admin.py (first half)**

```python
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot import db
from bot.keyboards.inline import (
    AdminCallback, admin_menu_kb, admin_categories_kb, admin_cat_actions_kb,
    admin_products_kb, admin_prod_actions_kb, prod_type_kb,
    confirm_delete_kb, back_to_main_kb,
)

router = Router()


class AdminStates(StatesGroup):
    waiting_cat_name = State()
    waiting_cat_new_name = State()
    waiting_prod_name = State()
    waiting_prod_price = State()
    waiting_prod_description = State()
    waiting_prod_edit_value = State()
    waiting_stock_items = State()
    waiting_broadcast_text = State()
    confirm_broadcast = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Admin Panel", reply_markup=admin_menu_kb())


@router.callback_query(AdminCallback.filter(F.action == "menu"))
async def admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Admin Panel", reply_markup=admin_menu_kb())
    await callback.answer()


# --- Categories ---

@router.callback_query(AdminCallback.filter(F.action == "cats"))
async def admin_cats(callback: CallbackQuery) -> None:
    cats = await db.get_all_categories()
    await callback.message.edit_text("Categories:", reply_markup=admin_categories_kb(cats))
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "cat_view"))
async def admin_cat_view(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    cat = await db.get_category(callback_data.id)
    if not cat:
        await callback.answer("Not found.", show_alert=True)
        return
    status = "Active" if cat["is_active"] else "Inactive"
    await callback.message.edit_text(
        f"Category: {cat['name']}\nStatus: {status}",
        reply_markup=admin_cat_actions_kb(cat["id"], bool(cat["is_active"])),
    )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "cat_add"))
async def admin_cat_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_cat_name)
    await callback.message.edit_text("Enter category name:")
    await callback.answer()


@router.message(AdminStates.waiting_cat_name)
async def receive_cat_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    cat_id = await db.add_category(name)
    await state.clear()
    cats = await db.get_all_categories()
    await message.answer(f"Category '{name}' created.", reply_markup=admin_categories_kb(cats))


@router.callback_query(AdminCallback.filter(F.action == "cat_edit_name"))
async def admin_cat_edit_name(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_cat_new_name)
    await state.update_data(cat_id=callback_data.id)
    await callback.message.edit_text("Enter new category name:")
    await callback.answer()


@router.message(AdminStates.waiting_cat_new_name)
async def receive_cat_new_name(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await db.update_category_name(data["cat_id"], message.text.strip())
    await state.clear()
    cats = await db.get_all_categories()
    await message.answer("Category renamed.", reply_markup=admin_categories_kb(cats))


@router.callback_query(AdminCallback.filter(F.action == "cat_toggle"))
async def admin_cat_toggle(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    await db.toggle_category(callback_data.id)
    cat = await db.get_category(callback_data.id)
    await callback.message.edit_text(
        f"Category: {cat['name']}\nStatus: {'Active' if cat['is_active'] else 'Inactive'}",
        reply_markup=admin_cat_actions_kb(cat["id"], bool(cat["is_active"])),
    )
    await callback.answer("Toggled.")


@router.callback_query(AdminCallback.filter(F.action == "cat_delete_confirm"))
async def admin_cat_delete_confirm(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    cat = await db.get_category(callback_data.id)
    await callback.message.edit_text(
        f"Delete category '{cat['name']}'? This cannot be undone.",
        reply_markup=confirm_delete_kb("cat_delete", callback_data.id),
    )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "cat_delete_yes"))
async def admin_cat_delete(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    await db.delete_category(callback_data.id)
    cats = await db.get_all_categories()
    await callback.message.edit_text("Category deleted.", reply_markup=admin_categories_kb(cats))
    await callback.answer()


# --- Products ---

@router.callback_query(AdminCallback.filter(F.action == "prods_cat"))
async def admin_prods_cat(callback: CallbackQuery) -> None:
    cats = await db.get_all_categories()
    from bot.keyboards.inline import admin_categories_kb
    await callback.message.edit_text("Select category to manage products:", reply_markup=admin_categories_kb(cats))
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "prod_add"))
async def admin_prod_add(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    await callback.message.edit_text(
        "Select product type:",
        reply_markup=prod_type_kb(callback_data.id),
    )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action.in_({"prod_type_account", "prod_type_string"})))
async def admin_prod_type_selected(
    callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext
) -> None:
    prod_type = "account" if callback_data.action == "prod_type_account" else "string"
    await state.set_state(AdminStates.waiting_prod_name)
    await state.update_data(cat_id=callback_data.id, prod_type=prod_type)
    await callback.message.edit_text("Enter product name:")
    await callback.answer()


@router.message(AdminStates.waiting_prod_name)
async def receive_prod_name(message: Message, state: FSMContext) -> None:
    await state.update_data(prod_name=message.text.strip())
    await state.set_state(AdminStates.waiting_prod_price)
    await message.answer("Enter price in USD (e.g. 5.99):")


@router.message(AdminStates.waiting_prod_price)
async def receive_prod_price(message: Message, state: FSMContext) -> None:
    try:
        price = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Invalid price. Enter a number (e.g. 5.99):")
        return
    await state.update_data(prod_price=price)
    await state.set_state(AdminStates.waiting_prod_description)
    await message.answer("Enter description (or send '-' to skip):")


@router.message(AdminStates.waiting_prod_description)
async def receive_prod_description(message: Message, state: FSMContext) -> None:
    desc = "" if message.text.strip() == "-" else message.text.strip()
    data = await state.get_data()
    prod_id = await db.add_product(
        data["cat_id"], data["prod_name"], desc, data["prod_price"], data["prod_type"]
    )
    await state.clear()
    products = await db.get_products_by_category(data["cat_id"], active_only=False)
    await message.answer(
        f"Product '{data['prod_name']}' created (ID: {prod_id}).",
        reply_markup=admin_products_kb(products, data["cat_id"]),
    )


@router.callback_query(AdminCallback.filter(F.action == "prod_view"))
async def admin_prod_view(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    prod = await db.get_product(callback_data.id)
    if not prod:
        await callback.answer("Not found.", show_alert=True)
        return
    stock_info = ""
    if prod["type"] == "string":
        counts = await db.get_stock_count(prod["id"])
        stock_info = f"\nStock: {counts['available']}/{counts['total']}"
    await callback.message.edit_text(
        f"{prod['name']}\nPrice: ${prod['price_usd']:.2f}\nType: {prod['type']}{stock_info}\n{prod['description'] or ''}",
        reply_markup=admin_prod_actions_kb(prod["id"], bool(prod["is_active"]), prod["type"]),
    )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "prod_edit"))
async def admin_prod_edit(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_prod_edit_value)
    await state.update_data(prod_id=callback_data.id, edit_field=callback_data.field)
    field_labels = {"name": "name", "price_usd": "price (USD)", "description": "description"}
    await callback.message.edit_text(f"Enter new {field_labels[callback_data.field]}:")
    await callback.answer()


@router.message(AdminStates.waiting_prod_edit_value)
async def receive_prod_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    value: str | float = message.text.strip()
    if data["edit_field"] == "price_usd":
        try:
            value = float(value.replace(",", "."))
        except ValueError:
            await message.answer("Invalid price. Enter a number:")
            return
    await db.update_product_field(data["prod_id"], data["edit_field"], value)
    await state.clear()
    prod = await db.get_product(data["prod_id"])
    await message.answer(
        "Updated.",
        reply_markup=admin_prod_actions_kb(prod["id"], bool(prod["is_active"]), prod["type"]),
    )


@router.callback_query(AdminCallback.filter(F.action == "prod_toggle"))
async def admin_prod_toggle(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    await db.toggle_product(callback_data.id)
    prod = await db.get_product(callback_data.id)
    await callback.message.edit_text(
        f"{prod['name']} — {'Active' if prod['is_active'] else 'Inactive'}",
        reply_markup=admin_prod_actions_kb(prod["id"], bool(prod["is_active"]), prod["type"]),
    )
    await callback.answer("Toggled.")


@router.callback_query(AdminCallback.filter(F.action == "prod_delete_confirm"))
async def admin_prod_delete_confirm(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    prod = await db.get_product(callback_data.id)
    await callback.message.edit_text(
        f"Delete product '{prod['name']}'?",
        reply_markup=confirm_delete_kb("prod_delete", callback_data.id),
    )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "prod_delete_yes"))
async def admin_prod_delete(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    prod = await db.get_product(callback_data.id)
    cat_id = prod["category_id"]
    await db.delete_product(callback_data.id)
    products = await db.get_products_by_category(cat_id, active_only=False)
    await callback.message.edit_text("Product deleted.", reply_markup=admin_products_kb(products, cat_id))
    await callback.answer()
```

- [ ] **Step 2: Commit**

```bash
git add bot/handlers/admin.py
git commit -m "feat: admin handler - categories and products"
```

---

### Task 15: Admin handler — stock, orders, stats, broadcast

**Files:**
- Modify: `bot/handlers/admin.py` (append)

- [ ] **Step 1: Append to bot/handlers/admin.py**

```python
# --- Stock ---

@router.callback_query(AdminCallback.filter(F.action == "stock_cat"))
async def admin_stock_cat(callback: CallbackQuery) -> None:
    from bot.keyboards.inline import admin_stock_cats_kb
    cats = await db.get_all_categories()
    await callback.message.edit_text("Select category:", reply_markup=admin_stock_cats_kb(cats))
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "stock_cat_prods"))
async def admin_stock_cat_prods(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    from bot.keyboards.inline import admin_stock_prods_kb
    prods = await db.get_products_by_category(callback_data.id, active_only=False)
    string_prods = [p for p in prods if p["type"] == "string"]
    if not string_prods:
        await callback.answer("No string products in this category.", show_alert=True)
        return
    await callback.message.edit_text("Select product to add stock:", reply_markup=admin_stock_prods_kb(string_prods))
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "stock_add"))
async def admin_stock_add(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext) -> None:
    prod = await db.get_product(callback_data.id)
    await state.set_state(AdminStates.waiting_stock_items)
    await state.update_data(prod_id=callback_data.id)
    counts = await db.get_stock_count(callback_data.id)
    await callback.message.edit_text(
        f"Product: {prod['name']}\nCurrent stock: {counts['available']} available\n\n"
        f"Send items one per line:"
    )
    await callback.answer()


@router.message(AdminStates.waiting_stock_items)
async def receive_stock_items(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    items = [line.strip() for line in message.text.splitlines() if line.strip()]
    if not items:
        await message.answer("No items found. Send at least one item:")
        return
    added = await db.add_stock_items(data["prod_id"], items)
    await state.clear()
    counts = await db.get_stock_count(data["prod_id"])
    await message.answer(
        f"{added} items added. Total available: {counts['available']}",
        reply_markup=admin_menu_kb(),
    )


@router.callback_query(AdminCallback.filter(F.action == "prod_stock"))
async def admin_prod_stock(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    prod = await db.get_product(callback_data.id)
    counts = await db.get_stock_count(callback_data.id)
    await callback.message.edit_text(
        f"Stock for '{prod['name']}':\nAvailable: {counts['available']}\nTotal loaded: {counts['total']}",
        reply_markup=admin_prod_actions_kb(prod["id"], bool(prod["is_active"]), prod["type"]),
    )
    await callback.answer()


# --- Orders ---

@router.callback_query(AdminCallback.filter(F.action == "orders_filter"))
async def admin_orders_filter(callback: CallbackQuery) -> None:
    from bot.keyboards.inline import admin_orders_filter_kb
    await callback.message.edit_text("Filter orders:", reply_markup=admin_orders_filter_kb())
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action.in_({"orders_pending", "orders_paid", "orders_delivered", "orders_all"})))
async def admin_orders_list(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    status = callback_data.action.replace("orders_", "")
    orders = await db.get_orders_by_status(status)
    if not orders:
        await callback.answer("No orders found.", show_alert=True)
        return
    lines = []
    for o in orders:
        lines.append(f"#{o['id']} {o['status'].upper()} @{o.get('username','?')} {o['product_name']} ${o['amount_usd']:.2f}")
    from bot.keyboards.inline import admin_orders_filter_kb
    await callback.message.edit_text(
        f"Orders ({status}):\n\n" + "\n".join(lines),
        reply_markup=admin_orders_filter_kb(),
    )
    await callback.answer()


# --- Stats ---

@router.callback_query(AdminCallback.filter(F.action == "stats"))
async def admin_stats(callback: CallbackQuery) -> None:
    stats = await db.get_admin_stats()
    await callback.message.edit_text(
        f"Stats:\n\nTotal orders delivered: {stats['total_orders']}\n"
        f"Total revenue: ${stats['revenue']:.2f}\n"
        f"Total users: {stats['total_users']}",
        reply_markup=admin_menu_kb(),
    )
    await callback.answer()


# --- Broadcast ---

@router.callback_query(AdminCallback.filter(F.action == "broadcast"))
async def admin_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_broadcast_text)
    await callback.message.edit_text("Enter message to broadcast to all users:")
    await callback.answer()


@router.message(AdminStates.waiting_broadcast_text)
async def receive_broadcast_text(message: Message, state: FSMContext) -> None:
    await state.update_data(broadcast_text=message.text)
    await state.set_state(AdminStates.confirm_broadcast)
    users = await db.get_all_users()
    await message.answer(
        f"Send to {len(users)} users?\n\nPreview:\n{message.text}",
        reply_markup=AdminCallback(action="broadcast_confirm").pack() and  # inline confirm
        __import__('aiogram').types.InlineKeyboardMarkup(inline_keyboard=[[
            __import__('aiogram').types.InlineKeyboardButton(text="Send", callback_data=AdminCallback(action="broadcast_confirm").pack()),
            __import__('aiogram').types.InlineKeyboardButton(text="Cancel", callback_data=AdminCallback(action="menu").pack()),
        ]])
    )


@router.callback_query(AdminCallback.filter(F.action == "broadcast_confirm"))
async def admin_broadcast_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()
    users = await db.get_all_users()
    sent = 0
    failed = 0
    for user in users:
        try:
            await callback.bot.send_message(user["id"], text)
            sent += 1
        except Exception:
            failed += 1
        import asyncio
        if sent % 25 == 0:
            await asyncio.sleep(1)  # Respect Telegram rate limits
    await callback.message.edit_text(
        f"Broadcast complete.\nSent: {sent}\nFailed: {failed}",
        reply_markup=admin_menu_kb(),
    )
    await callback.answer()
```

- [ ] **Step 2: Fix broadcast keyboard (clean up the import hack above)**

Replace the `receive_broadcast_text` function's reply_markup with a proper builder:

```python
@router.message(AdminStates.waiting_broadcast_text)
async def receive_broadcast_text(message: Message, state: FSMContext) -> None:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    await state.update_data(broadcast_text=message.text)
    await state.set_state(AdminStates.confirm_broadcast)
    users = await db.get_all_users()
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="Send", callback_data=AdminCallback(action="broadcast_confirm").pack()),
        InlineKeyboardButton(text="Cancel", callback_data=AdminCallback(action="menu").pack()),
    )
    await message.answer(
        f"Send to {len(users)} users?\n\nPreview:\n{message.text}",
        reply_markup=b.as_markup(),
    )
```

- [ ] **Step 3: Commit**

```bash
git add bot/handlers/admin.py
git commit -m "feat: admin handler - stock, orders, stats, broadcast"
```

---

### Task 16: Referral handler

**Files:**
- Create: `bot/handlers/referral.py`

- [ ] **Step 1: Implement bot/handlers/referral.py**

```python
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot import db
from bot.keyboards.inline import NavCallback, back_to_main_kb

router = Router()


@router.callback_query(NavCallback.filter(F.to == "referral"))
async def show_referral(callback: CallbackQuery) -> None:
    user = await db.get_user(callback.from_user.id)
    stats = await db.get_referral_stats(callback.from_user.id)
    bot_me = await callback.bot.get_me()
    link = f"https://t.me/{bot_me.username}?start=ref_{callback.from_user.id}"
    balance = user["balance"] if user else 0.0
    text = (
        f"Your referral link:\n{link}\n\n"
        f"Referrals made: {stats['count']}\n"
        f"Bonus earned: ${stats['total_earned']:.2f}\n"
        f"Your balance: ${balance:.2f}\n\n"
        f"Both you and your friend get $10 after their first purchase."
    )
    await callback.message.edit_text(text, reply_markup=back_to_main_kb())
    await callback.answer()
```

- [ ] **Step 2: Commit**

```bash
git add bot/handlers/referral.py
git commit -m "feat: referral link handler"
```

---

### Task 17: Main entry point

**Files:**
- Create: `bot/main.py`

- [ ] **Step 1: Implement bot/main.py**

```python
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import load_config
from bot import db
from bot.services.bitunix import BitunixClient
from bot.services.payment_checker import restore_monitors
from bot.handlers import start, catalog, purchase, admin, referral
from bot.middlewares.auth import AdminMiddleware


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()

    os.makedirs(os.path.dirname(config.db_path), exist_ok=True)
    await db.connect(config.db_path)

    bot = Bot(token=config.telegram_token)
    dp = Dispatcher(storage=MemoryStorage())

    bitunix = BitunixClient(config.bitunix_api_key, config.bitunix_secret_key)

    # Inject dependencies into handler context
    dp["config"] = config
    dp["bitunix"] = bitunix

    # Admin router gets the admin-only middleware
    admin_router = admin.router
    admin_router.message.middleware(AdminMiddleware(config))
    admin_router.callback_query.middleware(AdminMiddleware(config))

    dp.include_routers(
        start.router,
        catalog.router,
        purchase.router,
        referral.router,
        admin_router,
    )

    await restore_monitors(
        bot, bitunix,
        config.order_timeout_minutes,
        config.payment_check_interval,
        config.admin_telegram_id,
    )

    logging.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bitunix.close()
        logging.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify imports resolve**

```bash
python -c "from bot.main import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Install dependencies**

```bash
pip install -r requirements.txt
```

- [ ] **Step 4: Copy .env.example and fill in credentials**

```bash
cp .env.example .env
# Fill in: TELEGRAM_BOT_TOKEN, BITUNIX_API_KEY, BITUNIX_SECRET_KEY, ADMIN_TELEGRAM_ID
```

- [ ] **Step 5: Run the bot**

```bash
python -m bot.main
```

Expected: `Bot starting...` log line with no errors. Send `/start` to the bot and confirm main menu appears with 4 buttons.

- [ ] **Step 6: Run all tests**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add bot/main.py
git commit -m "feat: main entry point, bot wiring complete"
```

---

## Self-Review

### Spec Coverage
- [x] Two product types (account / string) — Tasks 5, 13
- [x] Dynamic categories admin — Tasks 4, 14
- [x] USD prices converted to crypto at payment — Task 7 (get_crypto_amount)
- [x] Admin panel via Telegram buttons — Tasks 9, 14, 15
- [x] Bitunix API with HMAC-SHA256 — Task 7
- [x] Deposit address per crypto, polling every 30s — Tasks 7, 8
- [x] English only — all handlers
- [x] Referral system ($10 mutual on first purchase) — Tasks 3, 8, 16
- [x] Single admin, ADMIN_TELEGRAM_ID — Tasks 2, 10
- [x] SQLite — Tasks 2-5
- [x] Credentials in .env — Tasks 1, 2
- [x] Order timeout (30 min expiry) — Task 8
- [x] Stock management for string products — Tasks 4, 15
- [x] Balance usage at checkout — Task 13

### Type Consistency
- `NavCallback`, `PurchaseCallback`, `CryptoCallback`, `AdminCallback` defined once in `keyboards/inline.py`, imported everywhere
- `db.*` functions return `dict | None` or `list[dict]` consistently
- `BitunixClient` methods are async throughout
- `AdminStates` and `PurchaseStates` defined in their respective handler files

### No Placeholders
No TBDs, TODOs, or "implement later" in any task.
