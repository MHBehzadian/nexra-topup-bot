"""A reseller making a panel for a colleague of theirs, from the bot:
kind (a Nexra panel, or one with no trace of Nexra) -> which of their panels'
servers it goes on (skipped when there is only one) -> username -> password
-> the usual top-up for its traffic -> made, with that traffic, once paid
(bot/subpanels.py).

Nothing is taken from their own panel: the new one is paid for on its own.
It is linked to their Telegram account like their own, so they see it under
their panels, top it up, and get its warnings and bills. The colleague only
ever gets a username and password — for the white-label kind, on a login page
with nothing of Nexra on it.
"""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards, subpanels, texts
from ... import db
from ..filters import Label
from ..nav import ALL_MENU_TEXTS, menu_kb_for
from ..panels import safe_get_admins
from ..states import SubPanel
from .topup import _ask_amount
from ...services.nexra_panel import NexraPanelError, SubPanelError, nexra_panel

router = Router(name="sub_panel")

# The same rule the panel applies, checked here so a bad name is asked again
# straight away instead of after the password.
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def _allowed(admins: list[dict]) -> list[dict]:
    """Their panels the superadmin has turned panel-making on for in Nexra."""
    return [a for a in admins if a.get("can_create_subpanels")]


async def _not_enabled(message: Message, user, admins: list[dict]) -> None:
    await message.answer(
        texts.CREATE_PANEL_NOT_ENABLED.format(
            user_id=user.id,
            tg_username=f"@{user.username}" if user.username else "-",
            panels="، ".join(a["username"] for a in admins) or "-",
        ),
        reply_markup=await menu_kb_for(user.id),
    )


@router.message(Label("BTN_CREATE_PANEL"))
async def start_sub_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    admins = await safe_get_admins(message)
    if admins is None:
        return
    if not _allowed(admins):
        await _not_enabled(message, message.from_user, admins)
        return
    await state.set_state(SubPanel.kind)
    await message.answer(texts.ASK_SUBPANEL_KIND, reply_markup=keyboards.subpanel_kind_kb())


@router.callback_query(F.data.startswith("subp_kind:"), SubPanel.kind)
async def picked_kind(call: CallbackQuery, state: FSMContext) -> None:
    white_label = call.data.split(":", 1)[1] == "plain"
    await state.update_data(white_label=white_label)
    await call.answer()

    try:
        admins = await nexra_panel.get_admins(call.from_user.id)
    except NexraPanelError:
        await state.clear()
        await call.message.answer(
            texts.PANEL_UNREACHABLE, reply_markup=await menu_kb_for(call.from_user.id)
        )
        return
    all_admins, admins = admins, _allowed(admins)
    if not admins:
        await state.clear()
        await _not_enabled(call.message, call.from_user, all_admins)
        return

    # The source only decides the server (and the inbounds and expiry that come
    # with it), so there is nothing to ask when all their panels share one.
    if len({a.get("panel") for a in admins}) == 1:
        await _ask_username(call.message, state, admins[0]["username"])
        return

    await state.update_data(source_choices=[a["username"] for a in admins])
    await state.set_state(SubPanel.source)
    await call.message.answer(
        texts.ASK_SUBPANEL_SOURCE, reply_markup=keyboards.subpanel_source_kb(admins)
    )


@router.callback_query(F.data.startswith("subp_src:"), SubPanel.source)
async def picked_source(call: CallbackQuery, state: FSMContext) -> None:
    choices = (await state.get_data()).get("source_choices") or []
    try:
        index = int(call.data.split(":", 1)[1])
    except ValueError:
        index = len(choices)
    if index >= len(choices):
        await call.answer(texts.PANEL_CHOICE_EXPIRED, show_alert=True)
        return
    await call.answer()
    await _ask_username(call.message, state, choices[index])


@router.callback_query(F.data.startswith("subp_kind:") | F.data.startswith("subp_src:"))
async def stale_choice(call: CallbackQuery) -> None:
    """A keyboard left over from a run that has since ended or moved on."""
    await call.answer(texts.PANEL_CHOICE_EXPIRED, show_alert=True)


