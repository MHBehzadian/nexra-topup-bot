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
from ..nav import ALL_MENU_TEXTS
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

    # Channel-backed tutorial: forward the original post, so editing it in the
    # channel updates what everyone receives from then on.
    if tutorial.source_chat_id and tutorial.source_message_id:
        try:
            await bot.forward_message(
                chat_id,
                from_chat_id=tutorial.source_chat_id,
                message_id=tutorial.source_message_id,
            )
        except Exception:
            # Channels with forwarding disabled still allow a plain copy.
            try:
                await bot.copy_message(
                    chat_id,
                    from_chat_id=tutorial.source_chat_id,
                    message_id=tutorial.source_message_id,
                )
            except Exception:
                await bot.send_message(chat_id, texts.TUTORIAL_UNAVAILABLE)
        return

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
    await message.answer(texts.ASK_TUTORIAL_TITLE, reply_markup=keyboards.cancel_kb())


@router.message(AddTutorial.title, SuperadminFilter(), ~F.text.in_(ALL_MENU_TEXTS))
async def get_tutorial_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer(texts.ASK_TUTORIAL_TITLE, reply_markup=keyboards.cancel_kb())
        return
    await state.update_data(title=title)
    await state.set_state(AddTutorial.content)
    await message.answer(texts.ASK_TUTORIAL_CONTENT, reply_markup=keyboards.cancel_kb())


@router.message(AddTutorial.content, SuperadminFilter(), ~F.text.in_(ALL_MENU_TEXTS))
async def get_tutorial_content(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    title = data["title"]

    # Forwarded from a channel: remember where it came from rather than copying
    # the content, so the channel stays the single source of truth.
    origin_chat = message.forward_from_chat
    if origin_chat is not None and message.forward_from_message_id:
        await state.clear()
        db.add_tutorial(
            title=title,
            content_type="forward",
            text=None,
            file_id=None,
            source_chat_id=origin_chat.id,
            source_message_id=message.forward_from_message_id,
        )
        await message.answer(
            texts.TUTORIAL_ADDED_CONFIRM.format(title=title),
            reply_markup=keyboards.superadmin_menu_kb(),
        )
        return

    if message.video:
        content_type, file_id, text = "video", message.video.file_id, message.caption
    elif message.photo:
        content_type, file_id, text = "photo", message.photo[-1].file_id, message.caption
    elif message.document:
        content_type, file_id, text = "document", message.document.file_id, message.caption
    elif message.text:
        content_type, file_id, text = "text", None, message.text
    else:
        await message.answer(texts.INVALID_TUTORIAL_CONTENT, reply_markup=keyboards.cancel_kb())
        return

    await state.clear()
    db.add_tutorial(title=title, content_type=content_type, text=text, file_id=file_id)
    await message.answer(
        texts.TUTORIAL_ADDED_CONFIRM.format(title=title), reply_markup=keyboards.superadmin_menu_kb()
    )
