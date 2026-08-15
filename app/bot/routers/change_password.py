"""Admin-facing: change the Marzban password Nexra Panel uses to represent them.

The Nexra-side copy (admins.marzban_password) is updated immediately via the panel
API. The real Marzban admin account is NOT touched automatically — the superadmin
gets notified with the new value and mirrors it inside Marzban by hand.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import texts
from ..states import ChangePassword
from ...config import settings
from ...services.nexra_panel import NexraPanelError, nexra_panel

router = Router(name="change_password")


@router.message(F.text == texts.BTN_CHANGE_PASSWORD)
async def start_change_password(message: Message, state: FSMContext) -> None:
    admin = await nexra_panel.get_admin(message.from_user.id)
    if admin is None:
        await message.answer(texts.NOT_LINKED_RETRY)
        return
    await state.set_state(ChangePassword.new_password)
    await message.answer(texts.ASK_NEW_PASSWORD)


@router.message(ChangePassword.new_password)
async def finish_change_password(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    new_password = (message.text or "").strip()
    if not new_password:
        await message.answer(texts.INVALID_PASSWORD)
        return

    admin = await nexra_panel.get_admin(message.from_user.id)
    if admin is None:
        await message.answer(texts.NOT_LINKED_RETRY)
        return

    try:
        await nexra_panel.change_password(message.from_user.id, new_password)
    except NexraPanelError as exc:
        await message.answer(f"خطا در ثبت تغییر رمز: {exc}")
        return

    await message.answer(texts.PASSWORD_CHANGE_SUBMITTED)

    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(
                superadmin_id,
                texts.PASSWORD_CHANGE_NOTIFY_SUPERADMIN.format(
                    username=admin["username"],
                    telegram_id=message.from_user.id,
                    new_password=new_password,
                ),
            )
        except Exception:
            continue
