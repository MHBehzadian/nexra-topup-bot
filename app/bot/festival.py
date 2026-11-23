"""The Black Friday festival, as the bot sees it.

Whether it is on, and until when, is set in one place: the festival section of
the Nexra panel's Settings. The bot reads it from there every minute and keeps
the last answer (in memory and in bot_settings), so a menu never waits on the
network and a panel outage doesn't switch the festival off mid-sale. The end
time is checked against the clock on every read, so the festival closes on
the minute even between two reads.

Purchases count from the moment the bot first sees a festival live. That start
is kept until the festival it belongs to is over, so moving the end time, or
switching it off and on again, doesn't reset anyone's count; only a new
festival, seen after the last one ended, starts a new count.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .. import db
from ..services.nexra_panel import nexra_panel

logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo("Asia/Tehran")

# One festival purchase: this much traffic, at the usual price per GB…
PACKAGE_GB = 1000
# …plus this much free, by how many they have bought before. Five purchases in
# all, 1500 GB of gifts between them.
BONUS_STEPS = (500, 400, 300, 200, 100)
# What a gift code is worth.
GIFT_CODE_GB = 200

POLL_SECONDS = 60

_STATE_KEY = "festival_state"
_START_KEY = "festival_started_at"
_SEEN_END_KEY = "festival_seen_end"

_state: dict | None = None


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        value = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _current() -> dict:
    global _state
    if _state is None:
        try:
            _state = json.loads(db.get_setting(_STATE_KEY) or "{}") or {}
        except ValueError:
            _state = {}
    return _state


def ends_at() -> datetime | None:
    return _parse(_current().get("ends_at"))


def is_live(now: datetime | None = None) -> bool:
    state = _current()
    if not state.get("enabled") or not state.get("active"):
        return False
    end = ends_at()
    return end is None or end > (now or datetime.now(timezone.utc))


def started_at() -> str:
    """When this festival's count began, as stored timestamps are written (UTC
    ISO), so it can be compared with them directly."""
    return db.get_setting(_START_KEY) or datetime.now(timezone.utc).isoformat()


def _track_start(now: datetime) -> None:
    start = db.get_setting(_START_KEY)
    seen_end = _parse(db.get_setting(_SEEN_END_KEY))
    # No festival seen yet, or the one we counted for is over: a new count.
    if start is None or (seen_end is not None and seen_end <= now):
        db.set_setting(_START_KEY, now.isoformat())
    end = _current().get("ends_at")
    if end:
        db.set_setting(_SEEN_END_KEY, end)


async def refresh() -> bool:
    """Ask the panel for the festival now. Keeps the last answer if it can't
    be reached. Returns whether it is live."""
    global _state
    try:
        festival = await nexra_panel.get_festival()
    except Exception as exc:
        logger.warning("festival lookup failed: %s", exc)
        return is_live()
    _state = {
        "enabled": bool(festival and festival.get("enabled")),
        "active": bool(festival and festival.get("active")),
        "ends_at": (festival or {}).get("ends_at"),
    }
    db.set_setting(_STATE_KEY, json.dumps(_state))
    now = datetime.now(timezone.utc)
    live = is_live(now)
    if live:
        _track_start(now)
    return live


async def run_festival_watcher(bot) -> None:  # noqa: ARG001 - same shape as the others
    while True:
        try:
            await refresh()
        except Exception as exc:  # never let the loop die
            logger.error("festival watcher failed: %s", exc)
        await asyncio.sleep(POLL_SECONDS)


# ------------------------------------------------------------------ offers


def purchases(telegram_id: int) -> tuple[int, int]:
    """(approved, waiting for review) festival purchases by this person."""
    since = started_at()
    return (
        db.count_festival_requests(telegram_id, since, "approved"),
        db.count_festival_requests(telegram_id, since, "pending"),
    )


def bonus_for(count: int) -> int | None:
    """The gift on the next purchase after `count` of them; None once used up."""
    return BONUS_STEPS[count] if count < len(BONUS_STEPS) else None


def describe_end() -> str:
    end = ends_at()
    if end is None:
        return "—"
    return end.astimezone(TEHRAN).strftime("%Y-%m-%d %H:%M")
