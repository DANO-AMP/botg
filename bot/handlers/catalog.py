from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot import db
from bot.keyboards.inline import (
    NavCallback, categories_kb, products_kb, product_detail_kb
)

router = Router()


@router.callback_query(NavCallback.filter(F.to == "categories"))
async def show_categories(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Session expired, please start again.", show_alert=True)
        return
    categories = await db.get_active_categories()
    if not categories:
        await callback.answer("No categories available yet.", show_alert=True)
        return
    await callback.message.edit_text("Choose a category:", reply_markup=categories_kb(categories))
    await callback.answer()


@router.callback_query(NavCallback.filter(F.to == "products"))
async def show_products(callback: CallbackQuery, callback_data: NavCallback) -> None:
    if not callback.message:
        await callback.answer("Session expired, please start again.", show_alert=True)
        return
    cat_id = callback_data.id
    cat = await db.get_category(cat_id)
    if not cat:
        await callback.answer("Category not found.", show_alert=True)
        return
    products = await db.get_products_by_category(cat_id)
    if not products:
        await callback.answer("No products in this category.", show_alert=True)
        return
    for p in products:
        if p["type"] == "string":
            counts = await db.get_stock_count(p["id"])
            p["stock_count"] = counts["available"]
    await callback.message.edit_text(
        f"{cat['name']}\n\nChoose a product:",
        reply_markup=products_kb(products, cat_id),
    )
    await callback.answer()


@router.callback_query(NavCallback.filter(F.to == "product_detail"))
async def show_product_detail(callback: CallbackQuery, callback_data: NavCallback) -> None:
    if not callback.message:
        await callback.answer("Session expired, please start again.", show_alert=True)
        return
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
