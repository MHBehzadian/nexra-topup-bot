"""Tutorials: superadmin uploads them (text/photo/video/document), any linked
admin can browse and open them. Media is kept by Telegram file_id — no local
storage needed, since a bot can resend a file_id it has already seen at any
time in the future."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards, texts
from ..filters import SuperadminFilter
from ..states import AddTutorial
from ... import db

router = Router(name="tutorials")


@router.message(F.text == texts.BTN_TUTORIALS)
async def list_tutorials(message: Message) -> None:
    tutorials = db.list_tutorials()
    if not tutorials:
        await message.answer(texts.NO_TUTORIALS)
        return
    await message.answer(texts.TUTORIALS_LIST_TEXT, reply_markup=keyboards.tutorials_list_kb(tutorials))


@router.callback_query(F.data.startswith("tutorial:"))
async def send_tutorial(call: CallbackQuery, bot: Bot) -> None:
    tutorial_id = int(call.data.split(":")[1])
    tutorial = db.get_tutorial(tutorial_id)
    if tutorial is None:
        await call.answer(texts.NOT_FOUND, show_alert=True)
        return

    await call.answer()
    chat_id = call.from_user.id
    caption = tutorial.text or None
    if tutorial.content_type == "video":
        await bot.send_video(chat_id, tutorial.file_id, caption=caption)
    elif tutorial.content_type == "photo":
        await bot.send_photo(chat_id, tutorial.file_id, caption=caption)
    elif tutorial.content_type == "document":
        await bot.send_document(chat_id, tutorial.file_id, caption=caption)
    else:
        await bot.send_message(chat_id, tutorial.text or "")


@router.message(F.text == texts.BTN_ADD_TUTORIAL, SuperadminFilter())
async def start_add_tutorial(message: Message, state: FSMContext) -> None:
    await state.set_state(AddTutorial.title)
    await message.answer(texts.ASK_TUTORIAL_TITLE)


@router.message(AddTutorial.title, SuperadminFilter())
async def get_tutorial_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer(texts.ASK_TUTORIAL_TITLE)
        return
    await state.update_data(title=title)
    await state.set_state(AddTutorial.content)
    await message.answer(texts.ASK_TUTORIAL_CONTENT)


@router.message(AddTutorial.content, SuperadminFilter())
async def get_tutorial_content(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    title = data["title"]

    if message.video:
        content_type, file_id, text = "video", message.video.file_id, message.caption
    elif message.photo:
        content_type, file_id, text = "photo", message.photo[-1].file_id, message.caption
    elif message.document:
        content_type, file_id, text = "document", message.document.file_id, message.caption
    elif message.text:
        content_type, file_id, text = "text", None, message.text
    else:
        await message.answer(texts.INVALID_TUTORIAL_CONTENT)
        return

    await state.clear()
    db.add_tutorial(title=title, content_type=content_type, text=text, file_id=file_id)
    await message.answer(texts.TUTORIAL_ADDED_CONFIRM.format(title=title))
