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
    if not callback.message:
        await callback.answer()
        return
    await state.clear()
    await callback.message.edit_text("Admin Panel", reply_markup=admin_menu_kb())
    await callback.answer()


# --- Categories ---

@router.callback_query(AdminCallback.filter(F.action == "cats"))
async def admin_cats(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    cats = await db.get_all_categories()
    await callback.message.edit_text("Categories:", reply_markup=admin_categories_kb(cats))
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "cat_view"))
async def admin_cat_view(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    if not callback.message:
        await callback.answer()
        return
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
    if not callback.message:
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_cat_name)
    await callback.message.edit_text("Enter category name:")
    await callback.answer()


@router.message(AdminStates.waiting_cat_name)
async def receive_cat_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if not name:
        await message.answer("Name cannot be empty. Try again:")
        return
    await db.add_category(name)
    await state.clear()
    cats = await db.get_all_categories()
    await message.answer(f"Category '{name}' created.", reply_markup=admin_categories_kb(cats))


@router.callback_query(AdminCallback.filter(F.action == "cat_edit_name"))
async def admin_cat_edit_name(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_cat_new_name)
    await state.update_data(cat_id=callback_data.id)
    await callback.message.edit_text("Enter new category name:")
    await callback.answer()


@router.message(AdminStates.waiting_cat_new_name)
async def receive_cat_new_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if not name:
        await message.answer("Name cannot be empty. Try again:")
        return
    data = await state.get_data()
    await db.update_category_name(data["cat_id"], name)
    await state.clear()
    cats = await db.get_all_categories()
    await message.answer("Category renamed.", reply_markup=admin_categories_kb(cats))


@router.callback_query(AdminCallback.filter(F.action == "cat_toggle"))
async def admin_cat_toggle(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    if not callback.message:
        await callback.answer()
        return
    await db.toggle_category(callback_data.id)
    cat = await db.get_category(callback_data.id)
    await callback.message.edit_text(
        f"Category: {cat['name']}\nStatus: {'Active' if cat['is_active'] else 'Inactive'}",
        reply_markup=admin_cat_actions_kb(cat["id"], bool(cat["is_active"])),
    )
    await callback.answer("Toggled.")


@router.callback_query(AdminCallback.filter(F.action == "cat_delete_confirm"))
async def admin_cat_delete_confirm(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    if not callback.message:
        await callback.answer()
        return
    cat = await db.get_category(callback_data.id)
    if not cat:
        await callback.answer("Not found.", show_alert=True)
        return
    await callback.message.edit_text(
        f"Delete category '{cat['name']}'? This cannot be undone.",
        reply_markup=confirm_delete_kb("cat_delete", callback_data.id),
    )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "cat_delete_yes"))
async def admin_cat_delete(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    if not callback.message:
        await callback.answer()
        return
    await db.delete_category(callback_data.id)
    cats = await db.get_all_categories()
    await callback.message.edit_text("Category deleted.", reply_markup=admin_categories_kb(cats))
    await callback.answer()


# --- Products ---

@router.callback_query(AdminCallback.filter(F.action == "prods_cat"))
async def admin_prods_cat(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    cats = await db.get_all_categories()
    await callback.message.edit_text("Select category to manage products:", reply_markup=admin_categories_kb(cats))
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "prod_add"))
async def admin_prod_add(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    if not callback.message:
        await callback.answer()
        return
    await callback.message.edit_text(
        "Select product type:",
        reply_markup=prod_type_kb(callback_data.id),
    )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action.in_({"prod_type_account", "prod_type_string"})))
async def admin_prod_type_selected(
    callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext
) -> None:
    if not callback.message:
        await callback.answer()
        return
    prod_type = "account" if callback_data.action == "prod_type_account" else "string"
    await state.set_state(AdminStates.waiting_prod_name)
    await state.update_data(cat_id=callback_data.id, prod_type=prod_type)
    await callback.message.edit_text("Enter product name:")
    await callback.answer()


@router.message(AdminStates.waiting_prod_name)
async def receive_prod_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if not name:
        await message.answer("Name cannot be empty. Try again:")
        return
    await state.update_data(prod_name=name)
    await state.set_state(AdminStates.waiting_prod_price)
    await message.answer("Enter price in USD (e.g. 5.99):")


@router.message(AdminStates.waiting_prod_price)
async def receive_prod_price(message: Message, state: FSMContext) -> None:
    try:
        price = float((message.text or "").strip().replace(",", "."))
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Invalid price. Enter a positive number (e.g. 5.99):")
        return
    await state.update_data(prod_price=price)
    await state.set_state(AdminStates.waiting_prod_description)
    await message.answer("Enter description (or send '-' to skip):")


@router.message(AdminStates.waiting_prod_description)
async def receive_prod_description(message: Message, state: FSMContext) -> None:
    desc = "" if (message.text or "").strip() == "-" else (message.text or "").strip()
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
    if not callback.message:
        await callback.answer()
        return
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
    if not callback.message:
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_prod_edit_value)
    await state.update_data(prod_id=callback_data.id, edit_field=callback_data.field)
    field_labels = {"name": "name", "price_usd": "price (USD)", "description": "description"}
    label = field_labels.get(callback_data.field, callback_data.field)
    await callback.message.edit_text(f"Enter new {label}:")
    await callback.answer()


