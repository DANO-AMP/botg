import asyncio
import logging
import time
from aiogram import Bot
from bot import db
from bot.services.cryptopay import CryptoPayClient
from bot.services.delivery import deliver_and_notify

logger = logging.getLogger(__name__)
_tasks: dict[int, asyncio.Task] = {}


async def start_monitor(
    order_id: int,
    bot: Bot,
    cryptopay: CryptoPayClient,
    timeout_minutes: float,
    check_interval: int,
    admin_id: int,
    bonus_usd: float = 10.0,
) -> None:
    existing = _tasks.get(order_id)
    if existing and not existing.done():
        existing.cancel()
    task = asyncio.create_task(
        _monitor_loop(order_id, bot, cryptopay, timeout_minutes, check_interval, admin_id, bonus_usd)
    )
    _tasks[order_id] = task


def stop_monitor(order_id: int) -> None:
    task = _tasks.pop(order_id, None)
    if task:
        task.cancel()


def cancel_all_monitors() -> None:
    for task in _tasks.values():
        task.cancel()
    _tasks.clear()


async def restore_monitors(
    bot: Bot,
    cryptopay: CryptoPayClient,
    timeout_minutes: int,
    check_interval: int,
    admin_id: int,
    bonus_usd: float = 10.0,
) -> None:
    pending = await db.get_pending_orders()
    now_ms = int(time.time() * 1000)
    for order in pending:
        if not order.get("invoice_id"):
            continue
        deadline_ms = order["created_at_ms"] + timeout_minutes * 60 * 1000
        if now_ms < deadline_ms:
            remaining_minutes = (deadline_ms - now_ms) / (60 * 1000)
            await start_monitor(order["id"], bot, cryptopay, remaining_minutes, check_interval, admin_id, bonus_usd)
        else:
            await db.update_order_status(order["id"], "expired")


async def _monitor_loop(
    order_id: int,
    bot: Bot,
    cryptopay: CryptoPayClient,
    timeout_minutes: float,
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
        invoice_id = order.get("invoice_id")
        if not invoice_id:
            _tasks.pop(order_id, None)
            return
        try:
            status = await cryptopay.get_invoice_status(int(invoice_id))
        except Exception as e:
            logger.warning("CryptoPay check failed for order %s: %s", order_id, e)
            continue
        if status == "paid":
            await deliver_and_notify(order_id, order, bot, admin_id, bonus_usd)
            _tasks.pop(order_id, None)
            return
        if status == "expired":
            await db.update_order_status(order_id, "expired")
            try:
                await bot.send_message(
                    order["user_id"],
                    "⌛ Your order has expired (payment invoice expired).\n"
                    "Start a new order if you still want to purchase.",
                )
            except Exception:
                logger.warning("Failed to notify user about order %s expiry", order_id)
            _tasks.pop(order_id, None)
            return

    order = await db.get_order(order_id)
    if order and order["status"] == "pending":
        await db.update_order_status(order_id, "expired")
        try:
            await bot.send_message(
                order["user_id"],
                "⌛ Your order has expired (no payment received in time).\n"
                "Start a new order if you still want to purchase.",
            )
        except Exception:
            logger.warning("Failed to notify user about order %s expiry", order_id)
    _tasks.pop(order_id, None)
