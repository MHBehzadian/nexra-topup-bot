"""Picking which server an action runs on.

Every SSH action is registered here by name. With one server it simply runs
there; with more, the superadmin taps the server first (callback srv:<action>:<id>).
"""

from __future__ import annotations

import html
import re
from typing import Awaitable, Callable

from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .. import db
from ..remote import Target

Action = Callable[[Message, "db.sqlite3.Row", FSMContext], Awaitable[None]]
ACTIONS: dict[str, Action] = {}

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def action(name: str):
    def register(fn: Action) -> Action:
        ACTIONS[name] = fn
        return fn

    return register


def target(row) -> Target:
    return Target.from_row(row)


def label(row) -> str:
    return f"{row['name']} ({row['host']})"


def clean(text: str, limit: int = 3500) -> str:
    """Remote output, safe inside <pre>: no colour codes, escaped, short enough."""
    text = ANSI.sub("", text or "").strip()
    if len(text) > limit:
        text = "…\n" + text[-limit:]
    return html.escape(text)


def no_servers_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ افزودن سرور", callback_data="srvadd")
    return kb.as_markup()


async def choose(message: Message, state: FSMContext, name: str) -> None:
    servers = db.list_servers()
    if not servers:
        await message.answer(
            "🖥 هنوز سروری اضافه نشده.\n"
            "اول سرور را با IP و رمز SSH اضافه کنید؛ ربات‌ها روی همان سرور ساخته و نگهداری می‌شوند.",
            reply_markup=no_servers_kb(),
        )
        return
    if len(servers) == 1:
        await ACTIONS[name](message, servers[0], state)
        return
    kb = InlineKeyboardBuilder()
    for row in servers:
        kb.button(text=label(row), callback_data=f"srv:{name}:{row['id']}")
    kb.adjust(1)
    await message.answer("روی کدام سرور؟", reply_markup=kb.as_markup())
