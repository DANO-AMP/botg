import logging
from aiogram import Bot
from bot import db

logger = logging.getLogger(__name__)


async def deliver_and_notify(
    order_id: int, order: dict, bot: Bot, admin_ids: int | list[int], bonus_usd: float = 10.0
) -> None:
    if isinstance(admin_ids, int):
        admin_ids = [admin_ids]
    product = await db.get_product(order["product_id"])
    if product is None:
        logger.error("Product not found for order %s", order_id)
        return

    if product["type"] == "account":
        delivered_value = order["generated_password"]
        email_line = f"📧 Email: {order['email']}\n" if order.get("email") else ""
        user_text = (
            f"✅ Payment confirmed!\n\n"
            f"{email_line}"
            f"🔑 Password: {delivered_value}\n\n"
            f"⚠️ Save these credentials now!"
        )
        admin_extra = f"\nEmail: {order.get('email') or '—'}\nPassword: {delivered_value}"
    elif product["type"] == "unlimited":
        delivered_value = product.get("fixed_value") or ""
        user_text = (
            f"✅ Payment confirmed!\n\n"
            f"📦 Product: {product['name']}\n"
            f"🔑 Your item:\n{delivered_value}\n\n"
            f"⚠️ Keep this safe!"
        )
        admin_extra = f"\nDelivered: {delivered_value}"
    else:
        stock_item = await db.claim_stock_item(order["product_id"], order["user_id"])
        if not stock_item:
            await db.update_user_balance(order["user_id"], order["amount_usd"])
            await db.update_order_status(order_id, "cancelled")
            try:
                await bot.send_message(
                    order["user_id"],
                    f"⚠️ Payment received but product is out of stock.\n"
                    f"💰 ${order['amount_usd']:.2f} credited to your balance.",
                )
            except Exception:
                logger.warning("Failed to notify user %s about out-of-stock refund", order["user_id"])
            return
        delivered_value = stock_item["value"]
        user_text = (
            f"✅ Payment confirmed!\n\n"
            f"📦 Product: {product['name']}\n"
            f"🔑 Your item:\n{delivered_value}\n\n"
            f"⚠️ Keep this safe!"
        )
        admin_extra = f"\nDelivered: {delivered_value}"

    await db.update_order_status(order_id, "delivered", {"delivered_value": delivered_value})

    bonus_applied = await db.apply_referral_bonus_if_first_purchase(
        order["user_id"], bonus_usd=bonus_usd
    )
    if bonus_applied:
        user_text += f"\n\n🎁 You received a ${bonus_usd:.2f} referral bonus!"

    try:
        await bot.send_message(order["user_id"], user_text)
    except Exception:
        logger.warning("Failed to notify user %s about delivery", order["user_id"])

    msg = (
        f"Order #{order_id} DELIVERED\n"
        f"User: {order['user_id']}\n"
        f"Product: {product['name']}\n"
        f"Amount: ${order['amount_usd']:.2f}"
        f"{admin_extra}"
    )
    for aid in admin_ids:
        try:
            await bot.send_message(aid, msg)
        except Exception:
            logger.warning("Failed to notify admin %s about order %s delivery", aid, order_id)
