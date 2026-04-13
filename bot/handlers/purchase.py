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
    if not callback.message:
        await callback.answer("Session expired.", show_alert=True)
        return
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
    if not message.from_user:
        return
    email = message.text.strip() if message.text else ""
    if "@" not in email or "." not in email:
        await message.answer("Invalid email. Please enter a valid email address:")
        return
    data = await state.get_data()
    product_id = data["product_id"]
    product = await db.get_product(product_id)
    if not product or not product["is_active"]:
        await state.clear()
        await message.answer("Product no longer available.", reply_markup=back_to_main_kb())
        return
    await state.update_data(email=email)
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
    if not callback.message:
        await callback.answer("Session expired.", show_alert=True)
        return
    if not callback.from_user:
        await callback.answer("Cannot identify user.", show_alert=True)
        return
    product = await db.get_product(callback_data.product_id)
    if not product:
        await callback.answer("Product not found.", show_alert=True)
        return

    user = await db.get_user(callback.from_user.id)
    balance = user["balance"] if user else 0.0
    price = product["price_usd"]
    crypto = callback_data.crypto

    use_balance = min(balance, price)
    crypto_needed = price - use_balance

    try:
        if crypto_needed > 0:
            amount_crypto = await bitunix.get_crypto_amount(crypto_needed, crypto)
            deposit_address = await bitunix.get_deposit_address(crypto)
        else:
            amount_crypto = 0.0
            deposit_address = ""
    except Exception:
        await callback.answer("Error contacting payment API. Try again.", show_alert=True)
        return

    fsm_data = await state.get_data()
    email = fsm_data.get("email")
    await state.clear()
    generated_password = generate_password() if product["type"] == "account" else None

    if use_balance > 0:
        await db.update_user_balance(callback.from_user.id, -use_balance)

    order_id = await db.create_order(
        user_id=callback.from_user.id,
        product_id=product["id"],
        email=email,
        generated_password=generated_password,
        amount_usd=price,
        balance_used=use_balance,
        amount_crypto=amount_crypto,
        crypto_currency=crypto,
        deposit_address=deposit_address,
        created_at_ms=int(time.time() * 1000),
    )

    if crypto_needed <= 0:
        from bot.services.payment_checker import _deliver_and_notify
        await db.update_order_status(order_id, "paid")
        order = await db.get_order(order_id)
        await _deliver_and_notify(order_id, order, callback.bot, config.admin_telegram_id, bonus_usd=config.referral_bonus_usd)
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
        bonus_usd=config.referral_bonus_usd,
    )

    await callback.message.edit_text(
        text, reply_markup=payment_pending_kb(order_id), parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(PurchaseCallback.filter(F.action == "check"))
async def check_payment(callback: CallbackQuery, callback_data: PurchaseCallback) -> None:
    if not callback.from_user:
        await callback.answer("Cannot identify user.", show_alert=True)
        return
    order = await db.get_order(callback_data.id)
    if not order:
        await callback.answer("Order not found.", show_alert=True)
        return
    if order["user_id"] != callback.from_user.id:
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
    if not callback.message:
        await callback.answer("Session expired.", show_alert=True)
        return
    order = await db.get_order(callback_data.id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Order not found.", show_alert=True)
        return
    if order["status"] != "pending":
        await callback.answer("Cannot cancel this order.", show_alert=True)
        return
    stop_monitor(callback_data.id)
    await db.update_order_status(callback_data.id, "cancelled")
    if order.get("balance_used", 0.0) > 0:
        await db.update_user_balance(order["user_id"], order["balance_used"])
    await callback.message.edit_text("Order cancelled.", reply_markup=back_to_main_kb())
    await callback.answer()
