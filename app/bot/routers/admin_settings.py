"""Superadmin-facing: configure the per-GB price, the card-to-card number, the
force-join channel, and the bulk-credentials-export PIN."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import keyboards, texts
from ..filters import SuperadminFilter
from ..nav import ALL_MENU_TEXTS
from ..states import ExportCredentials, SetBulkPin, SetCardNumber, SetForceJoinChannel, SetPricePerGb
from ... import db
from ...services.nexra_panel import NexraPanelError, nexra_panel

router = Router(name="admin_settings")
router.message.filter(SuperadminFilter())


@router.message(F.text == texts.BTN_SET_PRICE)
async def start_set_price(message: Message, state: FSMContext) -> None:
    await state.set_state(SetPricePerGb.value)
    await message.answer(texts.ASK_PRICE_PER_GB, reply_markup=keyboards.cancel_kb())


@router.message(SetPricePerGb.value, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_set_price(message: Message, state: FSMContext) -> None:
    await state.clear()
    raw = (message.text or "").strip().replace(",", "")
    try:
        price = float(raw)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.INVALID_PRICE, reply_markup=keyboards.superadmin_menu_kb())
        return
    db.set_setting("price_per_gb", str(price))
    await message.answer(
        texts.PRICE_SET_CONFIRM.format(price=int(price)), reply_markup=keyboards.superadmin_menu_kb()
    )


@router.message(F.text == texts.BTN_SET_CARD)
async def start_set_card(message: Message, state: FSMContext) -> None:
    await state.set_state(SetCardNumber.value)
    await message.answer(texts.ASK_CARD_NUMBER, reply_markup=keyboards.cancel_kb())


@router.message(SetCardNumber.value, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_set_card(message: Message, state: FSMContext) -> None:
    await state.clear()
    card_number = (message.text or "").strip()
    if not card_number:
        await message.answer(texts.INVALID_CARD_NUMBER, reply_markup=keyboards.superadmin_menu_kb())
        return
    db.set_setting("card_number", card_number)
    await message.answer(texts.CARD_SET_CONFIRM, reply_markup=keyboards.superadmin_menu_kb())


@router.message(F.text == texts.BTN_SET_FORCE_JOIN_CHANNEL)
async def start_set_channel(message: Message, state: FSMContext) -> None:
    await state.set_state(SetForceJoinChannel.value)
    await message.answer(texts.ASK_FORCE_JOIN_CHANNEL, reply_markup=keyboards.cancel_kb())


@router.message(SetForceJoinChannel.value, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_set_channel(message: Message, state: FSMContext) -> None:
    await state.clear()
    channel = (message.text or "").strip()
    if not channel.startswith("@"):
        await message.answer(texts.INVALID_CHANNEL, reply_markup=keyboards.superadmin_menu_kb())
        return
    db.set_setting("force_join_channel", channel)
    await message.answer(
        texts.FORCE_JOIN_CHANNEL_SET.format(channel=channel),
        reply_markup=keyboards.superadmin_menu_kb(),
    )


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


@router.message(F.text == texts.BTN_SET_BULK_PIN)
async def start_set_bulk_pin(message: Message, state: FSMContext) -> None:
    await state.set_state(SetBulkPin.value)
    await message.answer(texts.ASK_BULK_PIN_SET, reply_markup=keyboards.cancel_kb())


@router.message(SetBulkPin.value, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_set_bulk_pin(message: Message, state: FSMContext) -> None:
    await state.clear()
    pin = (message.text or "").strip()
    if not pin:
        await message.answer(texts.INVALID_BULK_PIN, reply_markup=keyboards.superadmin_menu_kb())
        return
    db.set_setting("bulk_password_pin", pin)
    await message.answer(texts.BULK_PIN_SET_CONFIRM, reply_markup=keyboards.superadmin_menu_kb())


@router.message(F.text == texts.BTN_EXPORT_ALL_PASSWORDS)
async def start_export_credentials(message: Message, state: FSMContext) -> None:
    if not db.get_setting("bulk_password_pin"):
        await message.answer(texts.BULK_PIN_NOT_SET)
        return
    await state.set_state(ExportCredentials.pin)
    await message.answer(texts.ASK_BULK_PIN_ENTER, reply_markup=keyboards.cancel_kb())


@router.message(ExportCredentials.pin, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_export_credentials(message: Message, state: FSMContext) -> None:
    await state.clear()
    entered_pin = (message.text or "").strip()
    correct_pin = db.get_setting("bulk_password_pin")
    if not correct_pin or entered_pin != correct_pin:
        await message.answer(texts.BULK_PIN_WRONG, reply_markup=keyboards.superadmin_menu_kb())
        return

    try:
        credentials = await nexra_panel.get_all_credentials()
    except NexraPanelError as exc:
        await message.answer(
            texts.SYNC_FAILED.format(error=exc), reply_markup=keyboards.superadmin_menu_kb()
        )
        return
    if not credentials:
        await message.answer(texts.NO_CREDENTIALS, reply_markup=keyboards.superadmin_menu_kb())
        return

    lines = [texts.CREDENTIALS_LIST_HEADER]
    chunks: list[str] = []
    current = lines[0]
    for admin in credentials:
        line = texts.CREDENTIALS_LINE.format(
            username=admin["username"],
            telegram_id=admin.get("telegram_id") or "—",
            password=admin["marzban_password"],
        )
        if len(current) + len(line) > 3500:
            chunks.append(current)
            current = ""
        current += line
    chunks.append(current)

    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        await message.answer(chunk, reply_markup=keyboards.superadmin_menu_kb() if is_last else None)


@router.message(F.text == texts.BTN_SYNC_TELEGRAM_IDS)
async def sync_telegram_ids(message: Message) -> None:
    await message.answer(texts.SYNC_RUNNING)
    try:
        result = await nexra_panel.sync_telegram_ids()
    except NexraPanelError as exc:
        await message.answer(
            texts.SYNC_FAILED.format(error=exc), reply_markup=keyboards.superadmin_menu_kb()
        )
        return

    updated = result.get("updated") or []
    if not updated:
        await message.answer(texts.SYNC_RESULT_NONE, reply_markup=keyboards.superadmin_menu_kb())
        return

    text = texts.SYNC_RESULT_HEADER.format(count=len(updated))
    for a in updated:
        text += texts.SYNC_RESULT_LINE.format(username=a["username"], telegram_id=a["telegram_id"])
    await message.answer(text, reply_markup=keyboards.superadmin_menu_kb())