@router.message(AdminStates.waiting_prod_edit_value)
async def receive_prod_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    raw = (message.text or "").strip()
    value: str | float = raw
    if data["edit_field"] == "price_usd":
        try:
            price = float(raw.replace(",", "."))
            if price <= 0:
                raise ValueError
            value = price
        except ValueError:
            await message.answer("Invalid price. Enter a positive number:")
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
    if not callback.message:
        await callback.answer()
        return
    await db.toggle_product(callback_data.id)
    prod = await db.get_product(callback_data.id)
    await callback.message.edit_text(
        f"{prod['name']} — {'Active' if prod['is_active'] else 'Inactive'}",
        reply_markup=admin_prod_actions_kb(prod["id"], bool(prod["is_active"]), prod["type"]),
    )
    await callback.answer("Toggled.")


@router.callback_query(AdminCallback.filter(F.action == "prod_delete_confirm"))
async def admin_prod_delete_confirm(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    if not callback.message:
        await callback.answer()
        return
    prod = await db.get_product(callback_data.id)
    if not prod:
        await callback.answer("Not found.", show_alert=True)
        return
    await callback.message.edit_text(
        f"Delete product '{prod['name']}'?",
        reply_markup=confirm_delete_kb("prod_delete", callback_data.id),
    )
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "prod_delete_yes"))
async def admin_prod_delete(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    if not callback.message:
        await callback.answer()
        return
    prod = await db.get_product(callback_data.id)
    if not prod:
        await callback.answer("Not found.", show_alert=True)
        return
    cat_id = prod["category_id"]
    await db.delete_product(callback_data.id)
    products = await db.get_products_by_category(cat_id, active_only=False)
    await callback.message.edit_text("Product deleted.", reply_markup=admin_products_kb(products, cat_id))
    await callback.answer()


# --- Stock ---

@router.callback_query(AdminCallback.filter(F.action == "stock_cat"))
async def admin_stock_cat(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    from bot.keyboards.inline import admin_stock_cats_kb
    cats = await db.get_all_categories()
    await callback.message.edit_text("Select category:", reply_markup=admin_stock_cats_kb(cats))
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "stock_cat_prods"))
async def admin_stock_cat_prods(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    if not callback.message:
        await callback.answer()
        return
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
    if not callback.message:
        await callback.answer()
        return
    prod = await db.get_product(callback_data.id)
    if not prod:
        await callback.answer("Product not found.", show_alert=True)
        return
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
    items = [line.strip() for line in (message.text or "").splitlines() if line.strip()]
    if not items:
        await message.answer("No items found. Send at least one item per line:")
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
    if not callback.message:
        await callback.answer()
        return
    prod = await db.get_product(callback_data.id)
    if not prod:
        await callback.answer("Product not found.", show_alert=True)
        return
    counts = await db.get_stock_count(callback_data.id)
    await callback.message.edit_text(
        f"Stock for '{prod['name']}':\nAvailable: {counts['available']}\nTotal loaded: {counts['total']}",
        reply_markup=admin_prod_actions_kb(prod["id"], bool(prod["is_active"]), prod["type"]),
    )
    await callback.answer()


# --- Orders ---

@router.callback_query(AdminCallback.filter(F.action == "orders_filter"))
async def admin_orders_filter(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    from bot.keyboards.inline import admin_orders_filter_kb
    await callback.message.edit_text("Filter orders:", reply_markup=admin_orders_filter_kb())
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action.in_({"orders_pending", "orders_paid", "orders_delivered", "orders_all"})))
async def admin_orders_list(callback: CallbackQuery, callback_data: AdminCallback) -> None:
    if not callback.message:
        await callback.answer()
        return
    from bot.keyboards.inline import admin_orders_filter_kb
    status = callback_data.action.replace("orders_", "")
    orders = await db.get_orders_by_status(status)
    if not orders:
        await callback.answer("No orders found.", show_alert=True)
        return
    lines = []
    for o in orders:
        lines.append(
            f"#{o['id']} {o['status'].upper()} @{o.get('username') or '?'} "
            f"{o['product_name']} ${o['amount_usd']:.2f}"
        )
    await callback.message.edit_text(
        f"Orders ({status}):\n\n" + "\n".join(lines),
        reply_markup=admin_orders_filter_kb(),
    )
    await callback.answer()


# --- Stats ---

@router.callback_query(AdminCallback.filter(F.action == "stats"))
async def admin_stats(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
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
    if not callback.message:
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_broadcast_text)
    await callback.message.edit_text("Enter message to broadcast to all users:")
    await callback.answer()


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


@router.callback_query(AdminCallback.filter(F.action == "broadcast_confirm"))
async def admin_broadcast_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()
    users = await db.get_all_users()
    sent = 0
    failed = 0
    import asyncio
    for user in users:
        try:
            await callback.bot.send_message(user["id"], text)
            sent += 1
        except Exception:
            failed += 1
        if sent % 25 == 0:
            await asyncio.sleep(1)
    await callback.message.edit_text(
        f"Broadcast complete.\nSent: {sent}\nFailed: {failed}",
        reply_markup=admin_menu_kb(),
    )
    await callback.answer()
