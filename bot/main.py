import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import load_config
from bot import db
from bot.services.bitunix import BitunixClient
from bot.services.payment_checker import restore_monitors
from bot.handlers import start, catalog, purchase, admin, referral
from bot.middlewares.auth import AdminMiddleware


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()

    os.makedirs(os.path.dirname(config.db_path) or ".", exist_ok=True)
    await db.connect(config.db_path)

    bot = Bot(token=config.telegram_token)
    dp = Dispatcher(storage=MemoryStorage())

    bitunix = BitunixClient(config.bitunix_api_key, config.bitunix_secret_key)

    dp["config"] = config
    dp["bitunix"] = bitunix

    admin_router = admin.router
    admin_router.message.middleware(AdminMiddleware(config))
    admin_router.callback_query.middleware(AdminMiddleware(config))

    dp.include_routers(
        start.router,
        catalog.router,
        purchase.router,
        referral.router,
        admin_router,
    )

    await restore_monitors(
        bot, bitunix,
        config.order_timeout_minutes,
        config.payment_check_interval,
        config.admin_telegram_id,
    )

    logging.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bitunix.close()
        logging.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
