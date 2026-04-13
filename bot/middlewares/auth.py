from typing import Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from bot.config import Config


class AdminMiddleware(BaseMiddleware):
    def __init__(self, config: Config) -> None:
        self._admin_id = config.admin_telegram_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id != self._admin_id:
            if isinstance(event, CallbackQuery):
                await event.answer("Access denied.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("Access denied.")
            return
        return await handler(event, data)
