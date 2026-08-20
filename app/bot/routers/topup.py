"""Admin-facing top-up flow:
pick panel (skipped if they own one) -> GB amount -> auto-computed invoice
-> پرداخت -> payment method (card-to-card only, for now) -> card number
-> receipt -> submit for review.
"""

from __future__ import annotations

import os
import uuid

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from .. import keyboards, texts
from ..nav import ALL_MENU_TEXTS
from ..panels import choose_panel, owned_panel
from ..states import TopUp
from ... import db
from ...config import settings

router = Router(name="topup")


async def _ask_amount(message: Message, state: FSMContext, username: str) -> None:
    await state.update_data(panel_username=username)
    await state.set_state(TopUp.amount_gb)
    await message.answer(texts.ASK_AMOUNT_GB, reply_markup=keyboards.cancel_kb())


@router.message(F.text == texts.BTN_TOPUP)
async def start_topup(message: Message, state: FSMContext) -> None:
    admin = await choose_panel(message, "topup")
    if admin:
        await _ask_amount(message, state, admin["username"])


@router.callback_query(F.data.startswith("pick:topup:"))
async def picked_panel_for_topup(call: CallbackQuery, state: FSMContext) -> None:
    username = call.data.split(":", 2)[2]
    target = await owned_panel(call.from_user.id, username)
    if not target:
        await call.answer(texts.NOT_LINKED_RETRY, show_alert=True)
        return
    await call.answer()
    await _ask_amount(call.message, state, username)


@router.message(TopUp.amount_gb, ~F.text.in_(ALL_MENU_TEXTS))
async def get_amount_gb(message: Message, state: FSMContext) -> None:
    try:
        amount = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        amount = None
    if amount is None or not (settings.min_gb <= amount <= settings.max_gb):
        await message.answer(
            f"{texts.INVALID_AMOUNT_GB} (بین {settings.min_gb:g} تا {settings.max_gb:g} گیگابایت)"
        )
        return

    price_per_gb_raw = db.get_setting("price_per_gb")
    if not price_per_gb_raw:
        await state.clear()
        await message.answer(texts.PRICE_NOT_SET, reply_markup=keyboards.main_menu_kb())
        return

    total_price = round(amount * float(price_per_gb_raw))
    await state.update_data(amount_gb=amount, total_price=total_price)
    await state.set_state(TopUp.awaiting_payment)
    await message.answer(
        texts.INVOICE_TEXT.format(gb=amount, price=total_price),
        reply_markup=keyboards.invoice_kb(),
    )


@router.callback_query(F.data == "topup_pay", TopUp.awaiting_payment)
async def show_payment_methods(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(
        texts.PAYMENT_METHODS_TEXT, reply_markup=keyboards.payment_methods_kb()
    )


@router.callback_query(F.data == "pay_method:card", TopUp.awaiting_payment)
async def show_card_payment(call: CallbackQuery, state: FSMContext) -> None:
    card_number = db.get_setting("card_number")
    if not card_number:
        await call.answer()
        await call.message.answer(texts.CARD_NOT_CONFIGURED)
        return

    data = await state.get_data()
    await call.answer()
    await state.set_state(TopUp.receipt)
    await call.message.answer(
        texts.CARD_PAYMENT_INSTRUCTIONS.format(price=data["total_price"], card_number=card_number),
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(TopUp.receipt, ~F.text.in_(ALL_MENU_TEXTS))
async def get_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.photo:
        await message.answer(texts.NOT_A_PHOTO)
        return

    data = await state.get_data()
    await state.clear()
    username = data["panel_username"]

    target = await owned_panel(message.from_user.id, username)
    if not target:
        await message.answer(texts.NOT_LINKED_RETRY, reply_markup=keyboards.unlinked_menu_kb())
        return

    os.makedirs(settings.media_dir, exist_ok=True)
    receipt_path = os.path.join(settings.media_dir, f"receipt_{uuid.uuid4().hex}.jpg")
    await bot.download(message.photo[-1], destination=receipt_path)

    request_id = db.create_request(
        admin_telegram_id=message.from_user.id,
        admin_username=username,
        requested_gb=data["amount_gb"],
        toman_amount=data["total_price"],
        receipt_path=receipt_path,
    )

    await message.answer(texts.REQUEST_SUBMITTED, reply_markup=keyboards.main_menu_kb())

    caption = (
        f"🧾 درخواست شارژ حجم جدید #{request_id}\n"
        f"🖥 پنل: {username}\n"
        f"👤 آیدی عددی: {message.from_user.id}\n"
        f"📶 حجم درخواستی: {data['amount_gb']:g} گیگابایت\n"
        f"💰 مبلغ: {data['total_price']:,} تومان"
    )
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_photo(
                superadmin_id,
                photo=FSInputFile(receipt_path),
                caption=caption,
                reply_markup=keyboards.approval_kb(request_id, message.from_user.id),
            )
        except Exception:
            continue
