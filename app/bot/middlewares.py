"""Bot middlewares."""

from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery
from aiogram.types import User as TgUser

from .. import db
from ..config import settings
from . import keyboards, texts

_MEMBER_OK = {"member", "administrator", "creator"}


class ForceJoinMiddleware(BaseMiddleware):
    """If force-join is turned on and a channel is configured (both set by the
    superadmin from inside the bot), users must join that channel before using
    the bot. Superadmins bypass. If membership can't be checked (e.g. the bot
    isn't an admin of the channel), users are let through rather than locked out.
    """

    async def __call__(self, handler, event, data):
        tg_user: TgUser | None = data.get("event_from_user")
        bot = data.get("bot")
        if tg_user is None or tg_user.id in settings.superadmin_id_list:
            return await handler(event, data)

        enabled = db.get_setting("force_join_enabled") == "1"
        channel = db.get_setting("force_join_channel")
        if not enabled or not channel:
            return await handler(event, data)

        try:
            member = await bot.get_chat_member(channel, tg_user.id)
            ok = member.status in _MEMBER_OK
        except Exception:
            ok = True

        if ok:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer(texts.FORCE_JOIN_TEXT, show_alert=True)
        await bot.send_message(
            tg_user.id, texts.FORCE_JOIN_TEXT, reply_markup=keyboards.force_join_kb(channel)
        )
        return None
