from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot import db
from bot.keyboards.inline import main_menu_kb, back_to_main_kb, NavCallback

router = Router()

WELCOME = "Welcome to the Store!\n\nBrowse products and pay with crypto."


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    await state.clear()
    args = message.text.split(maxsplit=1)
    referred_by: int | None = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1][4:])
            if ref_id != message.from_user.id:
                referred_by = ref_id
        except ValueError:
            pass

    await db.get_or_create_user(message.from_user.id, message.from_user.username, referred_by)

    if referred_by:
        existing_ref = await db.get_user(referred_by)
        if existing_ref:
            user = await db.get_user(message.from_user.id)
            if user and user.get("referred_by") == referred_by:
                await db.add_referral(referred_by, message.from_user.id)

    await message.answer(WELCOME, reply_markup=main_menu_kb())


@router.callback_query(NavCallback.filter(F.to == "main"))
async def show_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(WELCOME, reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(NavCallback.filter(F.to == "my_orders"))
async def show_my_orders(callback: CallbackQuery) -> None:
    orders = await db.get_user_orders(callback.from_user.id)
    if not orders:
        text = "You have no orders yet."
    else:
        lines = [f"#{o['id']} {o['status'].upper()} — {o['product_name']} ${o['amount_usd']:.2f}" for o in orders]
        text = "Your orders:\n\n" + "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=back_to_main_kb())
    await callback.answer()


@router.callback_query(NavCallback.filter(F.to == "balance"))
async def show_balance(callback: CallbackQuery) -> None:
    user = await db.get_user(callback.from_user.id)
    balance = user["balance"] if user else 0.0
    await callback.message.edit_text(
        f"Your balance: ${balance:.2f} USD\n\nUsed automatically when you buy products.",
        reply_markup=back_to_main_kb(),
    )
    await callback.answer()
