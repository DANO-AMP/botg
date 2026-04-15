from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot import db
from bot.keyboards.inline import NavCallback, back_to_main_kb

router = Router()


@router.callback_query(NavCallback.filter(F.to == "referral"))
async def show_referral(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer("Session expired.", show_alert=True)
        return
    if not callback.from_user:
        await callback.answer("Cannot identify user.", show_alert=True)
        return
    user = await db.get_user(callback.from_user.id)
    stats = await db.get_referral_stats(callback.from_user.id)
    bot_me = await callback.bot.get_me()
    link = f"t.me/{bot_me.username}?start=ref_{callback.from_user.id}"
    balance = user["balance"] if user else 0.0
    text = (
        f"🔗 Your referral link:\n{link}\n\n"
        f"👥 Referrals: {stats['count']}\n"
        f"💰 Bonus earned: ${stats['total_earned']:.2f}\n"
        f"💵 Your balance: ${balance:.2f}\n\n"
        f"🎁 Both you and your friend get $10 after their first purchase!"
    )
    await callback.message.edit_text(text, reply_markup=back_to_main_kb())
    await callback.answer()
