"""Weekly credit billing, on Tehran local time.

Two fixed points in the Persian week, both at 08:00 Asia/Tehran:
  • Wednesday — two days before the week ends: remind each debtor what they owe.
  • Friday — the end of the week: take what the wallet covers, tell each debtor
    what (if anything) is still outstanding, and send the superadmin the roster.

Each run is stamped with its ISO year-week so a restart, or the loop ticking
more than once inside the same hour, can't double-send.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot

from . import keyboards, texts
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


async def send_reminders(bot: Bot) -> int:
    """Wednesday: nudge every debtor with a pay button."""
    sent = 0
    for debt in db.list_outstanding_debts():
        if not debt["telegram_id"]:
            continue
        try:
            await bot.send_message(
                debt["telegram_id"],
                texts.WEEKLY_REMINDER.format(username=debt["username"], amount=debt["amount"]),
                reply_markup=keyboards.pay_debt_kb(debt["username"]),
            )
            sent += 1
        except Exception:
            continue
    return sent


async def run_settlement(bot: Bot) -> None:
    """Friday: draw down wallets, tell each debtor where they stand, then report."""
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

    report_lines: list[str] = []
    for debt in debts:
        username = debt["username"]
        telegram_id = debt["telegram_id"]
        paid = paid_by_panel.get(username, 0)
        remaining = db.get_debt(username)

        if telegram_id:
            try:
                if remaining <= 0:
                    await bot.send_message(
                        telegram_id,
                        texts.WEEKLY_WALLET_SETTLED.format(
                            username=username,
                            paid=paid,
                            balance=db.get_wallet_balance(telegram_id),
                        ),
                    )
                else:
                    await bot.send_message(
                        telegram_id,
                        texts.WEEKLY_WALLET_PARTIAL.format(
                            username=username, paid=paid, remaining=remaining
                        ),
                        reply_markup=keyboards.pay_debt_kb(username),
                    )
            except Exception:
                pass

        report_lines.append(
            texts.WEEKLY_SETTLEMENT_LINE.format(
                username=username,
                amount=remaining if remaining > 0 else paid,
                note=texts.WEEKLY_SETTLEMENT_PAID_NOTE if remaining <= 0 else "",
            )
        )

    report = texts.WEEKLY_SETTLEMENT_LIST_HEADER + "".join(report_lines)
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(superadmin_id, report)
        except Exception:
            continue


async def tick(bot: Bot) -> None:
    now = datetime.now(TEHRAN)
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


async def run_weekly_scheduler(bot: Bot) -> None:
    while True:
        try:
            await tick(bot)
        except Exception as exc:  # a bad week must not kill the loop
            logger.error(f"weekly scheduler failed: {exc}")
        await asyncio.sleep(600)
