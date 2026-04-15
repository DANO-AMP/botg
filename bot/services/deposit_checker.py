import asyncio
import logging
import time
from aiogram import Bot
from bot import db
from bot.services.cryptopay import CryptoPayClient

logger = logging.getLogger(__name__)
_tasks: dict[int, asyncio.Task] = {}


async def start_deposit_monitor(
    deposit_id: int,
    bot: Bot,
    cryptopay: CryptoPayClient,
    timeout_minutes: float,
    check_interval: int,
    admin_id: int = 0,
) -> None:
    existing = _tasks.get(deposit_id)
    if existing and not existing.done():
        existing.cancel()
    task = asyncio.create_task(
        _deposit_loop(deposit_id, bot, cryptopay, timeout_minutes, check_interval, admin_id)
    )
    _tasks[deposit_id] = task


def stop_deposit_monitor(deposit_id: int) -> None:
    task = _tasks.pop(deposit_id, None)
    if task:
        task.cancel()


def cancel_all_deposit_monitors() -> None:
    for task in _tasks.values():
        task.cancel()
    _tasks.clear()


async def restore_deposit_monitors(
    bot: Bot,
    cryptopay: CryptoPayClient,
    timeout_minutes: int,
    check_interval: int,
    admin_id: int = 0,
) -> None:
    pending = await db.get_pending_deposits()
    now_ms = int(time.time() * 1000)
    for deposit in pending:
        if not deposit.get("invoice_id"):
            continue
        deadline_ms = deposit["created_at_ms"] + timeout_minutes * 60 * 1000
        if now_ms < deadline_ms:
            remaining_minutes = (deadline_ms - now_ms) / (60 * 1000)
            await start_deposit_monitor(deposit["id"], bot, cryptopay, remaining_minutes, check_interval, admin_id)
        else:
            await db.update_deposit_status(deposit["id"], "expired")


async def _deposit_loop(
    deposit_id: int,
    bot: Bot,
    cryptopay: CryptoPayClient,
    timeout_minutes: float,
    check_interval: int,
    admin_id: int = 0,
) -> None:
    deadline = time.time() + timeout_minutes * 60
    while time.time() < deadline:
        await asyncio.sleep(check_interval)
        deposit = await db.get_deposit(deposit_id)
        if not deposit or deposit["status"] != "pending":
            _tasks.pop(deposit_id, None)
            return
        invoice_id = deposit.get("invoice_id")
        if not invoice_id:
            _tasks.pop(deposit_id, None)
            return
        try:
            status = await cryptopay.get_invoice_status(int(invoice_id))
        except Exception as e:
            logger.warning("CryptoPay check failed for deposit %s: %s", deposit_id, e)
            continue
        if status == "paid":
            await db.update_deposit_status(deposit_id, "completed")
            await db.update_user_balance(deposit["user_id"], deposit["amount_usd"])
            if admin_id:
                try:
                    await bot.send_message(admin_id,
                        f"✅ Deposit #{deposit_id} confirmed\n"
                        f"👤 User: {deposit['user_id']}\n"
                        f"💰 ${deposit['amount_usd']:.2f}")
                except Exception:
                    pass
            try:
                await bot.send_message(
                    deposit["user_id"],
                    f"✅ Deposit confirmed!\n\n💰 ${deposit['amount_usd']:.2f} has been added to your balance.",
                )
            except Exception:
                logger.warning("Failed to notify user %s about deposit %s", deposit["user_id"], deposit_id)
            _tasks.pop(deposit_id, None)
            return
        if status == "expired":
            await db.update_deposit_status(deposit_id, "expired")
            try:
                await bot.send_message(
                    deposit["user_id"],
                    "⌛ Deposit expired (payment invoice expired).\n"
                    "Start a new deposit if you wish to top up your balance.",
                )
            except Exception:
                logger.warning("Failed to notify user %s about deposit expiry", deposit["user_id"])
            _tasks.pop(deposit_id, None)
            return

    deposit = await db.get_deposit(deposit_id)
    if deposit and deposit["status"] == "pending":
        await db.update_deposit_status(deposit_id, "expired")
        try:
            await bot.send_message(
                deposit["user_id"],
                "⌛ Deposit expired (no payment received in time).\n"
                "Start a new deposit if you wish to top up your balance.",
            )
        except Exception:
            logger.warning("Failed to notify user %s about deposit expiry", deposit["user_id"])
    _tasks.pop(deposit_id, None)
