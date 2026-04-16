"""Lightweight aiohttp web server to receive MaxelPay webhook notifications.

MaxelPay POSTs to /webhook/maxelpay when a payment event occurs.
Payload format: {"event": "payment.completed", "data": {"orderId": "...", ...}}
Signature is verified via X-MaxelPay-Signature header (HMAC-SHA256).
"""

import asyncio
import json
import logging

from aiohttp import web
from aiogram import Bot

from bot import db
from bot.services.delivery import deliver_and_notify

logger = logging.getLogger(__name__)

_runner: web.AppRunner | None = None
_maxelpay_client = None  # set at startup
_bot: Bot | None = None
_admin_ids: list[int] = []
_bonus_usd: float = 10.0

# Webhook events
_PAID_EVENTS = {"payment.completed", "payment.overpaid"}
_EXPIRED_EVENTS = {"payment.expired"}


async def _handle_maxelpay_webhook(request: web.Request) -> web.Response:
    """Handle incoming MaxelPay webhook POST."""
    body = await request.read()
    logger.info("MaxelPay webhook received: %s", body[:500])

    # Verify signature if secret key is configured
    signature = request.headers.get("X-MaxelPay-Signature", "")
    if _maxelpay_client and _maxelpay_client._secret_key:
        if not signature:
            logger.warning("Webhook missing X-MaxelPay-Signature header")
        elif not _maxelpay_client.verify_webhook_signature(body, signature):
            logger.warning("Webhook signature verification failed")
            return web.json_response({"status": "error", "message": "invalid signature"}, status=401)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Could not parse MaxelPay webhook JSON")
        return web.json_response({"status": "error", "message": "invalid json"}, status=400)

    logger.info("MaxelPay webhook parsed: %s", payload)

    event = payload.get("event", "")
    data = payload.get("data", payload)  # fallback to root if no "data" key

    order_id_raw = (
        data.get("orderId") or data.get("order_id") or data.get("orderID") or ""
    )

    if not order_id_raw:
        logger.warning("Webhook missing orderId: %s", payload)
        return web.json_response({"status": "ok"})

    order_id_str = str(order_id_raw)

    if order_id_str.startswith("order_"):
        await _process_order_webhook(order_id_str, event, data)
    elif order_id_str.startswith("deposit_"):
        await _process_deposit_webhook(order_id_str, event, data)
    else:
        logger.warning("Unknown orderId prefix: %s", order_id_str)

    return web.json_response({"status": "ok"})


async def _process_order_webhook(order_id_str: str, event: str, data: dict) -> None:
    """Process a webhook for a purchase order."""
    try:
        db_order_id = int(order_id_str.replace("order_", ""))
    except ValueError:
        logger.error("Invalid order ID in webhook: %s", order_id_str)
        return

    order = await db.get_order(db_order_id)
    if not order:
        logger.warning("Order %s not found for webhook", db_order_id)
        return

    if order["status"] != "pending":
        logger.info("Order %s already %s, ignoring webhook", db_order_id, order["status"])
        return

    if event in _PAID_EVENTS and _bot:
        _cancel_expiry(order_id_str)
        await deliver_and_notify(db_order_id, order, _bot, _admin_ids, _bonus_usd)
    elif event in _EXPIRED_EVENTS and _bot:
        _cancel_expiry(order_id_str)
        await db.update_order_status(db_order_id, "expired")
        if order.get("balance_used", 0.0) > 0:
            await db.update_user_balance(order["user_id"], order["balance_used"])
        try:
            await _bot.send_message(
                order["user_id"],
                "Your order has expired (payment not completed).\n"
                "Start a new order if you still want to purchase.",
            )
        except Exception:
            logger.warning("Failed to notify user about order %s expiry", db_order_id)
    else:
        logger.info("Order %s webhook event '%s' — no action taken", db_order_id, event)


async def _process_deposit_webhook(order_id_str: str, event: str, data: dict) -> None:
    """Process a webhook for a balance deposit."""
    try:
        deposit_id = int(order_id_str.replace("deposit_", ""))
    except ValueError:
        logger.error("Invalid deposit ID in webhook: %s", order_id_str)
        return

    deposit = await db.get_deposit(deposit_id)
    if not deposit:
        logger.warning("Deposit %s not found for webhook", deposit_id)
        return

    if deposit["status"] != "pending":
        logger.info("Deposit %s already %s, ignoring webhook", deposit_id, deposit["status"])
        return

    if event in _PAID_EVENTS and _bot:
        _cancel_expiry(order_id_str)
        await db.update_deposit_status(deposit_id, "completed")
        await db.update_user_balance(deposit["user_id"], deposit["amount_usd"])
        if _admin_ids:
            try:
                await _bot.send_message(
                    _admin_ids[0],
                    f"Deposit #{deposit_id} confirmed\n"
                    f"User: {deposit['user_id']}\n"
                    f"${deposit['amount_usd']:.2f}",
                )
            except Exception:
                pass
        try:
            await _bot.send_message(
                deposit["user_id"],
                f"Deposit confirmed!\n\n"
                f"${deposit['amount_usd']:.2f} has been added to your balance.",
            )
        except Exception:
            logger.warning("Failed to notify user %s about deposit %s", deposit["user_id"], deposit_id)
    elif event in _EXPIRED_EVENTS and _bot:
        _cancel_expiry(order_id_str)
        await db.update_deposit_status(deposit_id, "expired")
        try:
            await _bot.send_message(
                deposit["user_id"],
                "Deposit expired (payment not completed).\n"
                "Start a new deposit if you wish to top up your balance.",
            )
        except Exception:
            logger.warning("Failed to notify user %s about deposit expiry", deposit["user_id"])
    else:
        logger.info("Deposit %s webhook event '%s' — no action taken", deposit_id, event)


