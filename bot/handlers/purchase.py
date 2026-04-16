import time
from typing import Any, Callable, Coroutine

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot import db
from bot.keyboards.inline import (
    PurchaseCallback, payment_pending_kb, back_to_main_kb,
)
from bot.services.maxelpay import MaxelPayClient
from bot.services.password import generate_password
from bot.services.delivery import deliver_and_notify
from bot.services.webhook_server import start_expiry_timer
from bot.services.notifications import notify_admin
from bot.config import Config

router = Router()

ReplyFn = Callable[..., Coroutine[Any, Any, Any]]


class PurchaseStates(StatesGroup):
    waiting_email = State()


@router.callback_query(PurchaseCallback.filter(F.action == "start"))
async def buy_start(
    callback: CallbackQuery,
    callback_data: PurchaseCallback,
    state: FSMContext,
    maxelpay: MaxelPayClient,
    config: Config,
) -> None:
    if not callback.message:
        await callback.answer("Session expired.", show_alert=True)
        return
    if not callback.from_user:
        await callback.answer("Cannot identify user.", show_alert=True)
        return
    pending_count = await db.count_pending_orders(callback.from_user.id)
    if pending_count >= 3:
        await callback.answer("You have 3 pending orders. Complete or cancel one first.", show_alert=True)
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
        await callback.answer()

        async def _reply(text: str, **kwargs: Any) -> None:
            if callback.message:
                await callback.message.edit_text(text, **kwargs)

        await _check_balance_and_process(
            callback.from_user.id, product, config, callback.bot, maxelpay, _reply,
        )
    else:
        await state.set_state(PurchaseStates.waiting_email)
        await state.update_data(product_id=product["id"])
        await callback.message.edit_text(
            f"🛒 Buying: {product['name']} — ${product['price_usd']:.2f}\n\n📧 Please enter your email address:"
        )
        await callback.answer()


@router.message(PurchaseStates.waiting_email)
async def receive_email(
    message: Message,
    state: FSMContext,
    maxelpay: MaxelPayClient,
    config: Config,
) -> None:
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
    await state.clear()
    await _check_balance_and_process(
        message.from_user.id, product, config, message.bot, maxelpay, message.answer, email=email,
    )


async def _check_balance_and_process(
    user_id: int,
    product: dict,
    config: Config,
    bot: Bot,
    maxelpay: MaxelPayClient,
    reply: ReplyFn,
    email: str | None = None,
) -> None:
    """Check if balance covers the order. If fully covered, process immediately.
    Otherwise, create a MaxelPay checkout for the remaining amount."""
    user = await db.get_user(user_id)
    balance = user["balance"] if user else 0.0
    price = product["price_usd"]
    use_balance = min(balance, price)
    remaining = price - use_balance

    if remaining <= 0:
        if use_balance > 0:
            if not await db.deduct_balance_if_sufficient(user_id, use_balance):
                await reply("⚠️ Balance changed. Please try again.", reply_markup=back_to_main_kb())
                return
        generated_password = generate_password() if product["type"] == "account" else None
        order_id = await db.create_order(
            user_id=user_id,
            product_id=product["id"],
            email=email,
            generated_password=generated_password,
            amount_usd=price,
            balance_used=use_balance,
            created_at_ms=int(time.time() * 1000),
        )
        await db.update_order_status(order_id, "paid")
        order = await db.get_order(order_id)
        await deliver_and_notify(order_id, order, bot, config.notification_targets, bonus_usd=config.referral_bonus_usd)
        await reply("✅ Payment complete! Check your messages above.")
        return

    # Deduct balance first if applicable
    if use_balance > 0:
        if not await db.deduct_balance_if_sufficient(user_id, use_balance):
            use_balance = 0.0
            remaining = price

    generated_password = generate_password() if product["type"] == "account" else None
    order_id = await db.create_order(
        user_id=user_id,
        product_id=product["id"],
        email=email,
        generated_password=generated_password,
        amount_usd=price,
        balance_used=use_balance,
        created_at_ms=int(time.time() * 1000),
    )

    # Create MaxelPay checkout
    maxelpay_order_id = f"order_{order_id}"
    try:
        checkout = await maxelpay.create_checkout(
            order_id=maxelpay_order_id,
            amount=remaining,
            user_email=email or "",
        )
    except Exception:
        # Rollback: cancel order and refund balance
        await db.update_order_status(order_id, "cancelled")
        if use_balance > 0:
            await db.update_user_balance(user_id, use_balance)
        await reply("Error creating payment. Please try again.", reply_markup=back_to_main_kb())
        return

    # Start expiry timer
    start_expiry_timer(maxelpay_order_id, config.order_timeout_minutes)

    text = (
        f"🧾 Order #{order_id}\n\n"
        f"📦 Product: {product['name']}\n"
        f"💲 Price: ${price:.2f}"
    )
    if use_balance > 0:
        text += f"\n💰 Balance used: -${use_balance:.2f}"
    text += (
        f"\n💳 To pay: ${remaining:.2f}\n\n"
        f"Tap 💳 Pay Now to complete payment.\n"
        f"⏱ You have {config.order_timeout_minutes} minutes."
    )

    await notify_admin(bot, config.notification_targets,
        f"🧾 New order #{order_id}\n👤 User: {user_id}\n📦 {product['name']}\n💲 ${price:.2f} (pay: ${remaining:.2f})")

    await reply(text, reply_markup=payment_pending_kb(order_id, checkout["payment_url"]))


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
        "pending": "Payment not confirmed yet. Please complete payment and wait for confirmation.",
        "delivered": "Your order has been delivered!",
        "expired": "This order has expired.",
        "cancelled": "This order was cancelled.",
    }
    await callback.answer(status_msg.get(order["status"], order["status"]), show_alert=True)


@router.callback_query(PurchaseCallback.filter(F.action == "cancel"))
async def cancel_order(callback: CallbackQuery, callback_data: PurchaseCallback, config: Config) -> None:
    if not callback.message:
        await callback.answer("Session expired.", show_alert=True)
        return
    if not callback.from_user:
        await callback.answer("Cannot identify user.", show_alert=True)
        return
    order = await db.get_order(callback_data.id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Order not found.", show_alert=True)
        return
    if order["status"] != "pending":
        await callback.answer("Cannot cancel this order.", show_alert=True)
        return
    from bot.services.webhook_server import _cancel_expiry
    _cancel_expiry(f"order_{callback_data.id}")
    await db.update_order_status(callback_data.id, "cancelled")
    if order.get("balance_used", 0.0) > 0:
        await db.update_user_balance(order["user_id"], order["balance_used"])
    await notify_admin(callback.bot, config.notification_targets,
        f"❌ Order #{callback_data.id} cancelled by user {callback.from_user.id}")
    await callback.message.edit_text("❌ Order cancelled.", reply_markup=back_to_main_kb())
    await callback.answer()
