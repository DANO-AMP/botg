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
    bonus_usd: float = 10.0,
) -> None:
    existing = _tasks.get(order_id)
    if existing and not existing.done():
        existing.cancel()
    task = asyncio.create_task(
        _monitor_loop(order_id, bot, client, timeout_minutes, check_interval, admin_id, bonus_usd)
    )
    _tasks[order_id] = task


def stop_monitor(order_id: int) -> None:
    task = _tasks.pop(order_id, None)
    if task:
        task.cancel()


async def restore_monitors(
    bot: Bot,
    client: BitunixClient,
    timeout_minutes: int,
    check_interval: int,
    admin_id: int,
    bonus_usd: float = 10.0,
) -> None:
    pending = await db.get_pending_orders()
    now_ms = int(time.time() * 1000)
    for order in pending:
        deadline_ms = order["created_at_ms"] + timeout_minutes * 60 * 1000
        if now_ms < deadline_ms:
            await start_monitor(order["id"], bot, client, timeout_minutes, check_interval, admin_id, bonus_usd)
        else:
            await db.update_order_status(order["id"], "expired")


async def _monitor_loop(
    order_id: int,
    bot: Bot,
    client: BitunixClient,
    timeout_minutes: int,
    check_interval: int,
    admin_id: int,
    bonus_usd: float = 10.0,
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
            await _deliver_and_notify(order_id, order, bot, admin_id, bonus_usd)
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


async def _deliver_and_notify(order_id: int, order: dict, bot: Bot, admin_id: int, bonus_usd: float = 10.0) -> None:
    product = await db.get_product(order["product_id"])
    if product is None:
        logger.error("Product not found for order %s", order_id)
        return

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
        stock_item = await db.claim_stock_item(order["product_id"], order["user_id"])
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
        order["user_id"], bonus_usd=bonus_usd
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
            f"User: {order['user_id']}\n"
            f"Product: {product['name']}\n"
            f"Amount: ${order['amount_usd']:.2f} "
            f"({order['amount_crypto']:.8f} {order['crypto_currency']})"
            f"{admin_extra}",
        )
    except Exception:
        pass
