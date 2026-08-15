"""Superadmin-facing: configure the per-GB price and the card number used for
card-to-card payments — read by the top-up flow in routers/topup.py."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import texts
from ..filters import SuperadminFilter
from ..states import SetCardNumber, SetPricePerGb
from ... import db

router = Router(name="admin_settings")
router.message.filter(SuperadminFilter())


@router.message(F.text == texts.BTN_SET_PRICE)
async def start_set_price(message: Message, state: FSMContext) -> None:
    await state.set_state(SetPricePerGb.value)
    await message.answer(texts.ASK_PRICE_PER_GB)


@router.message(SetPricePerGb.value)
async def finish_set_price(message: Message, state: FSMContext) -> None:
    await state.clear()
    raw = (message.text or "").strip().replace(",", "")
    try:
        price = float(raw)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.INVALID_PRICE)
        return
    db.set_setting("price_per_gb", str(price))
    await message.answer(texts.PRICE_SET_CONFIRM.format(price=int(price)))


@router.message(F.text == texts.BTN_SET_CARD)
async def start_set_card(message: Message, state: FSMContext) -> None:
    await state.set_state(SetCardNumber.value)
    await message.answer(texts.ASK_CARD_NUMBER)


@router.message(SetCardNumber.value)
async def finish_set_card(message: Message, state: FSMContext) -> None:
    await state.clear()
    card_number = (message.text or "").strip()
    if not card_number:
        await message.answer(texts.INVALID_CARD_NUMBER)
        return
    db.set_setting("card_number", card_number)
    await message.answer(texts.CARD_SET_CONFIRM)
