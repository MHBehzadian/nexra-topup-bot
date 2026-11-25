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


async def _owes(user_id: int, message: Message) -> bool:
    """Whether they owe anything (and are told to settle it first): neither a
    gift code nor a festival purchase is for someone with an open bill."""
    owed = open_bills(user_id)
    if not owed:
        return False
    await message.answer(
        texts.FESTIVAL_CODE_DEBTS_FIRST.format(total=sum(b.amount for b in owed)),
        reply_markup=keyboards.suspended_kb(),
    )
    return True


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
    # Debts are judged once the code is in, so the superadmin's report can say
    # who entered which code and why it didn't go to them.
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
    found = db.get_gift_code(code) if _CODE_RE.match(code) else None
    if not found or found.get("deleted"):
        # Stay in the state: a typo deserves another go without starting over.
        await message.answer(texts.FESTIVAL_CODE_INVALID)
        return
    await state.clear()
    name = message.from_user.full_name
    menu = await menu_kb_for(user_id)

    async def late(outcome: str, debt: int = 0, best_gb: float | None = None) -> None:
        place = db.log_code_attempt(code, user_id, name, outcome, debt, best_gb)
        await message.answer(
            texts.FESTIVAL_CODE_TAKEN.format(place=_ordinal(place)), reply_markup=menu
        )

    taken = found["redeemed_by"] is not None and found["redeemed_by"] != user_id
    owed = open_bills(user_id)
    debt = sum(b.amount for b in owed)

    # The code's own condition, never announced: a panel with at least this
    # much traffic left right now.
    min_gb = found.get("min_gb") or 0
    best_gb = None
    if min_gb:
        try:
            admins = await nexra_panel.get_admins(user_id)
        except Exception:
            await message.answer(texts.PANEL_UNREACHABLE, reply_markup=menu)
            return
        best_gb = max((bytes_to_gb(a.get("traffic")) for a in admins), default=0)
    unmet = [r for r, failed in (("debt", debt > 0), ("low", best_gb is not None and best_gb < min_gb)) if failed]

    if taken:
        # Gone anyway, so that is what they are told; the report keeps the rest.
        await late("+".join(unmet + ["late"]), debt, best_gb)
        return
    if unmet:
        # The code stays for the next person; they hear what they were missing.
        db.log_code_attempt(code, user_id, name, "+".join(unmet), debt, best_gb)
        conditions = ""
        if "debt" in unmet:
            conditions += texts.FESTIVAL_COND_DEBT.format(total=debt)
        if "low" in unmet:
            conditions += texts.FESTIVAL_COND_MIN_GB.format(min_gb=min_gb)
        await message.answer(
            texts.FESTIVAL_CODE_UNMET.format(conditions=conditions),
            reply_markup=keyboards.suspended_kb() if debt else menu,
        )
        if debt:
            await message.answer(texts.BACK_TO_MENU, reply_markup=menu)
        return

    outcome = db.claim_gift_code(code, user_id, festival.started_at())
    if outcome == "invalid":
        await message.answer(texts.FESTIVAL_CODE_INVALID, reply_markup=menu)
        return
    if outcome == "taken":
        await late("late", 0, best_gb)
        return
    if outcome == "already":
        db.log_code_attempt(code, user_id, name, "already")
        await message.answer(texts.FESTIVAL_CODE_ALREADY, reply_markup=menu)
        return
    db.log_code_attempt(code, user_id, name, "won", 0, best_gb)

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


async def _created(message: Message, code: str, min_gb: float) -> None:
    cond = texts.GIFT_CODE_COND_SUFFIX.format(min_gb=min_gb) if min_gb else ""
    await message.answer(
        texts.GIFT_CODE_CREATED.format(code=code, gb=festival.GIFT_CODE_GB, cond=cond),
        reply_markup=superadmin_kb(message.chat.id),
    )


async def _make_random(message: Message, user_id: int, min_gb: float) -> None:
    for _ in range(5):
        code = "BF-" + "".join(secrets.choice(_CODE_CHARS) for _ in range(8))
        if db.create_gift_code(code, festival.GIFT_CODE_GB, user_id, min_gb):
            await _created(message, code, min_gb)
            return


