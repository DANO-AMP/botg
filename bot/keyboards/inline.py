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
    b.row(
        InlineKeyboardButton(text="Add Balance", callback_data=AdminCallback(action="balance_user").pack()),
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
