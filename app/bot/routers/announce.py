"""A post with a button, sent to the bot's users, to a channel, or both.

Not tied to the festival: any text, photo, video or GIF, with an optional
button under it. The button is a t.me link back into the bot with a /start
payload, so it works the same from a channel as from the bot, and tapping it
restarts the bot for them — their menu is rebuilt, which is the only way a new
reply button (the festival's) reaches a keyboard they already have.

The draft is sent back to the superadmin first, exactly as it will go out: that
is the test send, and it can be repeated before sending it anywhere.
"""

from __future__ import annotations

import asyncio
import re
import secrets
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards, texts
from ..filters import Label, SuperadminFilter
from ..nav import ALL_MENU_TEXTS, superadmin_kb
from ..states import Announce
from ... import db

router = Router(name="announce")
router.message.filter(SuperadminFilter())
router.callback_query.filter(SuperadminFilter())

# /start payload of every announcement button: start.py opens the festival for
# it while one is running, and otherwise just the menu.
START_PAYLOAD = "go"

_CHANNEL_KEY = "announce_channel"
_CHANNEL_RE = re.compile(r"^(@[A-Za-z0-9_]{4,32}|-100\d{5,20})$")

# In memory: a draft is minutes old by the time it is sent, and losing one to a
# restart costs a re-send of the post, nothing more.
_drafts: dict[str, dict] = {}


def _channel() -> str | None:
    return db.get_setting(_CHANNEL_KEY) or db.get_setting("force_join_channel")


async def _markup(bot: Bot, draft: dict):
    if draft["label"] is None:
        return None
    me = await bot.me()
    url = f"https://t.me/{me.username}?start={START_PAYLOAD}"
    return keyboards.announce_post_kb(url, draft["label"], draft["emoji"])


async def _copy(bot: Bot, chat_id: int | str, draft: dict) -> None:
    await bot.copy_message(
        chat_id,
        from_chat_id=draft["chat_id"],
        message_id=draft["message_id"],
        reply_markup=await _markup(bot, draft),
    )


async def _preview(bot: Bot, chat_id: int, draft_id: str) -> None:
    await _copy(bot, chat_id, _drafts[draft_id])
    await bot.send_message(
        chat_id, texts.ANNOUNCE_PREVIEW, reply_markup=keyboards.announce_actions_kb(draft_id)
    )


@router.message(Label("BTN_ANNOUNCE"))
async def start_announce(message: Message, state: FSMContext) -> None:
    await state.set_state(Announce.content)
    await message.answer(texts.ASK_ANNOUNCE_CONTENT, reply_markup=keyboards.cancel_kb())


@router.message(Announce.content, ~F.text.in_(ALL_MENU_TEXTS))
async def got_content(message: Message, state: FSMContext) -> None:
    if not (
        message.text or message.photo or message.video or message.animation or message.document
    ):
        await message.answer(texts.ANNOUNCE_UNSUPPORTED)
        return
    await state.clear()
    draft_id = secrets.token_hex(4)
    _drafts[draft_id] = {
        "chat_id": message.chat.id,
        "message_id": message.message_id,
        "label": None,
        "emoji": None,
        "sent": set(),
    }
    await message.answer(texts.ANNOUNCE_GOT, reply_markup=superadmin_kb(message.from_user.id))
    await message.answer(
        texts.ASK_ANNOUNCE_BUTTON, reply_markup=keyboards.announce_button_kb(draft_id)
    )


