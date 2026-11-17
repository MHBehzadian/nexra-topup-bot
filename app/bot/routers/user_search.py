"""Superadmin: look a customer up and act on them in one place.

Shows everything the bot knows about a person — panels, wallet, debts, open
invoices, recent transactions — with buttons to change a panel's traffic,
deduct from their wallet, issue an invoice, or remove one.

A person can be looked up by typing who they are, or by forwarding one of
their messages to the bot.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    MessageOriginChannel,
    MessageOriginChat,
    MessageOriginHiddenUser,
    MessageOriginUser,
)

from .. import bills, enforcement, keyboards, texts
from ..filters import Label, SuperadminFilter
from ..invoices import describe_due, due_at_for
from ..nav import ALL_MENU_TEXTS, superadmin_kb
from ..states import DeductWallet, NewInvoice, SearchUser
from ... import db
from ...services.nexra_panel import NexraPanelError, nexra_panel
from ...units import bytes_to_gb

logger = logging.getLogger(__name__)

router = Router(name="user_search")
router.message.filter(SuperadminFilter())
router.callback_query.filter(SuperadminFilter())


async def _resolve(query: str) -> tuple[int | None, list[dict]]:
    """Find a person by numeric id, Telegram @username, or panel username.

    Returns (telegram_id, their panels).
    """
    query = query.strip().lstrip("@")

    try:
        all_admins = await nexra_panel.list_all_admins()
    except NexraPanelError:
        all_admins = []

    telegram_id: int | None = None
    if query.lstrip("-").isdigit():
        telegram_id = int(query)
    else:
        # Panel username first — it's the identifier the superadmin sees most.
        match = next((a for a in all_admins if a.get("username") == query), None)
        if match and match.get("telegram_id"):
            telegram_id = match["telegram_id"]
        else:
            for user in db.list_known_users():
                record = db.get_user(user)
                if record and (record.get("username") or "").lower() == query.lower():
                    telegram_id = user
                    break

    if telegram_id is None:
        return None, []
    return telegram_id, [a for a in all_admins if a.get("telegram_id") == telegram_id]


def _render_profile(telegram_id: int, panels: list[dict]) -> str:
    record = db.get_user(telegram_id)
    name = escape((record or {}).get("full_name") or "—")
    mention = f"@{record['username']}" if record and record.get("username") else "—"

    text = texts.USER_PROFILE.format(
        name=name,
        telegram_id=telegram_id,
        mention=mention,
        wallet=db.get_wallet_balance(telegram_id),
        debt=sum(b.amount for b in bills.open_bills(telegram_id)),
    )

    if panels:
        lines = "".join(
            texts.USER_PROFILE_PANEL_LINE.format(
                username=p["username"]
                + (texts.PANEL_LOCKED_MARK if p.get("suspended_reason") else ""),
                remaining_gb=bytes_to_gb(p.get("traffic")),
                initial_gb=bytes_to_gb(p.get("initial_traffic")),
            )
            for p in panels
        )
        text += texts.USER_PROFILE_PANELS.format(panels=lines)
    else:
        text += texts.USER_PROFILE_NO_PANELS

    debts = [d for d in db.list_outstanding_debts() if d["telegram_id"] == telegram_id]
    if debts:
        text += texts.USER_PROFILE_DEBTS.format(
            debts="".join(
                texts.USER_PROFILE_DEBT_LINE.format(username=d["username"], amount=d["amount"])
                for d in debts
            )
        )
    else:
        text += texts.USER_PROFILE_NO_DEBTS

    invoices = db.list_pending_invoices(telegram_id)
    if invoices:
        text += texts.USER_PROFILE_INVOICES.format(
            invoices="".join(
                texts.USER_PROFILE_INVOICE_LINE.format(
                    id=i.id, amount=i.remaining, description=i.description or "—"
                )
                for i in invoices
            )
        )
    else:
        text += texts.USER_PROFILE_NO_INVOICES

    history = db.list_requests_for(telegram_id, limit=8)
    if history:
        text += texts.USER_PROFILE_HISTORY.format(
            history="".join(
                texts.USER_PROFILE_HISTORY_LINE.format(
                    kind=texts.KIND_LABELS.get(r.kind, r.kind),
                    amount=r.toman_amount,
                    status=texts.STATUS_LABELS.get(r.status, r.status),
                    date=r.created_at[:10],
                )
                for r in history
            )
        )
    else:
        text += texts.USER_PROFILE_NO_HISTORY

    return text


async def show_profile(message: Message, telegram_id: int, panels: list[dict] | None = None) -> None:
    """Send a customer's card, with everything that can be done about them.

    Without `panels`, their panels are fetched; a panel that can't be reached
    still leaves the rest of the card worth showing, so it says so instead.
    """
    unreachable = False
    if panels is None:
        try:
            panels = await nexra_panel.get_admins(telegram_id)
        except NexraPanelError as exc:
            logger.error("panel lookup failed for %s: %s", telegram_id, exc)
            panels, unreachable = [], True

    text = _render_profile(telegram_id, panels)
    if unreachable:
        text += "\n" + texts.PANEL_UNREACHABLE
    locked_on_panel = any(p.get("suspended_reason") for p in panels)
    await message.answer(
        text, reply_markup=keyboards.user_actions_kb(telegram_id, locked=locked_on_panel)
    )


@router.message(Label("BTN_SEARCH_USER"))
async def start_search(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchUser.query)
    await message.answer(texts.ASK_SEARCH_QUERY, reply_markup=keyboards.cancel_kb())


# Before do_search: while it waits for a name, a forwarded message is a better
# answer than the text inside it.
@router.message(StateFilter(None, SearchUser.query), F.forward_origin)
async def from_forward(message: Message, state: FSMContext) -> None:
    """A message the superadmin forwarded here: open its sender's card if they
    are a customer, otherwise just show whose it is."""
    await state.clear()
    origin = message.forward_origin

    if isinstance(origin, MessageOriginUser):
        await _open_or_identify(message, origin.sender_user.id)
        return

    if isinstance(origin, MessageOriginHiddenUser):
        # Telegram hands over only their name. When exactly one customer goes by
        # it, that's who it is; with none or several, guessing would be worse
        # than saying the id is hidden.
        matches = db.find_users_by_full_name(origin.sender_user_name)
        if len(matches) == 1:
            await show_profile(message, matches[0])
        else:
            await message.answer(
                texts.FORWARD_HIDDEN_USER.format(name=escape(origin.sender_user_name)),
                reply_markup=superadmin_kb(message.from_user.id),
            )
        return

    if isinstance(origin, (MessageOriginChat, MessageOriginChannel)):
        chat = origin.sender_chat if isinstance(origin, MessageOriginChat) else origin.chat
        await message.answer(
            texts.FORWARD_FROM_CHAT.format(title=escape(chat.title or "—"), chat_id=chat.id),
            reply_markup=superadmin_kb(message.from_user.id),
        )


async def _open_or_identify(message: Message, telegram_id: int) -> None:
    """Their card if they have used the bot or own a panel; their id otherwise."""
    try:
        panels = await nexra_panel.get_admins(telegram_id)
    except NexraPanelError as exc:
        logger.error("panel lookup failed for %s: %s", telegram_id, exc)
        panels = None

    if panels or db.get_user(telegram_id):
        await show_profile(message, telegram_id, panels)
        return

    text = texts.FORWARD_NOT_A_USER.format(telegram_id=telegram_id)
    if panels is None:
        # They may still own a panel we couldn't see.
        text += "\n\n" + texts.PANEL_UNREACHABLE
    await message.answer(text, reply_markup=superadmin_kb(message.from_user.id))


@router.message(SearchUser.query, ~F.text.in_(ALL_MENU_TEXTS))
async def do_search(message: Message, state: FSMContext) -> None:
    await state.clear()
    telegram_id, panels = await _resolve(message.text or "")
    if telegram_id is None:
        await message.answer(texts.USER_NOT_FOUND, reply_markup=superadmin_kb(message.from_user.id))
        return

    await show_profile(message, telegram_id, panels)


# ---- locking a customer's panels by hand -------------------------------------
# Same mechanism the weekly-credit rule uses, but recorded as a manual lock so
# the automatic sweep never lifts it on its own.

@router.callback_query(F.data.startswith("usr_lock:"))
async def ask_lock(call: CallbackQuery) -> None:
    target = int(call.data.split(":", 1)[1])
    await call.answer()
    await call.message.answer(
        texts.CONFIRM_LOCK, reply_markup=keyboards.confirm_lock_kb(target, locking=True)
    )


@router.callback_query(F.data.startswith("lockok:"))
async def do_lock(call: CallbackQuery, bot: Bot) -> None:
    target = int(call.data.split(":", 1)[1])
    owed = sum(b.amount for b in bills.open_bills(target))
    locked = await enforcement.lock_panels(
        bot, target, reason="manual", total=owed, count=len(bills.open_bills(target))
    )
    if not locked:
        await call.answer(texts.LOCK_NO_PANELS, show_alert=True)
        return
    await call.answer(texts.LOCKED_TOAST)


def _who(telegram_id: int) -> str:
    user = db.get_user(telegram_id) or {}
    if user.get("username"):
        return f"@{user['username']}"
    return user.get("full_name") or str(telegram_id)


@router.message(Label("BTN_LOCKED_PANELS"))
async def list_locked(message: Message) -> None:
    """Every panel locked right now, by customer, with a way to free each."""
    rows = db.list_suspensions()
    # Locked on the panel with no record here (see enforcement.unlock) still
    # counts: the admin is locked out all the same.
    try:
        recorded = {r["username"] for r in rows}
        rows += [
            {
                "username": a["username"],
                "telegram_id": a["telegram_id"],
                "suspended_at": "—",
                "reason": a["suspended_reason"],
            }
            for a in await nexra_panel.list_all_admins()
            if a.get("suspended_reason") and a.get("telegram_id") and a["username"] not in recorded
        ]
    except NexraPanelError as exc:
        logger.warning("could not read lock flags from the panel: %s", exc)
    if not rows:
        await message.answer(texts.LOCKED_LIST_NONE)
        return

    by_customer: dict[int, list[dict]] = {}
    for row in rows:
        by_customer.setdefault(row["telegram_id"], []).append(row)

    lines, buttons = [], []
    for telegram_id, locks in by_customer.items():
        who = _who(telegram_id)
        since = min(r["suspended_at"] for r in locks)
        try:
            since = datetime.fromisoformat(since).astimezone(bills.TEHRAN).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
        reasons = {r.get("reason") or "unpaid" for r in locks}
        lines.append(
            texts.LOCKED_LINE.format(
                panels="، ".join(r["username"] for r in locks),
                who=escape(who),
                telegram_id=telegram_id,
                reason="، ".join(
                    texts.LOCK_REASON_MANUAL if r == "manual" else texts.LOCK_REASON_UNPAID
                    for r in sorted(reasons)
                ),
                since=since,
                owed=sum(b.amount for b in bills.open_bills(telegram_id)),
            )
        )
        buttons.append((telegram_id, who[:30]))

    header = texts.LOCKED_LIST_HEADER.format(panels=len(rows), people=len(by_customer))
    # One message for a short list; a long one is split, buttons under the last.
    chunks, current = [], header
    for line in lines:
        if len(current) + len(line) > 3800:
            chunks.append(current)
            current = ""
        current += line
    chunks.append(current)
    for chunk in chunks[:-1]:
        await message.answer(chunk)
    await message.answer(chunks[-1], reply_markup=keyboards.locked_customers_kb(buttons))


@router.callback_query(F.data.startswith("usr_unlock:"))
async def ask_unlock(call: CallbackQuery) -> None:
    target = int(call.data.split(":", 1)[1])
    await call.answer()
    await call.message.answer(
        texts.CONFIRM_UNLOCK, reply_markup=keyboards.confirm_lock_kb(target, locking=False)
    )


@router.callback_query(F.data.startswith("unlockok:"))
async def do_unlock(call: CallbackQuery, bot: Bot) -> None:
    parts = call.data.split(":")
    target = int(parts[1])
    # A confirm button sent before respites existed carries no length.
    days = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 3
    # Granted before the unlock, so a sweep running meanwhile can't relock.
    until = enforcement.grant_respite(target, days or None)
    owes = enforcement.owes_weekly(target)
    when = enforcement.describe_deadline(until) if days else ""
    note = texts.UNSUSPENDED_RESPITE_NOTE.format(until=when) if days and owes else ""
    # Lifts both kinds: told to unlock by hand means unlock, whatever put it on.
    result = await enforcement.unlock(bot, target, note=note)
    if result.failed:
        # Said in full, in a message: "not locked" here would be a lie, and the
        # reason is what decides what to do next.
        await call.message.answer(
            texts.UNLOCK_FAILED.format(
                lines="".join(
                    texts.UNLOCK_FAILED_LINE.format(username=escape(u), reason=escape(why))
                    for u, why in result.failed
                )
            )
        )
    if not result:
        enforcement.clear_respite(target)
        if result.failed:
            await call.answer()
        else:
            await call.answer(texts.LOCK_NOT_LOCKED, show_alert=True)
        return
    if days:
        plain = re.sub(r"<[^>]+>", "", when)
        await call.answer(texts.UNLOCKED_RESPITE_TOAST.format(until=plain), show_alert=True)
    else:
        await call.answer(texts.UNLOCKED_UNTIL_PAID_TOAST, show_alert=True)


@router.callback_query(F.data == "lock_no")
async def cancel_lock(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(texts.LOCK_CANCELLED, reply_markup=superadmin_kb(call.from_user.id))


@router.callback_query(F.data.startswith("usr_deduct:"))
async def start_deduct(call: CallbackQuery, state: FSMContext) -> None:
    target = int(call.data.split(":", 1)[1])
    await state.set_state(DeductWallet.amount)
    await state.update_data(deduct_target=target)
    await call.answer()
    await call.message.answer(texts.ASK_DEDUCT_AMOUNT, reply_markup=keyboards.cancel_kb())


@router.message(DeductWallet.amount, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_deduct(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip().replace(",", "").replace("٬", "")
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(texts.INVALID_WALLET_AMOUNT)
        return

    data = await state.get_data()
    await state.clear()
    target, amount = data["deduct_target"], int(raw)
    balance = db.deduct_wallet(target, amount)

    await message.answer(
        texts.DEDUCT_SUCCESS.format(amount=amount, balance=balance),
        reply_markup=superadmin_kb(message.from_user.id),
    )
    try:
        await bot.send_message(target, texts.WALLET_BALANCE.format(balance=balance))
    except Exception:
        pass


@router.callback_query(F.data.startswith("usr_invoice:"))
async def invoice_for_user(call: CallbackQuery, state: FSMContext) -> None:
    """Jump straight into the invoice flow with the target already filled in."""
    target = int(call.data.split(":", 1)[1])
    await state.set_state(NewInvoice.amount)
    await state.update_data(invoice_target=target)
    await call.answer()
    await call.message.answer(texts.ASK_INVOICE_AMOUNT, reply_markup=keyboards.cancel_kb())


@router.callback_query(F.data.startswith("usr_delinv:"))
async def choose_bill_to_delete(call: CallbackQuery) -> None:
    """Weekly credit is money owed like any invoice, so it can be written off here too."""
    target = int(call.data.split(":", 1)[1])
    items = sorted(bills.open_bills(target), key=bills.urgency, reverse=True)
    if not items:
        await call.answer(texts.NO_INVOICES, show_alert=True)
        return
    await call.answer()
    await call.message.answer(
        texts.CHOOSE_INVOICE_TO_DELETE, reply_markup=keyboards.bills_delete_kb(items)
    )


