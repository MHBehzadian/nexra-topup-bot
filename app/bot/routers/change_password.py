"""Admin-facing: change the password Nexra Panel uses to represent them in Marzban.

The panel API now changes the password directly in Marzban itself (using its
stored sudo credentials) and mirrors it into Nexra's own copy in one atomic
call, so this is applied immediately in the common case. If that automatic
call fails for any reason (e.g. the panel's stored Marzban credentials aren't
a sudo admin, or Marzban is unreachable), we fall back to the manual two-step:
notify the superadmin with an "Applied" button so they can set it in Marzban
by hand and confirm — see routers/approval.py's confirm_password_applied.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import keyboards, texts
from ..states import ChangePassword
from ... import db
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

    request_id = db.create_password_request(
        admin_telegram_id=message.from_user.id,
        admin_username=admin["username"],
        new_password=new_password,
    )

    try:
        await nexra_panel.change_password(message.from_user.id, new_password)
    except NexraPanelError as exc:
        # Automatic apply failed — fall back to the manual two-step.
        await message.answer(texts.PASSWORD_CHANGE_SUBMITTED)
        text = texts.PASSWORD_CHANGE_AUTO_FAILED_SUPERADMIN.format(
            username=admin["username"],
            telegram_id=message.from_user.id,
            new_password=new_password,
            error=exc,
        )
        for superadmin_id in settings.superadmin_id_list:
            try:
                await bot.send_message(
                    superadmin_id, text, reply_markup=keyboards.password_applied_kb(request_id)
                )
            except Exception:
                continue
        return

    db.mark_password_applied(request_id, applied_by=None)
    await message.answer(texts.PASSWORD_APPLIED_ADMIN)

    text = texts.PASSWORD_CHANGE_NOTIFY_SUPERADMIN_AUTO.format(
        username=admin["username"], telegram_id=message.from_user.id, new_password=new_password
    )
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(superadmin_id, text)
        except Exception:
            continue