@router.callback_query(F.data.startswith("ann_btn:"))
async def chose_button(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    _, kind, draft_id = call.data.split(":", 2)
    draft = _drafts.get(draft_id)
    if draft is None:
        await call.answer(texts.ANNOUNCE_EXPIRED, show_alert=True)
        return
    await call.answer()
    if kind == "custom":
        await state.set_state(Announce.label)
        await state.update_data(draft_id=draft_id)
        await call.message.answer(texts.ASK_ANNOUNCE_LABEL, reply_markup=keyboards.cancel_kb())
        return
    if kind == "preset":
        draft["label"], draft["emoji"] = texts.BTN_ANNOUNCE_FESTIVAL, "preset"
    else:
        draft["label"], draft["emoji"] = None, None
    await call.message.edit_reply_markup(reply_markup=None)
    await _preview(bot, call.message.chat.id, draft_id)


def _split_icon(message: Message) -> tuple[str, str | None]:
    """The label, and the premium emoji it starts with as the button's icon.

    Entity offsets count UTF-16 units, so the cut is made in UTF-16 too: an
    emoji is two of them, and slicing the str would cut in the wrong place.
    """
    text = message.text or ""
    for entity in message.entities or []:
        if entity.type == "custom_emoji" and entity.offset == 0:
            units = text.encode("utf-16-le")
            rest = units[entity.length * 2:].decode("utf-16-le")
            return rest.strip(), entity.custom_emoji_id
    return text.strip(), None


@router.message(Announce.label, ~F.text.in_(ALL_MENU_TEXTS))
async def got_label(message: Message, state: FSMContext, bot: Bot) -> None:
    draft_id = (await state.get_data()).get("draft_id")
    draft = _drafts.get(draft_id or "")
    if draft is None:
        await state.clear()
        await message.answer(texts.ANNOUNCE_EXPIRED, reply_markup=superadmin_kb(message.from_user.id))
        return
    label, emoji = _split_icon(message)
    if not label or len(label) > 64:
        await message.answer(texts.ANNOUNCE_LABEL_INVALID)
        return
    await state.clear()
    draft["label"], draft["emoji"] = label, emoji
    await message.answer(texts.ANNOUNCE_GOT, reply_markup=superadmin_kb(message.from_user.id))
    await _preview(bot, message.chat.id, draft_id)


def _draft_from(call: CallbackQuery) -> tuple[str, dict | None]:
    draft_id = call.data.rsplit(":", 1)[1]
    return draft_id, _drafts.get(draft_id)


@router.callback_query(F.data.startswith("ann:test:"))
async def test_again(call: CallbackQuery, bot: Bot) -> None:
    draft_id, draft = _draft_from(call)
    if draft is None:
        await call.answer(texts.ANNOUNCE_EXPIRED, show_alert=True)
        return
    await call.answer()
    await _preview(bot, call.message.chat.id, draft_id)


@router.callback_query(F.data.startswith("ann:drop:"))
async def discard(call: CallbackQuery) -> None:
    draft_id, _ = _draft_from(call)
    _drafts.pop(draft_id, None)
    await call.answer()
    await call.message.edit_text(texts.ANNOUNCE_DISCARDED)


@router.callback_query(F.data.startswith("ann:back:"))
async def back_to_actions(call: CallbackQuery) -> None:
    draft_id, draft = _draft_from(call)
    if draft is None:
        await call.answer(texts.ANNOUNCE_EXPIRED, show_alert=True)
        return
    await call.answer()
    await call.message.edit_text(
        texts.ANNOUNCE_PREVIEW, reply_markup=keyboards.announce_actions_kb(draft_id)
    )


# ---- to the bot's users ------------------------------------------------------


@router.callback_query(F.data.startswith("ann:bot:"))
async def confirm_bot(call: CallbackQuery) -> None:
    draft_id, draft = _draft_from(call)
    if draft is None:
        await call.answer(texts.ANNOUNCE_EXPIRED, show_alert=True)
        return
    if "bot" in draft["sent"]:
        await call.answer(texts.ANNOUNCE_ALREADY_SENT, show_alert=True)
        return
    await call.answer()
    await call.message.edit_text(
        texts.ANNOUNCE_CONFIRM_BOT.format(count=len(db.list_known_users())),
        reply_markup=keyboards.announce_confirm_kb(draft_id, "bot"),
    )


@router.callback_query(F.data.startswith("ann:okbot:"))
async def send_to_bot(call: CallbackQuery, bot: Bot) -> None:
    draft_id, draft = _draft_from(call)
    if draft is None:
        await call.answer(texts.ANNOUNCE_EXPIRED, show_alert=True)
        return
    if "bot" in draft["sent"]:
        await call.answer(texts.ANNOUNCE_ALREADY_SENT, show_alert=True)
        return
    # Marked before the first message goes, so a second tap can't send it twice.
    draft["sent"].add("bot")
    await call.answer()
    await call.message.edit_text(texts.ANNOUNCE_SENDING)

    sent = failed = 0
    for telegram_id in db.list_known_users():
        try:
            await _copy(bot, telegram_id, draft)
            sent += 1
        except Exception:
            failed += 1
        # About 30 messages a second is Telegram's limit.
        await asyncio.sleep(0.05)

    await call.message.edit_text(
        texts.ANNOUNCE_BOT_DONE.format(sent=sent, failed=failed),
        reply_markup=keyboards.announce_actions_kb(draft_id),
    )


# ---- to the channel ----------------------------------------------------------


async def _confirm_channel(message: Message, draft_id: str, edit: bool) -> None:
    text = texts.ANNOUNCE_CONFIRM_CHANNEL.format(channel=escape(_channel() or ""))
    markup = keyboards.announce_confirm_kb(draft_id, "ch")
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("ann:ch:"))
async def confirm_channel(call: CallbackQuery, state: FSMContext) -> None:
    draft_id, draft = _draft_from(call)
    if draft is None:
        await call.answer(texts.ANNOUNCE_EXPIRED, show_alert=True)
        return
    if "ch" in draft["sent"]:
        await call.answer(texts.ANNOUNCE_ALREADY_SENT, show_alert=True)
        return
    await call.answer()
    if not _channel():
        await state.set_state(Announce.channel)
        await state.update_data(draft_id=draft_id)
        await call.message.answer(texts.ASK_ANNOUNCE_CHANNEL, reply_markup=keyboards.cancel_kb())
        return
    await _confirm_channel(call.message, draft_id, edit=True)


