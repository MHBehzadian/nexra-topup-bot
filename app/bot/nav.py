"""Shared navigation: every FSM handler that expects free text (or a photo/
video/document) must exclude these labels via `~F.text.in_(ALL_MENU_TEXTS)` on
its filter. Without that, tapping any other menu button while mid-flow gets
swallowed by the waiting handler and misread as invalid input for that state,
with no way out. Excluding these lets the tap fall through to its real
handler instead (which is state-agnostic and simply restarts cleanly), and
the dedicated Cancel handler (routers/start.py) catches BTN_CANCEL itself.
"""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from . import keyboards, texts
from ..config import settings
from ..services.nexra_panel import nexra_panel

ALL_MENU_TEXTS = {
    texts.BTN_CANCEL,
    texts.BTN_TOPUP,
    texts.BTN_BALANCE,
    texts.BTN_CHANGE_PASSWORD,
    texts.BTN_CREATE_PANEL,
    texts.BTN_TUTORIALS,
    texts.BTN_ADD_TUTORIAL,
    texts.BTN_MESSAGE_USER,
    texts.BTN_PENDING_REQUESTS,
    texts.BTN_TOGGLE_FORCE_JOIN,
    texts.BTN_SET_FORCE_JOIN_CHANNEL,
    texts.BTN_SET_PRICE,
    texts.BTN_SET_CARD,
    texts.BTN_SET_BULK_PIN,
    texts.BTN_EXPORT_ALL_PASSWORDS,
    texts.BTN_PAY,
    texts.BTN_PAY_CARD,
    texts.BTN_SYNC_TELEGRAM_IDS,
    texts.BTN_MY_PANELS,
    texts.BTN_ALL_PANELS,
    texts.BTN_GRANT_TRAFFIC,
    texts.BTN_BROADCAST,
    texts.BTN_TOPUP_THIS_PANEL,
    texts.BTN_WALLET,
    texts.BTN_CHARGE_WALLET,
    texts.BTN_PAY_WALLET,
    texts.BTN_PAY_WEEKLY,
    texts.BTN_PAY_DEBT,
    texts.BTN_DEBTS,
    texts.BTN_TOGGLE_WEEKLY,
    texts.BTN_GRANT_WALLET,
}


async def menu_kb_for(user_id: int):
    """The persistent reply keyboard this user should see outside any flow.

    Falls back to the main menu if the panel can't be reached — cancelling must
    always return a usable keyboard, even during an outage.
    """
    if user_id in settings.superadmin_id_list:
        return keyboards.superadmin_menu_kb()
    try:
        admins = await nexra_panel.get_admins(user_id)
    except Exception:
        return keyboards.main_menu_kb()
    if not admins:
        return keyboards.unlinked_menu_kb()
    return keyboards.main_menu_kb()


async def cancel_and_show_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CANCELLED, reply_markup=await menu_kb_for(message.from_user.id))
