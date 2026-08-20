"""Background scanner that warns admins as a panel's traffic runs down.

Warnings fire once per threshold crossed, not once per scan — the bucket a panel
last warned at is stored, so an admin gets at most one message per step down
(100 → 50 → 10 → empty). Topping the panel back up clears the stored bucket, so
the same panel can warn again on its next decline.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from . import keyboards, texts
from .. import db
from ..config import settings
from ..services.nexra_panel import NexraPanelError, nexra_panel
from ..units import bytes_to_gb

logger = logging.getLogger(__name__)

# Ordered most-severe first; the first match wins.
_THRESHOLDS: list[tuple[str, float, str]] = [
    ("empty", 0.0, texts.WARN_EMPTY),
    ("10", 10.0, texts.WARN_10),
    ("50", 50.0, texts.WARN_50),
    ("100", 100.0, texts.WARN_100),
]


def bucket_for(remaining_gb: float) -> tuple[str, str] | None:
    """Which warning (if any) applies at this remaining volume."""
    if remaining_gb <= 0:
        return "empty", texts.WARN_EMPTY
    for name, limit, template in _THRESHOLDS:
        if name == "empty":
            continue
        if remaining_gb < limit:
            return name, template
    return None


async def scan_once(bot: Bot) -> int:
    """One pass over every panel. Returns how many warnings were sent."""
    try:
        admins = await nexra_panel.list_all_admins()
    except NexraPanelError as exc:
        logger.warning(f"traffic warning scan skipped: {exc}")
        return 0

    sent = 0
    for admin in admins:
        username = admin.get("username")
        telegram_id = admin.get("telegram_id")
        if not username or not telegram_id or not admin.get("is_active", True):
            continue

        remaining_gb = bytes_to_gb(admin.get("traffic"))
        result = bucket_for(remaining_gb)

        if result is None:
            # Comfortably above every threshold — rearm for the next decline.
            if db.get_warning_bucket(username):
                db.clear_warning_bucket(username)
            continue

        bucket, template = result
        if db.get_warning_bucket(username) == bucket:
            continue  # already warned at this step

        try:
            await bot.send_message(
                telegram_id,
                template.format(username=username, remaining_gb=remaining_gb),
                reply_markup=keyboards.topup_panel_kb(username),
            )
            sent += 1
        except Exception:
            # Blocked bot, deleted account, ... — record it anyway so a dead chat
            # doesn't get retried on every single scan.
            pass
        db.set_warning_bucket(username, bucket)

    return sent


async def run_warning_scanner(bot: Bot) -> None:
    while True:
        try:
            count = await scan_once(bot)
            if count:
                logger.info(f"sent {count} traffic warning(s)")
        except Exception as exc:  # never let one bad pass kill the loop
            logger.error(f"traffic warning scan failed: {exc}")
        await asyncio.sleep(settings.warning_scan_interval_seconds)