@router.callback_query(F.data.startswith("ann:setch:"))
async def change_channel(call: CallbackQuery, state: FSMContext) -> None:
    draft_id, draft = _draft_from(call)
    if draft is None:
        await call.answer(texts.ANNOUNCE_EXPIRED, show_alert=True)
        return
    await call.answer()
    await state.set_state(Announce.channel)
    await state.update_data(draft_id=draft_id)
    await call.message.answer(texts.ASK_ANNOUNCE_CHANNEL, reply_markup=keyboards.cancel_kb())


@router.message(Announce.channel, ~F.text.in_(ALL_MENU_TEXTS))
async def got_channel(message: Message, state: FSMContext) -> None:
    channel = (message.text or "").strip()
    if not _CHANNEL_RE.match(channel):
        await message.answer(texts.INVALID_CHANNEL)
        return
    draft_id = (await state.get_data()).get("draft_id") or ""
    await state.clear()
    db.set_setting(_CHANNEL_KEY, channel)
    await message.answer(texts.ANNOUNCE_GOT, reply_markup=superadmin_kb(message.from_user.id))
    if draft_id not in _drafts:
        await message.answer(texts.ANNOUNCE_EXPIRED)
        return
    await _confirm_channel(message, draft_id, edit=False)


@router.callback_query(F.data.startswith("ann:okch:"))
async def send_to_channel(call: CallbackQuery, bot: Bot) -> None:
    draft_id, draft = _draft_from(call)
    if draft is None:
        await call.answer(texts.ANNOUNCE_EXPIRED, show_alert=True)
        return
    if "ch" in draft["sent"]:
        await call.answer(texts.ANNOUNCE_ALREADY_SENT, show_alert=True)
        return
    channel = _channel()
    await call.answer()
    try:
        await _copy(bot, channel, draft)
    except Exception as exc:
        await call.message.edit_text(
            texts.ANNOUNCE_CHANNEL_FAILED.format(channel=escape(channel), error=escape(str(exc))),
            reply_markup=keyboards.announce_actions_kb(draft_id),
        )
        return
    draft["sent"].add("ch")
    await call.message.edit_text(
        texts.ANNOUNCE_CHANNEL_DONE.format(channel=escape(channel)),
        reply_markup=keyboards.announce_actions_kb(draft_id),
    )
