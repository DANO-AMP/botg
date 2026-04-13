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
    # Mapping prevents SQL injection: only these exact column names can be used
    _allowed_fields = {"name": "name", "description": "description", "price_usd": "price_usd"}
    col = _allowed_fields.get(field)
    if col is None:
        raise ValueError(f"Cannot update field: {field}")
    await _db.execute(f"UPDATE products SET {col} = ? WHERE id = ?", (value, product_id))
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
    values: list[Any] = [status]
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
