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
    assert _db is not None
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


# --- Users ---

async def get_or_create_user(user_id: int, username: str | None, referred_by: int | None = None) -> dict:
    await _db.execute(
        "INSERT OR IGNORE INTO users (id, username, referred_by) VALUES (?, ?, ?)",
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


# --- Referrals ---

async def add_referral(referrer_id: int, referred_id: int) -> None:
    await _db.execute(
        "INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
        (referrer_id, referred_id),
    )
    await _db.commit()


async def apply_referral_bonus_if_first_purchase(user_id: int, bonus_usd: float) -> bool:
    """Returns True if bonus was applied (first purchase triggers it). Atomic to prevent double-apply."""
    cur = await _db.execute(
        "UPDATE referrals SET bonus_applied = 1 WHERE referred_id = ? AND bonus_applied = 0",
        (user_id,),
    )
    await _db.commit()
    if cur.rowcount == 0:
        return False
    async with _db.execute(
        "SELECT referrer_id FROM referrals WHERE referred_id = ?", (user_id,)
    ) as sel:
        row = await sel.fetchone()
    if row:
        await _db.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?", (bonus_usd, user_id)
        )
        await _db.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?", (bonus_usd, row["referrer_id"])
        )
        await _db.commit()
    return True


async def get_referral_stats(user_id: int, bonus_per_referral: float = 10.0) -> dict:
    async with _db.execute(
        "SELECT COUNT(*) as count FROM referrals WHERE referrer_id = ?", (user_id,)
    ) as cur:
        count_row = await cur.fetchone()
    async with _db.execute(
        "SELECT COUNT(*) as earned FROM referrals WHERE referrer_id = ? AND bonus_applied = 1",
        (user_id,),
    ) as cur:
        earned_row = await cur.fetchone()
    return {
        "count": count_row["count"],
        "total_earned": earned_row["earned"] * bonus_per_referral,
    }