async def _next_step(message: Message, state: FSMContext, user_id: int, kind: str, min_gb: float) -> None:
    """Once the condition is known: a random code is made now; for a typed
    one, its text is asked for."""
    if kind == "new":
        await state.clear()
        await _make_random(message, user_id, min_gb)
        return
    await state.set_state(GiftCodeAdmin.code)
    await state.update_data(min_gb=min_gb)
    await message.answer(texts.ASK_GIFT_CODE, reply_markup=keyboards.cancel_kb())


@router.callback_query(F.data.in_({"gc:new", "gc:custom"}), SuperadminFilter())
async def ask_condition(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.clear()
    kind = call.data.split(":", 1)[1]
    await call.message.answer(
        texts.ASK_GIFT_CODE_CONDITION, reply_markup=keyboards.gift_code_condition_kb(kind)
    )


@router.callback_query(F.data.startswith("gc:cond:"), SuperadminFilter())
async def chose_condition(call: CallbackQuery, state: FSMContext) -> None:
    _, _, kind, value = call.data.split(":", 3)
    await call.answer()
    await call.message.edit_reply_markup(reply_markup=None)
    if value == "other":
        await state.set_state(GiftCodeAdmin.min_gb)
        await state.update_data(kind=kind)
        await call.message.answer(texts.ASK_GIFT_CODE_MIN_GB, reply_markup=keyboards.cancel_kb())
        return
    await _next_step(call.message, state, call.from_user.id, kind, float(value))


@router.message(GiftCodeAdmin.min_gb, SuperadminFilter(), ~F.text.in_(ALL_MENU_TEXTS))
async def typed_min_gb(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().translate(_FA_DIGITS).replace(",", "")
    try:
        min_gb = float(raw)
    except ValueError:
        min_gb = 0
    if min_gb <= 0:
        await message.answer(texts.INVALID_GIFT_CODE_MIN_GB)
        return
    kind = (await state.get_data()).get("kind", "new")
    await _next_step(message, state, message.from_user.id, kind, min_gb)


@router.message(GiftCodeAdmin.code, SuperadminFilter(), ~F.text.in_(ALL_MENU_TEXTS))
async def save_custom_code(message: Message, state: FSMContext) -> None:
    code = normalize_code(message.text)
    if not _CODE_RE.match(code):
        await message.answer(texts.GIFT_CODE_INVALID)
        return
    min_gb = float((await state.get_data()).get("min_gb") or 0)
    await state.clear()
    if not db.create_gift_code(code, festival.GIFT_CODE_GB, message.from_user.id, min_gb):
        await message.answer(texts.GIFT_CODE_EXISTS, reply_markup=superadmin_kb(message.from_user.id))
        return
    await _created(message, code, min_gb)


@router.callback_query(F.data == "gc:list", SuperadminFilter())
async def list_codes(call: CallbackQuery) -> None:
    await call.answer()
    codes = db.list_gift_codes()
    if not codes:
        await call.message.answer(texts.GIFT_CODES_EMPTY)
        return
    counts = db.code_log_counts()
    lines = []
    for c in codes:
        n = counts.get(c["code"], 0)
        tried = texts.GIFT_CODE_LINE_TRIED.format(count=n) if n else ""
        if c.get("min_gb"):
            tried = texts.GIFT_CODE_LINE_COND.format(min_gb=c["min_gb"]) + tried
        if c["redeemed_by"] is None:
            lines.append(texts.GIFT_CODE_LINE_FREE.format(code=escape(c["code"]), tried=tried))
            continue
        user = db.get_user(c["redeemed_by"]) or {}
        who = escape(user.get("full_name") or "") or str(c["redeemed_by"])
        lines.append(
            texts.GIFT_CODE_LINE_WON.format(
                code=escape(c["code"]),
                who=f"{who} (<code>{c['redeemed_by']}</code>)",
                panel=escape(c["username"] or texts.GIFT_CODE_PANEL_PENDING),
                tried=tried,
            )
        )
    await call.message.answer(
        texts.GIFT_CODES_HEADER + "".join(lines) + texts.GIFT_CODES_REPORT_HINT,
        reply_markup=keyboards.gift_codes_report_kb(codes, counts),
    )


_REPORT_MAX = 40


@router.callback_query(F.data.startswith("gc:rep:"), SuperadminFilter())
async def code_report(call: CallbackQuery) -> None:
    code = call.data.split(":", 2)[2]
    await call.answer()
    found = db.get_gift_code(code)
    entries = db.code_log(code)
    if not entries:
        await call.message.answer(texts.GIFT_CODE_REPORT_EMPTY.format(code=escape(code)))
        return
    text = texts.GIFT_CODE_REPORT_HEADER.format(code=escape(code), count=len(entries))
    for n, e in enumerate(entries[:_REPORT_MAX], start=1):
        panel = escape((found or {}).get("username") or texts.GIFT_CODE_PANEL_PENDING)
        best = (
            texts.GIFT_CODE_BEST_GB.format(gb=e["best_gb"]) if e.get("best_gb") is not None else "—"
        )
        icons, reasons = [], []
        # "debt_late" is how an entry read before reasons were joined with "+".
        for part in e["outcome"].replace("_", "+").split("+"):
            icon, reason = texts.GIFT_CODE_REASONS.get(part, ("▫️", part))
            icons.append(icon)
            reasons.append(
                reason.format(
                    debt=e["debt"] or 0,
                    panel=panel,
                    min_gb=(found or {}).get("min_gb") or 0,
                    best_gb=best,
                )
            )
        icon, reason = "".join(icons), texts.GIFT_CODE_REASON_JOIN.join(reasons)
        if e["tries"] and e["tries"] > 1:
            reason += texts.GIFT_CODE_REPORT_TRIES.format(tries=e["tries"])
        handle = f"@{e['tg_username']} · " if e.get("tg_username") else ""
        stamp = festival._parse(e["first_at"])
        text += texts.GIFT_CODE_REPORT_LINE.format(
            n=n,
            icon=icon,
            name=escape(e["name"] or e.get("tg_name") or "—"),
            ident=f"({escape(handle)}<code>{e['telegram_id']}</code>)",
            time=stamp.astimezone(festival.TEHRAN).strftime("%H:%M:%S") if stamp else "—",
            reason=reason,
        )
    if len(entries) > _REPORT_MAX:
        text += texts.GIFT_CODE_REPORT_MORE.format(count=len(entries) - _REPORT_MAX)
    await call.message.answer(text)


@router.callback_query(F.data == "gc:dellist", SuperadminFilter())
async def pick_code_to_delete(call: CallbackQuery) -> None:
    await call.answer()
    codes = db.list_gift_codes()
    if not codes:
        await call.message.answer(texts.GIFT_CODES_EMPTY)
        return
    await call.message.answer(
        texts.GIFT_CODES_DELETE_PICK, reply_markup=keyboards.gift_codes_delete_kb(codes)
    )


@router.callback_query(F.data.startswith("gc:del:"), SuperadminFilter())
async def confirm_delete_code(call: CallbackQuery) -> None:
    code = call.data.split(":", 2)[2]
    found = db.get_gift_code(code)
    if not found or found.get("deleted"):
        await call.answer(texts.GIFT_CODE_NOT_DELETED, show_alert=True)
        return
    await call.answer()
    text = texts.GIFT_CODE_CONFIRM_DELETE if found["redeemed_by"] is None else texts.GIFT_CODE_CONFIRM_DELETE_WON
    await call.message.answer(
        text.format(code=escape(code)), reply_markup=keyboards.gift_code_confirm_delete_kb(code)
    )


@router.callback_query(F.data.startswith("gc:delok:"), SuperadminFilter())
async def delete_code(call: CallbackQuery) -> None:
    code = call.data.split(":", 2)[2]
    if not db.delete_gift_code(code):
        await call.answer(texts.GIFT_CODE_NOT_DELETED, show_alert=True)
        return
    await call.answer()
    await call.message.edit_text(texts.GIFT_CODE_DELETED.format(code=escape(code)))


@router.callback_query(F.data == "gc:delno", SuperadminFilter())
async def keep_code(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.edit_text(texts.GIFT_CODE_DELETE_KEPT)
