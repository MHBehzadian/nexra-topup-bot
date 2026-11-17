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

# How long before a lock lands the customer is warned, longest first. Each
# stage goes out once per deadline: a lock that arrived with nothing but the
# routine reminders before it read as a surprise, not a consequence.
WARNING_HOURS = (12, 2)

# Set once every lock that predates the panel knowing about locks has been
# told to it, so those admins also see why they can't log in.
_PANEL_SYNC_KEY = "suspensions_synced_to_panel_v1"


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


def lock_time(bill: bills.Bill, started: datetime) -> datetime | None:
    """When this bill becomes grounds for a lock, or None if it never can.

    Weekly credit only. A manual invoice is a one-off arrangement rather than
    the standing weekly obligation this is meant to enforce, so it never locks
    anything — and never holds a lock closed either (see `owes_weekly`).
    """
    if bill.kind != "weekly" or bill.due is None or bill.amount <= 0:
        return None
    at = bill.due + timedelta(hours=GRACE_HOURS)
    if bill.due <= started:
        # Predates the rule: it gets its fortnight from the start line first.
        at = max(at, started + timedelta(days=LEGACY_GRACE_DAYS))
    return at


# A lock lifted by hand is the superadmin's decision, and the next sweep used
# to put it straight back on — the debt that caused it was still there. An
# unlock by hand now comes with a respite: no automatic lock for this customer
# until it ends, or, with no end, until their weekly credit is settled.
UNTIL_PAID = datetime.max.replace(tzinfo=timezone.utc)


def _respite_key(telegram_id: int) -> str:
    return f"lock_respite:{telegram_id}"


def grant_respite(telegram_id: int, days: int | None) -> datetime:
    """No automatic lock for `days` from now (None: until the weekly credit is
    settled). Returns when it ends."""
    until = UNTIL_PAID if days is None else datetime.now(timezone.utc) + timedelta(days=days)
    db.set_setting(_respite_key(telegram_id), until.isoformat())
    return until


def clear_respite(telegram_id: int) -> None:
    db.set_setting(_respite_key(telegram_id), "")


def respite_until(telegram_id: int | None, now: datetime | None = None) -> datetime | None:
    """When this customer's respite ends, or None if they have none (left)."""
    if telegram_id is None:
        return None
    stored = db.get_setting(_respite_key(telegram_id))
    if not stored:
        return None
    try:
        until = datetime.fromisoformat(stored)
    except ValueError:
        return None
    # An until-paid respite ends once nothing weekly is owed, so the customer's
    # next unpaid week is treated like anyone else's.
    if until <= (now or datetime.now(timezone.utc)) or (
        until == UNTIL_PAID and not owes_weekly(telegram_id)
    ):
        clear_respite(telegram_id)
        return None
    return until


def locking_bills(customer: bills.Customer, now: datetime | None = None) -> list[bills.Bill]:
    """The customer's bills that are late enough, and recent enough, to lock for."""
    now = now or datetime.now(bills.TEHRAN)
    if respite_until(customer.telegram_id, now):
        return []
    started = cutoff()
    return [
        bill
        for bill in customer.bills
        if (at := lock_time(bill, started)) is not None and at <= now
    ]


def lock_deadline(customer: bills.Customer) -> datetime | None:
    """The earliest moment one of this customer's bills will lock their panels;
    None if none will (or not before they pay, under an until-paid respite)."""
    started = cutoff()
    times = [at for b in customer.bills if (at := lock_time(b, started)) is not None]
    if not times:
        return None
    respite = respite_until(customer.telegram_id)
    if respite == UNTIL_PAID:
        return None
    # Under a respite the lock waits for its end, and the warnings follow it.
    return max(min(times), respite) if respite else min(times)


def deadline_for(telegram_id: int) -> datetime | None:
    customers = bills.by_customer(bills.open_bills(telegram_id))
    return lock_deadline(customers[0]) if customers else None


def describe_deadline(at: datetime, now: datetime | None = None) -> str:
    """The lock time as the customer reads it: Tehran clock time and hours left."""
    now = now or datetime.now(bills.TEHRAN)
    hours = max(1, round((at - now).total_seconds() / 3600))
    when = at.astimezone(bills.TEHRAN).strftime("%Y-%m-%d %H:%M")
    if hours >= 48:
        return texts.LOCK_DEADLINE_DAYS.format(when=when, days=round(hours / 24))
    return texts.LOCK_DEADLINE.format(when=when, hours=hours)


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
    """A failed send must never undo a lock that already happened, but it must
    not vanish either: losing the notice silently is how a customer ends up
    locked out with no idea why."""
    try:
        await bot.send_message(chat_id, text, **kwargs)
    except Exception as exc:
        logger.error(f"could not notify {chat_id}: {type(exc).__name__}: {exc}")


