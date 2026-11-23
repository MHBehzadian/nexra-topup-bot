"""The Black Friday festival: a gift code for whoever enters it first, and a
1000 GB package that comes with a shrinking gift, five times per person.

Only panel owners get here — the button is on their menu alone, and every step
checks again, since a callback or a /start link can arrive from anyone.
"""

from __future__ import annotations

import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from .. import auto_approve, festival, keyboards, texts
from ..bills import open_bills
from ..filters import Label, SuperadminFilter
from ..nav import ALL_MENU_TEXTS, menu_kb_for, superadmin_kb
from ..states import FestivalBuy, FestivalCode, GiftCodeAdmin
from ... import db
from ...config import settings
from ...services.nexra_panel import NexraPanelError, nexra_panel
from ...units import bytes_to_gb

router = Router(name="festival")

_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I to misread
_CODE_RE = re.compile(r"^[A-Z0-9_-]{3,32}$")
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _ordinal(n: int) -> str:
    if 1 <= n <= len(texts.FESTIVAL_PLACES):
        return texts.FESTIVAL_PLACES[n - 1]
    return texts.FESTIVAL_PLACE_N.format(n=str(n).translate(festival._FA))


def normalize_code(raw: str | None) -> str:
    return re.sub(r"\s+", "", (raw or "").translate(_FA_DIGITS)).upper()


async def _panels(user_id: int, message: Message) -> list[dict] | None:
    """Their panels; None (and they are told why) if the panel can't be reached
    or they own none — the festival is for panel owners only."""
    try:
        admins = await nexra_panel.get_admins(user_id)
    except Exception:
        await message.answer(texts.PANEL_UNREACHABLE)
        return None
    if not admins:
        await message.answer(texts.FESTIVAL_PANELS_ONLY, reply_markup=await menu_kb_for(user_id))
        return None
    return admins


async def _still_live(user_id: int, message: Message) -> bool:
    if festival.is_live():
        return True
    await message.answer(texts.FESTIVAL_OVER, reply_markup=await menu_kb_for(user_id))
    return False


async def show_festival(message: Message, user_id: int) -> None:
    """The festival's two doors. Also where a /start link from an announcement
    lands while the festival runs."""
    await festival.refresh()
    if not await _still_live(user_id, message):
        return
    if await _panels(user_id, message) is None:
        return
    await message.answer(
        texts.FESTIVAL_MENU.format(**festival.remaining()),
        reply_markup=keyboards.festival_menu_kb(),
    )


@router.message(Label("BTN_FESTIVAL"))
async def open_festival(message: Message, state: FSMContext) -> None:
    await state.clear()
    await show_festival(message, message.from_user.id)


# ------------------------------------------------------------------ gift code


async def _credit_code(
    message: Message, user_id: int, name: str, code: dict, username: str, bot: Bot
) -> None:
    # Taken first, credited second: a double tap finds the panel already set and
    # stops here, rather than crediting the gift twice.
    if not db.set_gift_code_panel(code["code"], username):
        await message.answer(texts.FESTIVAL_CODE_ALREADY)
        return
    try:
        result = await nexra_panel.topup(user_id, code["gb"], username=username)
    except NexraPanelError as exc:
        db.set_gift_code_panel(code["code"], None)
        await message.answer(texts.FESTIVAL_CODE_FAILED.format(error=escape(str(exc))))
        return

    db.clear_warning_bucket(username)
    db.record_sale(telegram_id=user_id, username=username, gb=code["gb"], amount=0, method="gift")
    await message.answer(
        texts.FESTIVAL_CODE_CREDITED.format(
            gb=code["gb"], username=escape(username), new_gb=bytes_to_gb(result.get("new_traffic_bytes"))
        ),
        reply_markup=await menu_kb_for(user_id),
    )
    # When they entered it (the moment it became theirs), not when the panel
    # was picked: that is what "first" was decided by.
    entered = festival._parse(code.get("redeemed_at")) or datetime.now(timezone.utc)
    entered = entered.astimezone(festival.TEHRAN)
    notice = texts.FESTIVAL_CODE_WON_NOTIFY.format(
        name=escape(name),
        time=entered.strftime("%H:%M:%S").translate(festival._FA),
        date=entered.strftime("%Y/%m/%d").translate(festival._FA),
        gb=code["gb"],
    )
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(superadmin_id, notice)
        except Exception:
            continue


