"""Admin-facing: request a change to the Marzban password Nexra Panel uses to
represent them.

Two-step by design: the Nexra-side copy (admins.marzban_password) is NOT
updated the moment the admin submits it. If it were, Nexra would immediately
start authenticating to the real Marzban API with a password Marzban doesn't
recognize yet, breaking that admin's user-management in Nexra until manually
fixed. Instead the superadmin is notified, changes it in real Marzban first,
and only then taps "Applied" — which is what actually updates Nexra's copy,
so the two are never out of sync.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import keyboards, texts
from ..states import ChangePassword
from ... import db
from ...config import settings
from ...services.nexra_panel import nexra_panel

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

    request_id = db.create_password_request(
        admin_telegram_id=message.from_user.id,
        admin_username=admin["username"],
        new_password=new_password,
    )

    await message.answer(texts.PASSWORD_CHANGE_SUBMITTED)

    text = texts.PASSWORD_CHANGE_NOTIFY_SUPERADMIN.format(
        username=admin["username"],
        telegram_id=message.from_user.id,
        new_password=new_password,
    )
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(
                superadmin_id, text, reply_markup=keyboards.password_applied_kb(request_id)
            )
        except Exception:
            continue
