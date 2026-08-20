"""/start: superadmin menu, linkage check, main menu, the admin's panel list,
and a one-time heads-up to every superadmin the first time a given Telegram
user ever starts the bot."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards, texts
from ..nav import cancel_and_show_menu
from ..panels import format_panel_line, safe_get_admins
from ... import db
from ...config import settings
from ...units import bytes_to_gb

router = Router(name="start")


async def _notify_superadmins_of_new_user(bot: Bot, message: Message, admins: list[dict]) -> None:
    user = message.from_user
    username = f"@{user.username}" if user.username else "—"
    if admins:
        text = texts.NEW_START_NOTIFICATION_LINKED.format(
            full_name=user.full_name,
            username=username,
            telegram_id=user.id,
            admin_username="، ".join(a["username"] for a in admins),
        )
    else:
        text = texts.NEW_START_NOTIFICATION_UNLINKED.format(
            full_name=user.full_name, username=username, telegram_id=user.id
        )
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(
                superadmin_id, text, reply_markup=keyboards.message_user_kb(user.id)
            )
        except Exception:
            continue


@router.message(CommandStart())
async def start(message: Message, bot: Bot) -> None:
    is_new_user = not db.user_exists(message.from_user.id)
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    if message.from_user.id in settings.superadmin_id_list:
        await message.answer(texts.SUPERADMIN_WELCOME, reply_markup=keyboards.superadmin_menu_kb())
        return

    admins = await safe_get_admins(message)
    if admins is None:
        return
    if is_new_user:
        await _notify_superadmins_of_new_user(bot, message, admins)

    if not admins:
        await message.answer(
            texts.START_UNLINKED.format(telegram_id=message.from_user.id),
            reply_markup=keyboards.unlinked_menu_kb(),
        )
        return

    total_remaining = sum(bytes_to_gb(a.get("traffic")) for a in admins)
    total_initial = sum(bytes_to_gb(a.get("initial_traffic")) for a in admins)
    await message.answer(
        texts.START_LINKED.format(
            username=admins[0]["username"] if len(admins) == 1 else message.from_user.full_name,
            remaining_gb=total_remaining,
            initial_gb=total_initial,
        ),
        reply_markup=keyboards.main_menu_kb(),
    )


@router.message(F.text.in_({texts.BTN_MY_PANELS, texts.BTN_BALANCE}))
async def my_panels(message: Message) -> None:
    admins = await safe_get_admins(message)
    if admins is None:
        return
    if not admins:
        await message.answer(texts.NO_PANELS)
        return
    text = texts.PANELS_LIST_HEADER + "".join(format_panel_line(a) for a in admins)
    await message.answer(text)


@router.message(F.text == texts.BTN_CREATE_PANEL)
async def create_panel_stub(message: Message) -> None:
    await message.answer(texts.CREATE_PANEL_SOON)


@router.message(F.text == texts.BTN_CANCEL)
async def cancel(message: Message, state: FSMContext) -> None:
    await cancel_and_show_menu(message, state)


@router.callback_query(F.data == "fj_check")
async def recheck_join(call: CallbackQuery) -> None:
    # ForceJoinMiddleware only lets this callback through once membership is
    # confirmed (or the gate is off), so reaching this handler already means OK.
    await call.answer(texts.FORCE_JOIN_CONFIRMED, show_alert=True)