async def _place_code(message: Message, user_id: int, name: str, code: dict, bot: Bot) -> None:
    """A won code goes to their only panel, or they pick one."""
    admins = await _panels(user_id, message)
    if admins is None:
        return
    if len(admins) == 1:
        await _credit_code(message, user_id, name, code, admins[0]["username"], bot)
        return
    # Several panels: the good news now, the full message once one is picked.
    await message.answer(texts.FESTIVAL_CODE_WON.format(gb=code["gb"]))
    await message.answer(
        texts.FESTIVAL_CODE_PICK_PANEL, reply_markup=keyboards.panel_picker_kb(admins, "festgift")
    )


@router.callback_query(F.data == "fest:code")
async def ask_code(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await call.answer()
    user_id = call.from_user.id
    if not await _still_live(user_id, call.message):
        return
    won = db.gift_code_won_by(user_id, festival.started_at())
    if won:
        # Won but never placed (closed the picker, or the panel was down): pick
        # up where they left off rather than lose the gift.
        if won["username"] is None:
            await _place_code(call.message, user_id, call.from_user.full_name, won, bot)
        else:
            await call.message.answer(texts.FESTIVAL_CODE_ALREADY)
        return
    if await _panels(user_id, call.message) is None:
        return
    await state.set_state(FestivalCode.code)
    await call.message.answer(texts.FESTIVAL_ASK_CODE, reply_markup=keyboards.cancel_kb())


@router.message(FestivalCode.code, ~F.text.in_(ALL_MENU_TEXTS))
async def enter_code(message: Message, state: FSMContext, bot: Bot) -> None:
    user_id = message.from_user.id
    code = normalize_code(message.text)
    if not festival.is_live():
        await state.clear()
        await message.answer(texts.FESTIVAL_OVER, reply_markup=await menu_kb_for(user_id))
        return
    if not _CODE_RE.match(code):
        await message.answer(texts.FESTIVAL_CODE_INVALID)
        return

    outcome = db.claim_gift_code(code, user_id, festival.started_at())
    if outcome == "invalid":
        # Stay in the state: a typo deserves another go without starting over.
        await message.answer(texts.FESTIVAL_CODE_INVALID)
        return
    await state.clear()
    if outcome == "taken":
        place = db.record_late_attempt(code, user_id)
        await message.answer(
            texts.FESTIVAL_CODE_TAKEN.format(place=_ordinal(place)),
            reply_markup=await menu_kb_for(user_id),
        )
        return
    if outcome == "already":
        await message.answer(texts.FESTIVAL_CODE_ALREADY, reply_markup=await menu_kb_for(user_id))
        return

    won = db.get_gift_code(code)
    if outcome == "mine" and won and won["username"]:
        await message.answer(texts.FESTIVAL_CODE_ALREADY, reply_markup=await menu_kb_for(user_id))
        return
    await _place_code(message, user_id, message.from_user.full_name, won, bot)


@router.callback_query(F.data.startswith("pick:festgift:"))
async def picked_gift_panel(call: CallbackQuery, bot: Bot) -> None:
    username = call.data.split(":", 2)[2]
    user_id = call.from_user.id
    won = db.gift_code_won_by(user_id, festival.started_at())
    if not won or won["username"] is not None:
        await call.answer(texts.FESTIVAL_CODE_ALREADY, show_alert=True)
        return
    try:
        admins = await nexra_panel.get_admins(user_id)
    except Exception:
        await call.answer(texts.PANEL_UNREACHABLE, show_alert=True)
        return
    if not any(a["username"] == username for a in admins):
        await call.answer(texts.NOT_LINKED_RETRY, show_alert=True)
        return
    await call.answer()
    await call.message.edit_reply_markup(reply_markup=None)
    await _credit_code(call.message, user_id, call.from_user.full_name, won, username, bot)


# ------------------------------------------------------------------ 1000 GB + gift


def _next_bonus(user_id: int) -> tuple[int | None, str | None]:
    """The gift on their next purchase, or why there is none (a text)."""
    approved, pending = festival.purchases(user_id)
    if pending:
        return None, texts.FESTIVAL_PENDING
    bonus = festival.bonus_for(approved)
    if bonus is None:
        return None, texts.FESTIVAL_LIMIT
    return bonus, None


def _package_price() -> int | None:
    raw = db.get_setting("price_per_gb")
    return round(festival.PACKAGE_GB * float(raw)) if raw else None


@router.callback_query(F.data == "fest:offer")
async def show_offer(call: CallbackQuery) -> None:
    await call.answer()
    user_id = call.from_user.id
    if not await _still_live(user_id, call.message):
        return
    if await _panels(user_id, call.message) is None:
        return
    bonus, why_not = _next_bonus(user_id)
    if why_not:
        await call.message.answer(why_not)
        return
    price = _package_price()
    if price is None:
        await call.message.answer(texts.PRICE_NOT_SET)
        return
    await call.message.answer(
        texts.FESTIVAL_OFFER.format(gb=festival.PACKAGE_GB, bonus=bonus, price=price),
        reply_markup=keyboards.festival_continue_kb(),
    )


async def _invoice(message: Message, state: FSMContext, user_id: int, username: str) -> None:
    bonus, why_not = _next_bonus(user_id)
    if why_not:
        await message.answer(why_not)
        return
    price = _package_price()
    if price is None:
        await message.answer(texts.PRICE_NOT_SET)
        return
    card_number = db.get_setting("card_number")
    if not card_number:
        await message.answer(texts.CARD_NOT_CONFIGURED)
        return
    # Card to card only: no wallet, no weekly credit for the festival.
    await state.set_state(FestivalBuy.receipt)
    await state.update_data(fest_username=username, fest_price=price)
    await message.answer(
        texts.FESTIVAL_CARD_INSTRUCTIONS.format(
            username=escape(username),
            gb=festival.PACKAGE_GB,
            bonus=bonus,
            price=price,
            card_number=card_number,
        ),
        reply_markup=keyboards.cancel_kb(),
    )


@router.callback_query(F.data == "fest:go")
async def continue_offer(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    user_id = call.from_user.id
    if not await _still_live(user_id, call.message):
        return
    bonus, why_not = _next_bonus(user_id)
    if why_not:
        await call.message.answer(why_not)
        return

    # Everything owed has to be cleared first — invoices, and weekly credit
    # even before its Friday comes round. Sent to the usual payment screens.
    owed = open_bills(user_id)
    if owed:
        await call.message.answer(
            texts.FESTIVAL_DEBTS_FIRST.format(total=sum(b.amount for b in owed)),
            reply_markup=keyboards.suspended_kb(),
        )
        return

    admins = await _panels(user_id, call.message)
    if admins is None:
        return
    if len(admins) == 1:
        await _invoice(call.message, state, user_id, admins[0]["username"])
        return
    await call.message.answer(
        texts.FESTIVAL_PICK_PANEL, reply_markup=keyboards.panel_picker_kb(admins, "festbuy")
    )


@router.callback_query(F.data.startswith("pick:festbuy:"))
async def picked_buy_panel(call: CallbackQuery, state: FSMContext) -> None:
    username = call.data.split(":", 2)[2]
    user_id = call.from_user.id
    try:
        admins = await nexra_panel.get_admins(user_id)
    except Exception:
        await call.answer(texts.PANEL_UNREACHABLE, show_alert=True)
        return
    if not any(a["username"] == username for a in admins):
        await call.answer(texts.NOT_LINKED_RETRY, show_alert=True)
        return
    await call.answer()
    if not await _still_live(user_id, call.message):
        return
    await _invoice(call.message, state, user_id, username)


@router.message(FestivalBuy.receipt, ~F.text.in_(ALL_MENU_TEXTS))
async def get_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.photo:
        await message.answer(texts.NOT_A_PHOTO)
        return
    data = await state.get_data()
    await state.clear()
    user_id = message.from_user.id
    username = data["fest_username"]

    try:
        admins = await nexra_panel.get_admins(user_id)
    except Exception:
        admins = None
    if admins is not None and not any(a["username"] == username for a in admins):
        await message.answer(texts.NOT_LINKED_RETRY, reply_markup=await menu_kb_for(user_id))
        return

    # The gift is fixed by the receipt, counting the ones still waiting as
    # well, so two receipts sent from two open screens can't both take the
    # same step. Money already sent is never turned away: past the fifth it is
    # still a 1000 GB purchase, just without a gift.
    approved, pending = festival.purchases(user_id)
    bonus = festival.bonus_for(approved + pending) or 0

    os.makedirs(settings.media_dir, exist_ok=True)
    receipt_path = os.path.join(settings.media_dir, f"receipt_{uuid.uuid4().hex}.jpg")
    await bot.download(message.photo[-1], destination=receipt_path)

    request_id = db.create_request(
        admin_telegram_id=user_id,
        admin_username=username,
        requested_gb=festival.PACKAGE_GB,
        toman_amount=data["fest_price"],
        receipt_path=receipt_path,
        kind="festival" if bonus else "topup",
        bonus_gb=bonus,
    )
    await message.answer(texts.FESTIVAL_SUBMITTED, reply_markup=await menu_kb_for(user_id))

    caption = (
        f"🔥 خرید جشنواره بلک فرایدی #{request_id}\n"
        f"▪️ پنل: {escape(username)}\n"
        f"👤 آیدی عددی: {user_id}\n"
        f"📊 حجم: {festival.PACKAGE_GB:,} گیگ + {bonus:g} گیگ هدیه "
        f"(خرید {approved + pending + 1} از {len(festival.BONUS_STEPS)})\n"
        f"💰 مبلغ: {data['fest_price']:,} تومان"
    ) + auto_approve.caption_note()
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_photo(
                superadmin_id,
                photo=FSInputFile(receipt_path),
                caption=caption,
                reply_markup=keyboards.approval_kb(request_id, user_id),
            )
        except Exception:
            continue


# ------------------------------------------------------------------ superadmin


def _admin_text() -> str:
    totals = db.festival_totals(festival.started_at())
    started = festival._parse(db.get_setting("festival_started_at"))
    return texts.FESTIVAL_ADMIN.format(
        status=texts.FESTIVAL_STATUS_LIVE if festival.is_live() else texts.FESTIVAL_STATUS_OFF,
        ends=festival.describe_end(),
        started=started.astimezone(festival.TEHRAN).strftime("%Y-%m-%d %H:%M") if started else "—",
        **totals,
    )


@router.message(Label("BTN_FESTIVAL_ADMIN"), SuperadminFilter())
async def festival_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await festival.refresh()
    await message.answer(_admin_text(), reply_markup=keyboards.festival_admin_kb())


async def _created(message: Message, code: str) -> None:
    await message.answer(
        texts.GIFT_CODE_CREATED.format(code=code, gb=festival.GIFT_CODE_GB),
        reply_markup=superadmin_kb(message.chat.id),
    )


@router.callback_query(F.data == "gc:new", SuperadminFilter())
async def new_random_code(call: CallbackQuery) -> None:
    await call.answer()
    for _ in range(5):
        code = "BF-" + "".join(secrets.choice(_CODE_CHARS) for _ in range(8))
        if db.create_gift_code(code, festival.GIFT_CODE_GB, call.from_user.id):
            await _created(call.message, code)
            return


@router.callback_query(F.data == "gc:custom", SuperadminFilter())
async def ask_custom_code(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(GiftCodeAdmin.code)
    await call.message.answer(texts.ASK_GIFT_CODE, reply_markup=keyboards.cancel_kb())


@router.message(GiftCodeAdmin.code, SuperadminFilter(), ~F.text.in_(ALL_MENU_TEXTS))
async def save_custom_code(message: Message, state: FSMContext) -> None:
    code = normalize_code(message.text)
    if not _CODE_RE.match(code):
        await message.answer(texts.GIFT_CODE_INVALID)
        return
    await state.clear()
    if not db.create_gift_code(code, festival.GIFT_CODE_GB, message.from_user.id):
        await message.answer(texts.GIFT_CODE_EXISTS, reply_markup=superadmin_kb(message.from_user.id))
        return
    await _created(message, code)


@router.callback_query(F.data == "gc:list", SuperadminFilter())
async def list_codes(call: CallbackQuery) -> None:
    await call.answer()
    codes = db.list_gift_codes()
    if not codes:
        await call.message.answer(texts.GIFT_CODES_EMPTY)
        return
    lines = []
    for c in codes:
        if c["redeemed_by"] is None:
            lines.append(texts.GIFT_CODE_LINE_FREE.format(code=escape(c["code"])))
            continue
        user = db.get_user(c["redeemed_by"]) or {}
        who = escape(user.get("full_name") or "") or str(c["redeemed_by"])
        lines.append(
            texts.GIFT_CODE_LINE_WON.format(
                code=escape(c["code"]),
                who=f"{who} (<code>{c['redeemed_by']}</code>)",
                panel=escape(c["username"] or texts.GIFT_CODE_PANEL_PENDING),
            )
        )
    await call.message.answer(
        texts.GIFT_CODES_HEADER + "".join(lines),
        reply_markup=keyboards.gift_codes_delete_kb(codes),
    )


@router.callback_query(F.data.startswith("gc:del:"), SuperadminFilter())
async def delete_code(call: CallbackQuery) -> None:
    code = call.data.split(":", 2)[2]
    if db.delete_gift_code(code):
        await call.answer(texts.GIFT_CODE_DELETED, show_alert=True)
    else:
        await call.answer(texts.GIFT_CODE_NOT_DELETED, show_alert=True)
