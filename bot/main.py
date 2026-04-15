import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands

from bot.config import load_config
from bot import db
from bot.services.cryptopay import CryptoPayClient
from bot.services.payment_checker import restore_monitors, cancel_all_monitors
from bot.services.deposit_checker import restore_deposit_monitors, cancel_all_deposit_monitors
from bot.handlers import start, catalog, purchase, admin, referral, deposit
from bot.middlewares.auth import AdminMiddleware


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()

    os.makedirs(os.path.dirname(config.db_path) or ".", exist_ok=True)
    await db.connect(config.db_path)

    bot = Bot(token=config.telegram_token)
    dp = Dispatcher(storage=MemoryStorage())
    cryptopay = CryptoPayClient(config.cryptobot_token)

    dp["config"] = config
    dp["cryptopay"] = cryptopay

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
        await restore_monitors(
            bot, cryptopay,
            config.order_timeout_minutes,
            config.payment_check_interval,
            config.admin_telegram_ids[0],
            bonus_usd=config.referral_bonus_usd,
        )
        await restore_deposit_monitors(
            bot, cryptopay,
            config.order_timeout_minutes,
            config.payment_check_interval,
            admin_id=config.admin_telegram_ids[0],
        )
        logging.info("Bot starting...")
        await dp.start_polling(bot)
    finally:
        cancel_all_monitors()
        cancel_all_deposit_monitors()
        await db.close()
        await cryptopay.close()
        logging.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
