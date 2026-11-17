"""Superadmin: add traffic to a panel or take some back.

Reached two ways: from a customer's profile card (➕ / ➖ beside their other
actions — the panel is picked from theirs), or from the panels section's
"➖ کسر حجم" button, which asks for the panel's username like "➕ افزودن حجم"
does.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards, texts, traffic
from ..filters import Label, SuperadminFilter
from ..nav import ALL_MENU_TEXTS, superadmin_kb
from ..states import AdjustTraffic
from ...services.nexra_panel import NexraPanelError, nexra_panel
from ...units import bytes_to_gb
from .user_search import show_profile

router = Router(name="traffic")
router.message.filter(SuperadminFilter())
router.callback_query.filter(SuperadminFilter())

# Rounding in the GB shown can make "everything that's left" a hair more than
# what's actually there; that much over is still taken as everything.
_TOLERANCE_GB = 0.005


async def _ask_amount(
    message: Message, state: FSMContext, panel: dict, mode: str, profile: int | None
) -> None:
    remaining = bytes_to_gb(panel.get("traffic"))
    await state.set_state(AdjustTraffic.amount)
    await state.update_data(
        trf_username=panel["username"], trf_mode=mode, trf_remaining=remaining, trf_profile=profile
    )
    if mode == traffic.ADD:
        prompt = texts.ASK_GRANT_AMOUNT.format(username=panel["username"])
    else:
        prompt = texts.ASK_DEDUCT_TRAFFIC_AMOUNT.format(
            username=panel["username"], remaining_gb=remaining
        )
    await message.answer(prompt, reply_markup=keyboards.cancel_kb())


# ---- from the panels section, by username -----------------------------------

@router.message(Label("BTN_DEDUCT_TRAFFIC"))
async def start_deduct(message: Message, state: FSMContext) -> None:
    await state.set_state(AdjustTraffic.username)
    await message.answer(texts.ASK_DEDUCT_TRAFFIC_USERNAME, reply_markup=keyboards.cancel_kb())


@router.message(AdjustTraffic.username, ~F.text.in_(ALL_MENU_TEXTS))
async def got_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip()
    if not username:
        await message.answer(texts.ASK_DEDUCT_TRAFFIC_USERNAME)
        return
    try:
        panel = await traffic.find_panel(username)
    except NexraPanelError as exc:
        await state.clear()
        await message.answer(
            texts.DEDUCT_TRAFFIC_FAILED.format(error=exc),
            reply_markup=superadmin_kb(message.from_user.id),
        )
        return
    if not panel:
        await message.answer(texts.PANEL_USERNAME_NOT_FOUND.format(username=username))
        return
    await _ask_amount(message, state, panel, traffic.SUB, profile=None)


# ---- from a customer's profile card -----------------------------------------

@router.callback_query(F.data.startswith("usr_trf:"))
async def from_profile(call: CallbackQuery, state: FSMContext) -> None:
    _, mode, raw_id = call.data.split(":", 2)
    target = int(raw_id)
    try:
        panels = await nexra_panel.get_admins(target)
    except NexraPanelError:
        await call.answer(texts.PANEL_UNREACHABLE, show_alert=True)
        return
    if not panels:
        await call.answer(texts.USER_HAS_NO_PANELS, show_alert=True)
        return

    await call.answer()
    if len(panels) == 1:
        await _ask_amount(call.message, state, panels[0], mode, profile=target)
        return
    # Kept for when the panel is picked, so the card can be shown again after.
    await state.set_state(None)
    await state.update_data(trf_profile=target)
    await call.message.answer(
        texts.CHOOSE_PANEL_FOR_TRAFFIC,
        reply_markup=keyboards.traffic_panel_picker_kb(panels, mode),
    )


@router.callback_query(F.data.startswith("trf:"))
async def picked_panel(call: CallbackQuery, state: FSMContext) -> None:
    _, mode, username = call.data.split(":", 2)
    try:
        panel = await traffic.find_panel(username)  # fresh numbers, not the picker's
    except NexraPanelError:
        await call.answer(texts.PANEL_UNREACHABLE, show_alert=True)
        return
    if not panel:
        await call.answer(texts.USER_HAS_NO_PANELS, show_alert=True)
        return
    await call.answer()
    profile = (await state.get_data()).get("trf_profile") or panel.get("telegram_id")
    await _ask_amount(call.message, state, panel, mode, profile=profile)


# ---- the amount, whichever way it was reached -------------------------------

@router.message(AdjustTraffic.amount, ~F.text.in_(ALL_MENU_TEXTS))
async def got_amount(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip().replace(",", ".")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.INVALID_AMOUNT_GB)
        return

    data = await state.get_data()
    mode, remaining = data["trf_mode"], data["trf_remaining"]
    if mode == traffic.SUB and amount > remaining + _TOLERANCE_GB:
        # Stays in this step: the next number typed is the corrected amount.
        await message.answer(texts.DEDUCT_TRAFFIC_TOO_MUCH.format(remaining_gb=remaining))
        return
    if mode == traffic.SUB:
        amount = min(amount, remaining)

    await state.clear()
    ok, reply = await traffic.change(bot, data["trf_username"], amount, mode)
    await message.answer(reply, reply_markup=superadmin_kb(message.from_user.id))

    # Back to the card it was started from, now showing the new numbers.
    if ok and data.get("trf_profile"):
        await show_profile(message, data["trf_profile"])