# --- Expiry timers ---

_expiry_tasks: dict[str, asyncio.Task] = {}


async def _expiry_timer(key: str, timeout_minutes: float) -> None:
    """Wait for timeout and expire the order/deposit if still pending."""
    await asyncio.sleep(timeout_minutes * 60)

    if key.startswith("order_"):
        try:
            db_id = int(key.replace("order_", ""))
        except ValueError:
            return
        order = await db.get_order(db_id)
        if order and order["status"] == "pending":
            await db.update_order_status(db_id, "expired")
            if order.get("balance_used", 0.0) > 0:
                await db.update_user_balance(order["user_id"], order["balance_used"])
            if _bot:
                try:
                    await _bot.send_message(
                        order["user_id"],
                        "Your order has expired (no payment received in time).\n"
                        "Start a new order if you still want to purchase.",
                    )
                except Exception:
                    pass
    elif key.startswith("deposit_"):
        try:
            db_id = int(key.replace("deposit_", ""))
        except ValueError:
            return
        deposit = await db.get_deposit(db_id)
        if deposit and deposit["status"] == "pending":
            await db.update_deposit_status(db_id, "expired")
            if _bot:
                try:
                    await _bot.send_message(
                        deposit["user_id"],
                        "Deposit expired (no payment received in time).\n"
                        "Start a new deposit if you wish to top up your balance.",
                    )
                except Exception:
                    pass

    _expiry_tasks.pop(key, None)


def start_expiry_timer(key: str, timeout_minutes: float) -> None:
    """Start a timer that expires the order/deposit after timeout_minutes."""
    existing = _expiry_tasks.get(key)
    if existing and not existing.done():
        existing.cancel()
    _expiry_tasks[key] = asyncio.create_task(_expiry_timer(key, timeout_minutes))


def _cancel_expiry(key: str) -> None:
    task = _expiry_tasks.pop(key, None)
    if task and not task.done():
        task.cancel()


def cancel_all_expiry_timers() -> None:
    for task in _expiry_tasks.values():
        task.cancel()
    _expiry_tasks.clear()


async def restore_expiry_timers(timeout_minutes: int) -> None:
    """Restore expiry timers for pending orders/deposits after bot restart."""
    import time

    now_ms = int(time.time() * 1000)

    for order in await db.get_pending_orders():
        deadline_ms = order["created_at_ms"] + timeout_minutes * 60 * 1000
        if now_ms < deadline_ms:
            remaining = (deadline_ms - now_ms) / (60 * 1000)
            start_expiry_timer(f"order_{order['id']}", remaining)
        else:
            await db.update_order_status(order["id"], "expired")
            if order.get("balance_used", 0.0) > 0:
                await db.update_user_balance(order["user_id"], order["balance_used"])

    for deposit in await db.get_pending_deposits():
        deadline_ms = deposit["created_at_ms"] + timeout_minutes * 60 * 1000
        if now_ms < deadline_ms:
            remaining = (deadline_ms - now_ms) / (60 * 1000)
            start_expiry_timer(f"deposit_{deposit['id']}", remaining)
        else:
            await db.update_deposit_status(deposit["id"], "expired")


# --- Server lifecycle ---

async def start_webhook_server(
    bot: Bot,
    maxelpay_client,
    port: int,
    admin_ids: list[int],
    bonus_usd: float = 10.0,
) -> None:
    """Start the aiohttp webhook server."""
    global _runner, _maxelpay_client, _bot, _admin_ids, _bonus_usd

    _maxelpay_client = maxelpay_client
    _bot = bot
    _admin_ids = list(admin_ids)
    _bonus_usd = bonus_usd

    app = web.Application()
    app.router.add_post("/webhook/maxelpay", _handle_maxelpay_webhook)
    app.router.add_get("/health", lambda r: web.json_response({"status": "ok"}))

    _runner = web.AppRunner(app)
    await _runner.setup()
    site = web.TCPSite(_runner, "0.0.0.0", port)
    await site.start()
    logger.info("Webhook server started on port %d", port)


async def stop_webhook_server() -> None:
    """Stop the webhook server."""
    global _runner
    if _runner:
        await _runner.cleanup()
        _runner = None
    logger.info("Webhook server stopped")
