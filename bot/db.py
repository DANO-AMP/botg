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
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
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
