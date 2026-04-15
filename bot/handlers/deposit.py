import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot import db
from bot.keyboards.inline import (
    DepositCallback, deposit_pending_kb, back_to_main_kb,
)
from bot.services.cryptopay import CryptoPayClient
from bot.services.deposit_checker import start_deposit_monitor, stop_deposit_monitor
from bot.services.notifications import notify_admin
from bot.config import Config

router = Router()


class DepositStates(StatesGroup):
    waiting_amount = State()


@router.callback_query(DepositCallback.filter(F.action == "start"))
async def deposit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer("Session expired.", show_alert=True)
        return
    await state.set_state(DepositStates.waiting_amount)
    await callback.message.edit_text(
        "💎 Enter the amount you want to deposit in USD (e.g. 10):"
    )
    await callback.answer()


@router.message(DepositStates.waiting_amount)
async def receive_deposit_amount(
    message: Message,
    state: FSMContext,
    cryptopay: CryptoPayClient,
    config: Config,
) -> None:
    if not message.from_user:
        return
    text = (message.text or "").strip().lstrip("$").replace(",", ".")
    try:
        amount = float(text)
        if amount < 1.0:
            await message.answer("Minimum deposit is $1.00. Enter amount:")
            return
    except ValueError:
        await message.answer("Invalid amount. Enter a number (e.g. 10):")
        return

    await state.clear()

    pending = await db.count_pending_deposits(message.from_user.id)
    if pending >= 3:
        await message.answer(
            "You have 3 pending deposits. Wait or cancel one first.",
            reply_markup=back_to_main_kb(),
        )
        return

    try:
        invoice = await cryptopay.create_invoice(
            amount_usd=amount,
            description=f"Balance deposit ${amount:.2f}",
            expires_in=config.order_timeout_minutes * 60,
            payload=f"deposit:user:{message.from_user.id}:amount:{amount}",
        )
    except Exception:
        await message.answer(
            "Error creating payment. Please try again.",
            reply_markup=back_to_main_kb(),
        )
        return

    deposit_id = await db.create_deposit(
        user_id=message.from_user.id,
        amount_usd=amount,
        created_at_ms=int(time.time() * 1000),
        invoice_id=str(invoice["invoice_id"]),
    )

    await start_deposit_monitor(
        deposit_id, message.bot, cryptopay,
        config.order_timeout_minutes, config.payment_check_interval,
        admin_id=config.admin_telegram_id,
    )

    reply_text = (
        f"💎 Deposit #{deposit_id}\n\n"
        f"💲 Amount: ${amount:.2f} USD\n\n"
        f"Tap 💳 Pay Now to complete payment.\n"
        f"⏱ You have {config.order_timeout_minutes} minutes."
    )
    await notify_admin(message.bot, config.admin_telegram_id,
        f"💎 New deposit #{deposit_id}\n👤 User: {message.from_user.id}\n💲 ${amount:.2f}")

    await message.answer(reply_text, reply_markup=deposit_pending_kb(deposit_id, invoice["pay_url"]))


@router.callback_query(DepositCallback.filter(F.action == "check"))
async def check_deposit_payment(callback: CallbackQuery, callback_data: DepositCallback) -> None:
    if not callback.from_user:
        await callback.answer("Cannot identify user.", show_alert=True)
        return
    deposit = await db.get_deposit(callback_data.id)
    if not deposit or deposit["user_id"] != callback.from_user.id:
        await callback.answer("Deposit not found.", show_alert=True)
        return
    status_msg = {
        "pending": "Payment not confirmed yet. Please wait or try again.",
        "completed": "Deposit confirmed! Your balance has been credited.",
        "expired": "This deposit request has expired.",
        "cancelled": "This deposit was cancelled.",
    }
    await callback.answer(status_msg.get(deposit["status"], deposit["status"]), show_alert=True)


@router.callback_query(DepositCallback.filter(F.action == "cancel"))
async def cancel_deposit(callback: CallbackQuery, callback_data: DepositCallback, cryptopay: CryptoPayClient, config: Config) -> None:
    if not callback.message:
        await callback.answer("Session expired.", show_alert=True)
        return
    if not callback.from_user:
        await callback.answer("Cannot identify user.", show_alert=True)
        return
    deposit = await db.get_deposit(callback_data.id)
    if not deposit or deposit["user_id"] != callback.from_user.id:
        await callback.answer("Deposit not found.", show_alert=True)
        return
    if deposit["status"] != "pending":
        await callback.answer("Cannot cancel this deposit.", show_alert=True)
        return
    stop_deposit_monitor(callback_data.id)
    if deposit.get("invoice_id"):
        await cryptopay.delete_invoice(int(deposit["invoice_id"]))
    await db.update_deposit_status(callback_data.id, "cancelled")
    await notify_admin(callback.bot, config.admin_telegram_id,
        f"❌ Deposit #{callback_data.id} cancelled by user {callback.from_user.id}")
    await callback.message.edit_text("❌ Deposit cancelled.", reply_markup=back_to_main_kb())
    await callback.answer()
