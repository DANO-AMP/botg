import logging
from aiogram import Bot

logger = logging.getLogger(__name__)


async def notify_admin(bot: Bot, admin_ids: int | list[int], text: str) -> None:
    """Send a notification to admin(s). Accepts single ID or list of IDs."""
    if isinstance(admin_ids, int):
        admin_ids = [admin_ids]
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logger.warning("Failed to send admin notification to %s", admin_id)
