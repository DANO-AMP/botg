import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands

from bot.config import load_config
from bot import db
from bot.services.maxelpay import MaxelPayClient
from bot.services.webhook_server import (
    start_webhook_server, stop_webhook_server,
    restore_expiry_timers, cancel_all_expiry_timers,
)
from bot.handlers import start, catalog, purchase, admin, referral, deposit
from bot.middlewares.auth import AdminMiddleware


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()

    os.makedirs(os.path.dirname(config.db_path) or ".", exist_ok=True)
    await db.connect(config.db_path)

    bot = Bot(token=config.telegram_token)
    dp = Dispatcher(storage=MemoryStorage())
    maxelpay = MaxelPayClient(
        api_key=config.maxelpay_api_key,
        secret_key=config.maxelpay_secret_key,
        webhook_base_url=config.webhook_base_url,
        mode=config.maxelpay_mode,
    )

    dp["config"] = config
    dp["maxelpay"] = maxelpay

    admin_router = admin.router
    admin_router.message.middleware(AdminMiddleware(config))
    admin_router.callback_query.middleware(AdminMiddleware(config))

    dp.include_routers(
        start.router,
        catalog.router,
        purchase.router,
        deposit.router,
        referral.router,
        admin_router,
    )

    await bot.set_my_commands([
        BotCommand(command="start", description="Main menu"),
        BotCommand(command="admin", description="Admin panel"),
    ])
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    try:
        await start_webhook_server(
            bot, maxelpay,
            port=config.webhook_port,
            admin_id=config.admin_telegram_ids[0],
            bonus_usd=config.referral_bonus_usd,
        )
        await restore_expiry_timers(config.order_timeout_minutes)
        logging.info("Bot starting...")
        await dp.start_polling(bot)
    finally:
        cancel_all_expiry_timers()
        await stop_webhook_server()
        await db.close()
        await maxelpay.close()
        logging.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