async def _ask_username(message: Message, state: FSMContext, source: str) -> None:
    await state.update_data(source=source)
    await state.set_state(SubPanel.username)
    await message.answer(texts.ASK_SUBPANEL_USERNAME, reply_markup=keyboards.cancel_kb())


@router.message(SubPanel.username, ~F.text.in_(ALL_MENU_TEXTS))
async def got_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip()
    if not USERNAME_RE.match(username):
        await message.answer(texts.INVALID_SUBPANEL_USERNAME)
        return
    await state.update_data(new_username=username)
    data = await state.get_data()
    # Back here after the panel said the name was taken: the rest is known.
    if data.get("new_password"):
        await _create(message, state)
        return
    await state.set_state(SubPanel.password)
    await message.answer(texts.ASK_SUBPANEL_PASSWORD, reply_markup=keyboards.cancel_kb())


def password_ok(password: str) -> bool:
    """6 to 64 English characters with no spaces, at least one of them a letter
    and one a digit — the same rule the Nexra panel enforces."""
    return (
        6 <= len(password) <= 64
        and all(33 <= ord(c) <= 126 for c in password)
        and any(c.isascii() and c.isalpha() for c in password)
        and any(c.isdigit() for c in password)
    )


@router.message(SubPanel.password, ~F.text.in_(ALL_MENU_TEXTS))
async def got_password(message: Message, state: FSMContext) -> None:
    password = (message.text or "").strip()
    if not password_ok(password):
        await message.answer(texts.INVALID_SUBPANEL_PASSWORD)
        return
    await state.update_data(new_password=password)
    await _create(message, state)


async def _create(message: Message, state: FSMContext) -> None:
    """Check the panel could be made, then have its traffic paid for. It is
    made only once the payment goes through (bot/subpanels.py), so it never
    exists empty and nobody pays for a name that turns out to be taken."""
    user_id = message.from_user.id
    data = await state.get_data()
    source = data["source"]
    username = data["new_username"]
    if db.pending_subpanel_held_by_other(username, user_id):
        await state.set_state(SubPanel.username)
        await message.answer(texts.SUBPANEL_USERNAME_TAKEN, reply_markup=keyboards.cancel_kb())
        return
    try:
        await nexra_panel.create_sub_admin(
            telegram_id=user_id,
            source_username=source,
            username=username,
            password=data["new_password"],
            white_label=bool(data.get("white_label")),
            dry_run=True,
        )
    except SubPanelError as exc:
        await _explain_failure(message, state, exc, source)
        return
    except NexraPanelError as exc:
        await state.clear()
        await message.answer(
            texts.SUBPANEL_FAILED.format(error=exc), reply_markup=await menu_kb_for(user_id)
        )
        return

    db.save_pending_subpanel(
        username=username,
        telegram_id=user_id,
        source=source,
        password=data["new_password"],
        white_label=bool(data.get("white_label")),
    )
    await state.clear()
    await message.answer(
        texts.SUBPANEL_PAY_FIRST.format(username=username, min_gb=subpanels.MIN_GB)
    )
    # The usual top-up from here on — same amounts, prices and ways to pay —
    # with the new username as its panel.
    await _ask_amount(message, state, username)


async def _explain_failure(
    message: Message, state: FSMContext, exc: SubPanelError, source: str
) -> None:
    """Ask again for a taken username; end the flow for everything else."""
    if exc.status == 409 and "already exists" in exc.message:
        await state.set_state(SubPanel.username)
        await message.answer(texts.SUBPANEL_USERNAME_TAKEN, reply_markup=keyboards.cancel_kb())
        return

    await state.clear()
    menu = await menu_kb_for(message.from_user.id)
    if exc.status == 403 and "not enabled" in exc.message:
        await message.answer(
            texts.CREATE_PANEL_NOT_ENABLED.format(
                user_id=message.from_user.id,
                tg_username=f"@{message.from_user.username}" if message.from_user.username else "-",
                panels=source,
            ),
            reply_markup=menu,
        )
        return
    if exc.status == 403:
        await message.answer(texts.SUBPANEL_SOURCE_LOCKED.format(source=source), reply_markup=menu)
        return
    await message.answer(texts.SUBPANEL_FAILED.format(error=exc.message), reply_markup=menu)
