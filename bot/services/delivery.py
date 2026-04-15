import logging
from aiogram import Bot
from bot import db

logger = logging.getLogger(__name__)


async def deliver_and_notify(
    order_id: int, order: dict, bot: Bot, admin_id: int, bonus_usd: float = 10.0
) -> None:
    product = await db.get_product(order["product_id"])
    if product is None:
        logger.error("Product not found for order %s", order_id)
        return

    if product["type"] == "account":
        delivered_value = order["generated_password"]
        user_text = (
            f"✅ Payment confirmed!\n\n"
            f"📧 Email: {order['email']}\n"
            f"🔑 Password: {delivered_value}\n\n"
            f"⚠️ Save these credentials now!"
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
        user_text += "\n\n🎁 You received a $10 referral bonus!"

    try:
        await bot.send_message(order["user_id"], user_text)
    except Exception:
        logger.warning("Failed to notify user %s about delivery", order["user_id"])

    try:
        await bot.send_message(
            admin_id,
            f"Order #{order_id} DELIVERED\n"
            f"User: {order['user_id']}\n"
            f"Product: {product['name']}\n"
            f"Amount: ${order['amount_usd']:.2f}"
            f"{admin_extra}",
        )
    except Exception:
        logger.warning("Failed to notify admin about order %s delivery", order_id)
