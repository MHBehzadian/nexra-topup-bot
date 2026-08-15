"""/start: linkage check, main menu, and a heads-up to every superadmin."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from .. import keyboards, texts
from ... import db
from ...config import settings
from ...services.nexra_panel import nexra_panel
from ...units import bytes_to_gb

router = Router(name="start")


async def _notify_superadmins_of_start(bot: Bot, message: Message, admin: dict | None) -> None:
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
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    admin = await nexra_panel.get_admin(message.from_user.id)
    await _notify_superadmins_of_start(bot, message, admin)

    if admin is None:
        await message.answer(
            texts.START_UNLINKED.format(telegram_id=message.from_user.id),
            reply_markup=keyboards.unlinked_menu_kb(),
        )
        return

    balance_gb = bytes_to_gb(admin.get("traffic"))
    await message.answer(
        texts.START_LINKED.format(username=admin["username"], balance_gb=balance_gb),
        reply_markup=keyboards.main_menu_kb(),
    )


@router.message(F.text == texts.BTN_BALANCE)
async def check_balance(message: Message) -> None:
    admin = await nexra_panel.get_admin(message.from_user.id)
    if admin is None:
        await message.answer(texts.NOT_LINKED_RETRY)
        return
    balance_gb = bytes_to_gb(admin.get("traffic"))
    await message.answer(f"موجودی فعلی: {balance_gb:.2f} گیگابایت")


@router.message(F.text == texts.BTN_CREATE_PANEL)
async def create_panel_stub(message: Message) -> None:
    await message.answer(texts.CREATE_PANEL_SOON)
