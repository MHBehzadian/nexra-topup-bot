"""Locking a panel when its bills go unpaid, and giving it back when they don't.

Reminders alone stopped working: nothing happened to anyone who ignored them,
so ignoring them became normal. A panel whose debt survives its settlement date
by a further 24 hours now has its password changed, which locks the reseller out
of both Marzban and Nexra until they settle. Their users keep working — this
costs the reseller their management access, not their customers' configs.

Two deliberate limits:
  • Only debts that fell due after enforcement was switched on count. Whatever
    was already outstanding on the day this shipped is never grounds for a lock,
    so nobody wakes up locked out over a bill they were never warned carried
    teeth.
  • A lock is lifted only when the customer owes nothing at all — weekly credit
    and manual invoices alike — since partial payment is how the old reminders
    were ignored in the first place.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from . import bills, keyboards, texts
from .. import db
from ..config import settings
from ..services.nexra_panel import NexraPanelError, nexra_panel

logger = logging.getLogger(__name__)

# What a locked panel's password becomes.
LOCK_PASSWORD = "75911304@Mhb"

# Grace past the settlement date before the lock lands.
GRACE_HOURS = 24

# What was already overdue when enforcement started isn't exempt forever, but it
# is given a fortnight from the start line to be cleared before it can lock
# anything — nobody is caught out by a bill that predates the rule.
LEGACY_GRACE_DAYS = 14

# The key is versioned: changing when the start line falls means re-stamping it,
# and a new key does that on the next run without touching the database by hand.
_CUTOFF_KEY = "enforcement_start_v2"


def cutoff() -> datetime:
    """The moment enforcement began. Written once, on the first run; debts
    already overdue by then get LEGACY_GRACE_DAYS from here, newer ones the
    usual 24 hours past their settlement date."""
    stored = db.get_setting(_CUTOFF_KEY)
    if stored:
        try:
            return datetime.fromisoformat(stored)
        except ValueError:
            pass
    now = datetime.now(timezone.utc)
    db.set_setting(_CUTOFF_KEY, now.isoformat())
    logger.info(f"non-payment enforcement starts from {now.isoformat()}")
    return now


def locking_bills(customer: bills.Customer, now: datetime | None = None) -> list[bills.Bill]:
    """The customer's bills that are late enough, and recent enough, to lock for.

    Weekly credit only. A manual invoice is a one-off arrangement rather than
    the standing weekly obligation this is meant to enforce, so it never locks
    anything — and never holds a lock closed either (see `owes_weekly`).
    """
    now = now or datetime.now(bills.TEHRAN)
    started = cutoff()
    deadline = now - timedelta(hours=GRACE_HOURS)
    eligible = []
    for bill in customer.bills:
        if bill.kind != "weekly":
            continue
        if bill.due is None or bill.due > deadline:
            continue  # not yet past the settlement date plus its grace
        if bill.due <= started and now < started + timedelta(days=LEGACY_GRACE_DAYS):
            continue  # predates the rule, and its fortnight hasn't run out yet
        eligible.append(bill)
    return eligible


def owes_weekly(telegram_id: int) -> bool:
    """Whether any weekly credit is still outstanding — the one thing that
    decides whether a lock stays on."""
    return any(b.kind == "weekly" and b.amount > 0 for b in bills.open_bills(telegram_id))


async def _panels_of(telegram_id: int) -> list[dict]:
    try:
        return await nexra_panel.get_admins(telegram_id)
    except NexraPanelError as exc:
        logger.warning(f"could not list panels for {telegram_id}: {exc}")
        return []


async def _passwords() -> dict[str, str]:
    """Current password per panel username, as the panel holds them."""
    try:
        creds = await nexra_panel.get_all_credentials()
    except NexraPanelError as exc:
        logger.warning(f"could not read panel credentials: {exc}")
        return {}
    return {c["username"]: c["marzban_password"] for c in creds if c.get("marzban_password")}


async def _tell(bot: Bot, chat_id: int, text: str, **kwargs) -> None:
    try:
        await bot.send_message(chat_id, text, **kwargs)
    except Exception:
        pass


async def _tell_superadmins(bot: Bot, text: str) -> None:
    for superadmin_id in settings.superadmin_id_list:
        await _tell(bot, superadmin_id, text)


async def lock_panels(
    bot: Bot, telegram_id: int, *, reason: str = "unpaid", total: int = 0, count: int = 0
) -> list[str]:
    """Lock every panel this person owns. Returns the ones actually locked."""
    panels = await _panels_of(telegram_id)
    if not panels:
        return []

    passwords = await _passwords()
    locked: list[str] = []
    for panel in panels:
        username = panel.get("username")
        if not username or db.is_suspended(username):
            continue
        current = passwords.get(username)
        if not current:
            logger.warning(f"no stored password for {username}; cannot lock it")
            continue
        try:
            await nexra_panel.change_password(
                telegram_id=telegram_id,
                current_password=current,
                new_password=LOCK_PASSWORD,
                username=username,
            )
        except NexraPanelError as exc:
            logger.error(f"failed to lock {username}: {exc}")
            continue
        # Written only after the panel confirms, so a failed change never
        # leaves a record claiming a lock that isn't there.
        db.record_suspension(username, telegram_id, current, reason=reason)
        locked.append(username)

    if not locked:
        return []

    await _tell(
        bot,
        telegram_id,
        texts.SUSPENDED_NOTICE.format(total=total, count=count),
        reply_markup=keyboards.suspended_kb(),
    )
    await _tell_superadmins(
        bot,
        texts.SUSPENDED_ADMIN_NOTICE.format(
            panels="، ".join(locked), telegram_id=telegram_id, total=total
        ),
    )
    logger.info(f"locked {locked} for {telegram_id} ({reason})")
    return locked


async def unlock(bot: Bot, telegram_id: int, *, reason: str | None = None) -> list[str]:
    """Put back every password this customer's panels had before the lock.

    `reason` narrows it: the automatic sweep passes 'unpaid' so a lock placed by
    hand is never lifted by someone simply settling their weekly credit.
    """
    rows = db.list_suspensions(telegram_id, reason=reason)
    if not rows:
        return []

    restored: list[str] = []
    for row in rows:
        try:
            await nexra_panel.change_password(
                telegram_id=telegram_id,
                current_password=LOCK_PASSWORD,
                new_password=row["previous_password"],
                username=row["username"],
            )
        except NexraPanelError as exc:
            logger.error(f"failed to unlock {row['username']}: {exc}")
            continue
        db.clear_suspension(row["username"])
        restored.append(row["username"])

    if not restored:
        return []

    await _tell(bot, telegram_id, texts.UNSUSPENDED_NOTICE)
    await _tell_superadmins(
        bot,
        texts.UNSUSPENDED_ADMIN_NOTICE.format(
            panels="، ".join(restored), telegram_id=telegram_id
        ),
    )
    logger.info(f"unlocked {restored} for {telegram_id}")
    return restored


async def settle_up(bot: Bot, telegram_id: int) -> None:
    """Called after any payment: give the panels back once the weekly credit is
    clear. Outstanding invoices don't hold it, since they could never have
    caused the lock in the first place."""
    if not db.list_suspensions(telegram_id, reason="unpaid"):
        return
    if owes_weekly(telegram_id):
        return
    await unlock(bot, telegram_id, reason="unpaid")


async def tick(bot: Bot) -> None:
    """One sweep: lock whoever has run out of grace, unlock whoever has paid."""
    cutoff()  # make sure the start line exists before anything is judged against it

    for customer in bills.by_customer(bills.open_bills()):
        if customer.telegram_id is None:
            continue
        overdue = locking_bills(customer)
        if overdue:
            await lock_panels(
                bot,
                customer.telegram_id,
                total=customer.total,
                count=len(customer.bills),
            )

    # Locks the rule put on come off as soon as the weekly credit is settled.
    for row in db.list_suspensions(reason="unpaid"):
        if not owes_weekly(row["telegram_id"]):
            await unlock(bot, row["telegram_id"], reason="unpaid")