async def _tell_superadmins(bot: Bot, text: str) -> None:
    for superadmin_id in settings.superadmin_id_list:
        await _tell(bot, superadmin_id, text)


async def _flag_on_panel(telegram_id: int, username: str, reason: str | None) -> bool:
    """Tell the panel a lock went on or came off, so its login page can say why
    instead of "wrong password". Best effort: the lock itself is the password
    change, and a panel that hasn't been updated yet simply doesn't know."""
    try:
        await nexra_panel.set_suspension(telegram_id, username, reason)
        return True
    except NexraPanelError as exc:
        logger.warning(f"could not flag {username} as {reason or 'unlocked'} on the panel: {exc}")
        return False


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
        await _flag_on_panel(telegram_id, username, reason)
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


async def unlock(
    bot: Bot, telegram_id: int, *, reason: str | None = None, note: str = ""
) -> list[str]:
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
        await _flag_on_panel(telegram_id, row["username"], None)
        restored.append(row["username"])

    if not restored:
        return []

    await _tell(bot, telegram_id, texts.UNSUSPENDED_NOTICE + note)
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


def _warned_stage(telegram_id: int, deadline: datetime) -> int | None:
    """The smallest warning stage already sent for this deadline, if any."""
    stored = db.get_setting(f"lock_warning:{telegram_id}")
    if not stored:
        return None
    at, _, stage = stored.rpartition("|")
    if at != deadline.isoformat():
        return None  # sent for an earlier deadline, which has since been paid
    try:
        return int(stage)
    except ValueError:
        return None


async def warn_before_lock(bot: Bot, customer: bills.Customer, now: datetime) -> None:
    """Warn once at each of WARNING_HOURS before this customer's panels lock."""
    deadline = lock_deadline(customer)
    if deadline is None or deadline <= now:
        return
    hours_left = (deadline - now).total_seconds() / 3600
    due_stages = [h for h in WARNING_HOURS if hours_left <= h]
    if not due_stages:
        return
    # Only the nearest stage: a bot that was down for the 12-hour one shouldn't
    # send it and the 2-hour one back to back.
    stage = min(due_stages)
    sent = _warned_stage(customer.telegram_id, deadline)
    if sent is not None and sent <= stage:
        return

    weekly = [b for b in customer.bills if b.kind == "weekly"]
    await _tell(
        bot,
        customer.telegram_id,
        texts.LOCK_WARNING.format(
            panels="، ".join(b.username for b in weekly),
            amount=sum(b.amount for b in weekly),
            deadline=describe_deadline(deadline, now),
        ),
        reply_markup=keyboards.suspended_kb(),
    )
    # Stamped either way, like every other reminder: a blocked chat must not be
    # retried on every tick, and the failure is already in the log.
    db.set_setting(f"lock_warning:{customer.telegram_id}", f"{deadline.isoformat()}|{stage}")


async def _sync_existing_to_panel() -> None:
    """Once: tell the panel about every lock placed before it could be told."""
    if db.get_setting(_PANEL_SYNC_KEY):
        return
    ok = True
    for row in db.list_suspensions():
        ok &= await _flag_on_panel(row["telegram_id"], row["username"], row["reason"])
    if ok:
        db.set_setting(_PANEL_SYNC_KEY, datetime.now(timezone.utc).isoformat())


async def tick(bot: Bot) -> None:
    """One sweep: warn whoever is about to run out of grace, lock whoever has,
    unlock whoever has paid."""
    cutoff()  # make sure the start line exists before anything is judged against it
    await _sync_existing_to_panel()

    now = datetime.now(bills.TEHRAN)
    for customer in bills.by_customer(bills.open_bills()):
        if customer.telegram_id is None:
            continue
        if locking_bills(customer, now):
            await lock_panels(
                bot,
                customer.telegram_id,
                total=customer.total,
                count=len(customer.bills),
            )
        elif not db.list_suspensions(customer.telegram_id):
            await warn_before_lock(bot, customer, now)

    # Locks the rule put on come off as soon as the weekly credit is settled.
    for row in db.list_suspensions(reason="unpaid"):
        if not owes_weekly(row["telegram_id"]):
            await unlock(bot, row["telegram_id"], reason="unpaid")
