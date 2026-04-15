import logging
from aiogram import Bot

logger = logging.getLogger(__name__)


async def notify_admin(bot: Bot, admin_id: int, text: str) -> None:
    """Send a notification to the admin. Silently fails if delivery fails."""
    try:
        await bot.send_message(admin_id, text)
    except Exception:
        logger.warning("Failed to send admin notification: %s", text[:80])
