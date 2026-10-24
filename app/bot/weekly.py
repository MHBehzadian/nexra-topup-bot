"""Weekly credit billing, on Tehran local time.

Two fixed points in the Persian week, both at 08:00 Asia/Tehran:
  • Wednesday — two days before the week ends: remind each debtor what they owe.
  • Friday — the end of the week: take what the wallet covers, tell each debtor
    what (if anything) is still outstanding, and send the superadmin the roster.
Whatever is overdue after that is chased every other day. Every message goes
to the customer once for all their panels and invoices, never once per bill.

Each run is stamped with its ISO year-week so a restart, or the loop ticking
more than once inside the same hour, can't double-send.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import Bot

from . import enforcement, keyboards, texts
from .invoices import describe_due, is_due
from .. import db
from ..billing import apply_wallet_to_debts
from ..config import settings

logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo("Asia/Tehran")

# Python weekday(): Monday=0 ... Wednesday=2, Friday=4.
REMINDER_WEEKDAY = 2
SETTLEMENT_WEEKDAY = 4
RUN_HOUR = 8


def _week_stamp(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-{week:02d}"


def _already_ran(key: str, stamp: str) -> bool:
    return db.get_setting(key) == stamp


# Bills are chased per customer, in one message for all their panels and
# invoices, and at most every CHASE_EVERY_DAYS. Wednesday's reminder and
# Friday's settlement count as a chase too, so the day after either is quiet.
CHASE_EVERY_DAYS = 2


def _chase_key(telegram_id: int) -> str:
    return f"chased:{telegram_id}"


def _chased_recently(telegram_id: int, today: date) -> bool:
    try:
        last = date.fromisoformat(db.get_setting(_chase_key(telegram_id)) or "")
    except ValueError:
        return False
    return (today - last).days < CHASE_EVERY_DAYS


def _by_owner(rows, owner) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for row in rows:
        if owner(row):
            grouped.setdefault(owner(row), []).append(row)
    return grouped


def _days_overdue(debt: dict, now: datetime) -> int:
    try:
        since = datetime.fromisoformat(debt["overdue_since"]).astimezone(TEHRAN)
        return max(1, (now - since).days)
    except Exception:
        return 1


async def _send(bot: Bot, telegram_id: int, text: str, markup) -> bool:
    try:
        await bot.send_message(telegram_id, text, reply_markup=markup)
        return True
    except Exception as exc:
        logger.info(f"could not message {telegram_id}: {type(exc).__name__}")
        return False


async def send_reminders(bot: Bot) -> int:
    """Wednesday: nudge every debtor, once for all their panels."""
    sent = 0
    today = datetime.now(TEHRAN).date()
    for telegram_id, debts in _by_owner(db.list_outstanding_debts(), lambda d: d["telegram_id"]).items():
        if len(debts) == 1:
            debt = debts[0]
            text = texts.WEEKLY_REMINDER.format(username=debt["username"], amount=debt["amount"])
            markup = keyboards.pay_debt_kb(debt["username"])
        else:
            text = texts.WEEKLY_REMINDER_MULTI.format(
                lines="".join(
                    texts.OWED_LINE_WEEKLY.format(username=d["username"], amount=d["amount"])
                    for d in debts
                ),
                total=sum(d["amount"] for d in debts),
            )
            markup = keyboards.suspended_kb()
        sent += await _send(bot, telegram_id, text, markup)
        db.set_setting(_chase_key(telegram_id), today.isoformat())
    return sent


async def send_debt_reminders(bot: Bot) -> int:
    """Chase what is overdue — weekly credit past its settlement, and manual
    invoices past their deadline — in one message per customer, every other day.

    Weekly credit is chased only once stamped overdue: someone who bought on
    Saturday has until Friday to pay and must not be nagged in between.
    Invoices with no deadline are never chased — an open-ended invoice is a
    record, not a demand.
    """
    now = datetime.now(TEHRAN)
    today = now.date()
    debts = _by_owner(
        (d for d in db.list_outstanding_debts() if d.get("overdue_since")),
        lambda d: d["telegram_id"],
    )
    invoices = _by_owner(
        (i for i in db.list_pending_invoices() if is_due(i.due_at)),
        lambda i: i.telegram_id,
    )

    sent = 0
    for telegram_id in list(dict.fromkeys([*debts, *invoices])):
        if _chased_recently(telegram_id, today):
            continue
        owed_debts, owed_invoices = debts.get(telegram_id, []), invoices.get(telegram_id, [])
        if len(owed_debts) + len(owed_invoices) == 1:
            if owed_debts:
                debt = owed_debts[0]
                text = texts.OVERDUE_REMINDER.format(
                    username=debt["username"], amount=debt["amount"], days=_days_overdue(debt, now)
                )
                markup = keyboards.pay_debt_kb(debt["username"])
            else:
                invoice = owed_invoices[0]
                text = texts.INVOICE_REMINDER.format(
                    id=invoice.id,
                    amount=invoice.remaining,
                    description=invoice.description or "—",
                    due=describe_due(invoice.due_at),
                )
                markup = keyboards.pay_invoice_kb(invoice.id)
        else:
            lines = "".join(
                texts.OWED_LINE_WEEKLY_OVERDUE.format(
                    username=d["username"], amount=d["amount"], days=_days_overdue(d, now)
                )
                for d in owed_debts
            ) + "".join(
                texts.OWED_LINE_INVOICE.format(
                    id=i.id,
                    description=i.description or "—",
                    amount=i.remaining,
                    due=describe_due(i.due_at),
                )
                for i in owed_invoices
            )
            text = texts.OVERDUE_REMINDER_MULTI.format(
                lines=lines,
                total=sum(d["amount"] for d in owed_debts) + sum(i.remaining for i in owed_invoices),
            )
            markup = keyboards.suspended_kb()
        sent += await _send(bot, telegram_id, text, markup)
        # Stamped either way, so a blocked chat isn't retried every tick.
        db.set_setting(_chase_key(telegram_id), today.isoformat())
        for invoice in owed_invoices:
            db.set_invoice_reminded(invoice.id, today.isoformat())
    return sent


def _lock_line(telegram_id: int) -> str:
    # Said now, with the time, rather than left to the lock itself: this is the
    # last routine message before it lands.
    deadline = enforcement.deadline_for(telegram_id)
    return (
        texts.WEEKLY_LOCK_LINE.format(deadline=enforcement.describe_deadline(deadline))
        if deadline
        else ""
    )


async def run_settlement(bot: Bot) -> None:
    """Friday: draw down wallets, tell each debtor where they stand — once for
    all their panels — then report to the superadmin."""
    debts = db.list_outstanding_debts()
    if not debts:
        for superadmin_id in settings.superadmin_id_list:
            try:
                await bot.send_message(superadmin_id, texts.WEEKLY_SETTLEMENT_NONE)
            except Exception:
                continue
        return

    # Wallet is per person, so settle once per owner rather than once per panel.
    paid_by_panel: dict[str, int] = {}
    for telegram_id in {d["telegram_id"] for d in debts if d["telegram_id"]}:
        for entry in apply_wallet_to_debts(telegram_id):
            paid_by_panel[entry["username"]] = entry["paid"]

    today = datetime.now(TEHRAN).date()
    report_lines: list[str] = []
    outcome: dict[str, tuple[int, int]] = {}
    for debt in debts:
        username = debt["username"]
        paid = paid_by_panel.get(username, 0)
        remaining = db.get_debt(username)
        outcome[username] = (paid, remaining)
        if remaining > 0:
            # Survived its settlement date — from now on it gets chased.
            db.mark_overdue(username)
        report_lines.append(
            texts.WEEKLY_SETTLEMENT_LINE.format(
                username=username,
                amount=remaining if remaining > 0 else paid,
                note=texts.WEEKLY_SETTLEMENT_PAID_NOTE if remaining <= 0 else "",
            )
        )

    for telegram_id, owned in _by_owner(debts, lambda d: d["telegram_id"]).items():
        names = [d["username"] for d in owned]
        left = sum(outcome[n][1] for n in names)
        if len(names) == 1:
            paid, remaining = outcome[names[0]]
            if remaining <= 0:
                text = texts.WEEKLY_WALLET_SETTLED.format(
                    username=names[0], paid=paid, balance=db.get_wallet_balance(telegram_id)
                )
                markup = None
            else:
                text = texts.WEEKLY_WALLET_PARTIAL.format(
                    username=names[0], paid=paid, remaining=remaining, lock_line=_lock_line(telegram_id)
                )
                markup = keyboards.pay_debt_kb(names[0])
        elif left <= 0:
            text = texts.WEEKLY_WALLET_SETTLED_MULTI.format(
                lines="".join(
                    texts.SETTLEMENT_LINE_PAID.format(username=n, paid=outcome[n][0]) for n in names
                ),
                balance=db.get_wallet_balance(telegram_id),
            )
            markup = None
        else:
            text = texts.WEEKLY_SETTLEMENT_MULTI.format(
                lines="".join(
                    texts.SETTLEMENT_LINE_LEFT.format(
                        username=n, paid=outcome[n][0], remaining=outcome[n][1]
                    )
                    if outcome[n][1] > 0
                    else texts.SETTLEMENT_LINE_PAID.format(username=n, paid=outcome[n][0])
                    for n in names
                ),
                remaining=left,
                lock_line=_lock_line(telegram_id),
            )
            markup = keyboards.suspended_kb()
        await _send(bot, telegram_id, text, markup)
        db.set_setting(_chase_key(telegram_id), today.isoformat())

    report = texts.WEEKLY_SETTLEMENT_LIST_HEADER + "".join(report_lines)
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(superadmin_id, report)
        except Exception:
            continue


async def tick(bot: Bot) -> None:
    now = datetime.now(TEHRAN)

    # Locking and unlocking runs on every pass, not just at RUN_HOUR: the 24h
    # grace expires at whatever time Friday's settlement ran, and someone who
    # has just paid should get their panel back within minutes, not at 08:00.
    try:
        await enforcement.tick(bot)
    except Exception as exc:
        logger.error(f"non-payment enforcement failed: {exc}")

    if now.hour != RUN_HOUR:
        return
    stamp = _week_stamp(now)

    if now.weekday() == REMINDER_WEEKDAY and not _already_ran("weekly_reminder_week", stamp):
        count = await send_reminders(bot)
        db.set_setting("weekly_reminder_week", stamp)
        logger.info(f"weekly reminders sent: {count}")

    if now.weekday() == SETTLEMENT_WEEKDAY and not _already_ran("weekly_settlement_week", stamp):
        await run_settlement(bot)
        db.set_setting("weekly_settlement_week", stamp)
        logger.info("weekly settlement completed")

    # After the two above, so whoever they just reached is left alone today:
    # each customer hears about what they owe at most every other day.
    day_stamp = now.strftime("%Y-%m-%d")
    if db.get_setting("overdue_reminder_date") != day_stamp:
        count = await send_debt_reminders(bot)
        db.set_setting("overdue_reminder_date", day_stamp)
        if count:
            logger.info(f"debt reminders sent: {count}")


async def run_weekly_scheduler(bot: Bot) -> None:
    while True:
        try:
            await tick(bot)
        except Exception as exc:  # a bad week must not kill the loop
            logger.error(f"weekly scheduler failed: {exc}")
        await asyncio.sleep(600)
