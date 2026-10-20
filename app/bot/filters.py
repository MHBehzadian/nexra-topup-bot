"""Shared aiogram filters."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from . import customize
from ..config import settings


class SuperadminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return user is not None and user.id in settings.superadmin_id_list


class Label(BaseFilter):
    """A tap on one of these reply buttons, given by their names in texts.

    Compared at the moment of the tap rather than when the handler is
    registered, since a label can be renamed from the Nexra panel — and the
    default label still counts, because a keyboard sent before the change keeps
    showing it until the next menu replaces it.
    """

    def __init__(self, *names: str) -> None:
        self.names = names

    async def __call__(self, message: Message) -> bool:
        return message.text is not None and message.text in customize.labels_for(*self.names)
