"""Superadmin-facing: configure the per-GB price and the card number used for
card-to-card payments — read by the top-up flow in routers/topup.py."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import texts
from ..filters import SuperadminFilter
from ..states import SetCardNumber, SetForceJoinChannel, SetPricePerGb
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


@router.message(F.text == texts.BTN_SET_FORCE_JOIN_CHANNEL)
async def start_set_channel(message: Message, state: FSMContext) -> None:
    await state.set_state(SetForceJoinChannel.value)
    await message.answer(texts.ASK_FORCE_JOIN_CHANNEL)


@router.message(SetForceJoinChannel.value)
async def finish_set_channel(message: Message, state: FSMContext) -> None:
    await state.clear()
    channel = (message.text or "").strip()
    if not channel.startswith("@"):
        await message.answer(texts.INVALID_CHANNEL)
        return
    db.set_setting("force_join_channel", channel)
    await message.answer(texts.FORCE_JOIN_CHANNEL_SET.format(channel=channel))


@router.message(F.text == texts.BTN_TOGGLE_FORCE_JOIN)
async def toggle_force_join(message: Message) -> None:
    channel = db.get_setting("force_join_channel")
    currently_on = db.get_setting("force_join_enabled") == "1"
    if not currently_on and not channel:
        await message.answer(texts.FORCE_JOIN_NO_CHANNEL_YET)
        return
    db.set_setting("force_join_enabled", "0" if currently_on else "1")
    await message.answer(
        texts.FORCE_JOIN_ENABLED_OFF if currently_on else texts.FORCE_JOIN_ENABLED_ON
    )
