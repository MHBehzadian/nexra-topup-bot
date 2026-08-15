"""/start: superadmin menu, linkage check, main menu, and a one-time heads-up
to every superadmin the first time a given Telegram user ever starts the bot."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from .. import keyboards, texts
from ... import db
from ...config import settings
from ...services.nexra_panel import nexra_panel
from ...units import bytes_to_gb

router = Router(name="start")


async def _notify_superadmins_of_new_user(bot: Bot, message: Message, admin: dict | None) -> None:
    user = message.from_user
    username = f"@{user.username}" if user.username else "—"
    if admin:
        text = texts.NEW_START_NOTIFICATION_LINKED.format(
            full_name=user.full_name,
            username=username,
            telegram_id=user.id,
            admin_username=admin["username"],
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

    admin = await nexra_panel.get_admin(message.from_user.id)
    if is_new_user:
        await _notify_superadmins_of_new_user(bot, message, admin)

    if admin is None:
        await message.answer(
            texts.START_UNLINKED.format(telegram_id=message.from_user.id),
            reply_markup=keyboards.unlinked_menu_kb(),
        )
        return

    await message.answer(
        texts.START_LINKED.format(
            username=admin["username"],
            remaining_gb=bytes_to_gb(admin.get("traffic")),
            initial_gb=bytes_to_gb(admin.get("initial_traffic")),
        ),
        reply_markup=keyboards.main_menu_kb(),
    )


@router.message(F.text == texts.BTN_BALANCE)
async def check_balance(message: Message) -> None:
    admin = await nexra_panel.get_admin(message.from_user.id)
    if admin is None:
        await message.answer(texts.NOT_LINKED_RETRY)
        return
    await message.answer(
        texts.BALANCE_TEXT.format(
            remaining_gb=bytes_to_gb(admin.get("traffic")),
            initial_gb=bytes_to_gb(admin.get("initial_traffic")),
        )
    )


@router.message(F.text == texts.BTN_CREATE_PANEL)
async def create_panel_stub(message: Message) -> None:
    await message.answer(texts.CREATE_PANEL_SOON)


@router.callback_query(F.data == "fj_check")
async def recheck_join(call: CallbackQuery) -> None:
    # ForceJoinMiddleware only lets this callback through once membership is
    # confirmed (or the gate is off), so reaching this handler already means OK.
    await call.answer(texts.FORCE_JOIN_CONFIRMED, show_alert=True)
