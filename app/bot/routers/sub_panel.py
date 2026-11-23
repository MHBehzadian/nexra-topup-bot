"""A reseller making a panel for a colleague of theirs, from the bot:
kind (a Nexra panel, or one with no trace of Nexra) -> which of their panels
pays for it (skipped if they own one) -> username -> password -> traffic.

The traffic moves out of their own panel into the new one, and the new panel
is linked to their Telegram account like their own: they see it under their
panels, top it up, and get its warnings and bills. The colleague only ever
gets a username and password — for the white-label kind, on a login page with
nothing of Nexra on it.
"""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards, texts
from ..filters import Label
from ..nav import ALL_MENU_TEXTS, menu_kb_for
from ..panels import safe_get_admins
from ..states import SubPanel
from ...config import settings
from ...services.nexra_panel import NexraPanelError, SubPanelError, nexra_panel
from ...units import bytes_to_gb

router = Router(name="sub_panel")

# The same rule the panel applies, checked here so a bad name is asked again
# straight away instead of after the password and the traffic.
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


@router.message(Label("BTN_CREATE_PANEL"))
async def start_sub_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    admins = await safe_get_admins(message)
    if admins is None:
        return
    if not admins:
        await message.answer(
            texts.CREATE_PANEL_NEEDS_PANEL, reply_markup=await menu_kb_for(message.from_user.id)
        )
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
    if not admins:
        await state.clear()
        await call.message.answer(
            texts.CREATE_PANEL_NEEDS_PANEL, reply_markup=await menu_kb_for(call.from_user.id)
        )
        return

    if len(admins) == 1:
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
        await _ask_traffic(message, state)
        return
    await state.set_state(SubPanel.password)
    await message.answer(texts.ASK_SUBPANEL_PASSWORD, reply_markup=keyboards.cancel_kb())


@router.message(SubPanel.password, ~F.text.in_(ALL_MENU_TEXTS))
async def got_password(message: Message, state: FSMContext) -> None:
    password = (message.text or "").strip()
    if not 6 <= len(password) <= 64 or any(c.isspace() for c in password):
        await message.answer(texts.INVALID_SUBPANEL_PASSWORD)
        return
    await state.update_data(new_password=password)
    await _ask_traffic(message, state)


async def _source_panel(telegram_id: int, source: str) -> dict | None:
    """The source panel as it is now — its balance moves while the flow runs."""
    admins = await nexra_panel.get_admins(telegram_id)
    return next((a for a in admins if a["username"] == source), None)


async def _ask_traffic(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        panel = await _source_panel(message.chat.id, data["source"])
    except NexraPanelError:
        await state.clear()
        await message.answer(texts.PANEL_UNREACHABLE, reply_markup=await menu_kb_for(message.chat.id))
        return
    if panel is None:
        await state.clear()
        await message.answer(texts.NOT_LINKED_RETRY, reply_markup=await menu_kb_for(message.chat.id))
        return
    await state.set_state(SubPanel.traffic)
    await message.answer(
        texts.ASK_SUBPANEL_TRAFFIC.format(
            source=data["source"], remaining_gb=bytes_to_gb(panel.get("traffic"))
        ),
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(SubPanel.traffic, ~F.text.in_(ALL_MENU_TEXTS))
async def got_traffic(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    try:
        traffic = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        traffic = 0
    if not traffic > 0 or traffic != traffic or traffic == float("inf"):
        await message.answer(texts.INVALID_AMOUNT_GB)
        return

    data = await state.get_data()
    source = data["source"]
    await message.answer(texts.CREATING_ADMIN)
    try:
        result = await nexra_panel.create_sub_admin(
            telegram_id=user_id,
            source_username=source,
            username=data["new_username"],
            password=data["new_password"],
            traffic_gb=traffic,
            white_label=bool(data.get("white_label")),
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

    await state.clear()
    expiry = result.get("expiry_date")
    expiry_line = texts.CREATE_ADMIN_EXPIRY_LINE.format(expiry=expiry[:10]) if expiry else ""
    if result.get("white_label"):
        summary = texts.SUBPANEL_SUCCESS_PLAIN.format(
            username=data["new_username"],
            password=data["new_password"],
            traffic_gb=traffic,
            panel_url=texts.PANEL_URL_WHITE_LABEL,
            expiry_line=expiry_line,
        )
    else:
        summary = texts.CREATE_ADMIN_SUCCESS.format(
            username=data["new_username"],
            password=data["new_password"],
            traffic_gb=traffic,
            panel_url=settings.panel_login_link,
            alarm_bot=settings.alarm_bot,
            manager_bot=settings.manager_bot,
            expiry_line=expiry_line,
        )
    # Alone, so it can be forwarded to the colleague as it is.
    await message.answer(summary)
    await message.answer(
        texts.SUBPANEL_CREATED_NOTE.format(
            username=data["new_username"],
            traffic_gb=traffic,
            source=source,
            remaining_gb=bytes_to_gb(result.get("source_traffic_bytes")),
        ),
        reply_markup=await menu_kb_for(user_id),
    )


async def _explain_failure(
    message: Message, state: FSMContext, exc: SubPanelError, source: str
) -> None:
    """Ask again for what can be fixed by typing something else; end the flow
    for everything that can't."""
    if exc.status == 409 and "already exists" in exc.message:
        await state.set_state(SubPanel.username)
        await message.answer(texts.SUBPANEL_USERNAME_TAKEN, reply_markup=keyboards.cancel_kb())
        return
    if exc.status == 409 and "left on this panel" in exc.message:
        try:
            panel = await _source_panel(message.from_user.id, source)
        except NexraPanelError:
            panel = None
        await message.answer(
            texts.SUBPANEL_TRAFFIC_TOO_HIGH.format(
                source=source, remaining_gb=bytes_to_gb((panel or {}).get("traffic"))
            ),
            reply_markup=keyboards.cancel_kb(),
        )
        return

    await state.clear()
    menu = await menu_kb_for(message.from_user.id)
    if exc.status == 403:
        await message.answer(texts.SUBPANEL_SOURCE_LOCKED.format(source=source), reply_markup=menu)
        return
    await message.answer(texts.SUBPANEL_FAILED.format(error=exc.message), reply_markup=menu)
