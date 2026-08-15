"""Admin-facing top-up flow: GB amount -> toman amount -> receipt photo -> submit."""

from __future__ import annotations

import os
import uuid

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from .. import keyboards, texts
from ..states import TopUp
from ... import db
from ...config import settings
from ...services.nexra_panel import nexra_panel

router = Router(name="topup")


@router.message(F.text == texts.BTN_TOPUP)
async def start_topup(message: Message, state: FSMContext) -> None:
    admin = await nexra_panel.get_admin(message.from_user.id)
    if admin is None:
        await message.answer(texts.NOT_LINKED_RETRY)
        return
    await state.set_state(TopUp.amount_gb)
    await message.answer(texts.ASK_AMOUNT_GB)


@router.message(TopUp.amount_gb)
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
    await state.update_data(amount_gb=amount)
    await state.set_state(TopUp.toman_amount)
    await message.answer(texts.ASK_TOMAN_AMOUNT)


@router.message(TopUp.toman_amount)
async def get_toman_amount(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace(",", "").replace("٬", "")
    if not raw.isdigit():
        await message.answer(texts.INVALID_TOMAN_AMOUNT)
        return
    await state.update_data(toman_amount=int(raw))
    await state.set_state(TopUp.receipt)
    await message.answer(texts.ASK_RECEIPT)


@router.message(TopUp.receipt)
async def get_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.photo:
        await message.answer(texts.NOT_A_PHOTO)
        return

    data = await state.get_data()
    await state.clear()

    admin = await nexra_panel.get_admin(message.from_user.id)
    if admin is None:
        await message.answer(texts.NOT_LINKED_RETRY)
        return

    os.makedirs(settings.media_dir, exist_ok=True)
    filename = f"receipt_{uuid.uuid4().hex}.jpg"
    receipt_path = os.path.join(settings.media_dir, filename)
    await bot.download(message.photo[-1], destination=receipt_path)

    request_id = db.create_request(
        admin_telegram_id=message.from_user.id,
        admin_username=admin["username"],
        requested_gb=data["amount_gb"],
        toman_amount=data["toman_amount"],
        receipt_path=receipt_path,
    )

    await message.answer(texts.REQUEST_SUBMITTED)

    caption = (
        f"درخواست شارژ حجم جدید #{request_id}\n"
        f"ادمین: {admin['username']} (telegram_id: {message.from_user.id})\n"
        f"حجم درخواستی: {data['amount_gb']:g} گیگابایت\n"
        f"مبلغ واریزی: {data['toman_amount']:,} تومان"
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
