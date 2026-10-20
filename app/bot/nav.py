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
from .. import db
from ..config import settings

# Named rather than listed by label: a label can be changed from the Nexra
# panel, and customize.refresh_menu_texts() then refills the set in place (the
# filters hold this very object), keeping the default labels in it as well.
MENU_KEYS = (
    "BTN_CANCEL",
    "BTN_TOPUP",
    "BTN_BALANCE",
    "BTN_CHANGE_PASSWORD",
    "BTN_CREATE_PANEL",
    "BTN_TUTORIALS",
    "BTN_ADD_TUTORIAL",
    "BTN_DELETE_TUTORIAL",
    "BTN_VIEW_TUTORIALS",
    "BTN_SEC_PANELS",
    "BTN_SEC_FINANCE",
    "BTN_SEC_USERS",
    "BTN_SEC_SETTINGS",
    "BTN_BACK",
    "BTN_TOGGLE_AUTO_APPROVE",
    "BTN_SALES_REPORT",
    "BTN_DIGEST",
    "BTN_PANEL_HISTORY",
    "BTN_MESSAGE_USER",
    "BTN_PENDING_REQUESTS",
    "BTN_TOGGLE_FORCE_JOIN",
    "BTN_SET_FORCE_JOIN_CHANNEL",
    "BTN_SET_PRICE",
    "BTN_SET_CARD",
    "BTN_SET_BULK_PIN",
    "BTN_EXPORT_ALL_PASSWORDS",
    "BTN_PAY",
    "BTN_PAY_CARD",
    "BTN_SYNC_TELEGRAM_IDS",
    "BTN_MY_PANELS",
    "BTN_ALL_PANELS",
    "BTN_GRANT_TRAFFIC",
    "BTN_BROADCAST",
    "BTN_TOPUP_THIS_PANEL",
    "BTN_WALLET",
    "BTN_CHARGE_WALLET",
    "BTN_PAY_WALLET",
    "BTN_PAY_WEEKLY",
    "BTN_PAY_DEBT",
    "BTN_DEBTS",
    "BTN_TOGGLE_WEEKLY",
    "BTN_GRANT_WALLET",
    "BTN_BACKUP",
    "BTN_CREATE_ADMIN",
    "BTN_NEW_INVOICE",
    "BTN_INVOICES",
    "BTN_PAY_INVOICE",
    "BTN_MY_INVOICES",
    "BTN_PANEL_LOGIN",
    "BTN_FORECAST",
    "BTN_SEARCH_USER",
    "BTN_PARTNERSHIP",
    "BTN_WALLET_CUSTOM",
)
ALL_MENU_TEXTS: set[str] = {getattr(texts, name) for name in MENU_KEYS}


# Which section each superadmin currently has open. Finishing an action returns
# them to it rather than to the root menu, so setting the price and then the card
# number doesn't mean walking back in through Settings each time. In memory on
# purpose: it is a UI position, not data, and falling back to the root menu after
# a restart is the right thing to do anyway.
_open_section: dict[int, str] = {}


def remember_section(user_id: int, section: str) -> None:
    _open_section[user_id] = section


def forget_section(user_id: int) -> None:
    _open_section.pop(user_id, None)


def superadmin_kb(user_id: int):
    """The section keyboard this superadmin is in, or the root menu."""
    builder = keyboards.SECTION_KEYBOARDS.get(_open_section.get(user_id))
    return builder() if builder else keyboards.superadmin_menu_kb()


async def menu_kb_for(user_id: int):
    """The persistent reply keyboard this user should see outside any flow.

    Reads the linkage cached at their last successful panel lookup rather than
    calling the panel again: cancelling an action must never depend on the panel
    being reachable, and a momentary outage must not strip a linked admin's menu
    down to the unlinked one.
    """
    if user_id in settings.superadmin_id_list:
        return superadmin_kb(user_id)
    if db.is_user_linked(user_id):
        return keyboards.main_menu_kb()
    # No panel: the wallet and invoices only open once we have billed them.
    if db.has_billing_account(user_id):
        return keyboards.unlinked_menu_kb()
    return keyboards.prospect_menu_kb()


async def cancel_and_show_menu(message: Message, state: FSMContext) -> None:
    # A receipt held back from the automatic approver while the superadmin was
    # typing goes back to it, or it would sit unapproved until someone noticed.
    held = (await state.get_data()).get("held_request_id")
    if held is not None:
        from . import auto_approve  # here: auto_approve pulls in most of the bot

        auto_approve.release(held)
    await state.clear()
    await message.answer(texts.CANCELLED, reply_markup=await menu_kb_for(message.from_user.id))
