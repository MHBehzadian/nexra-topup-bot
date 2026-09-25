"""The day in one message, sent to the superadmins each night.

Everything here is already visible somewhere in the bot; the point is not having
to go and look. What is worth being told unprompted is what changed today and
what is waiting: money taken, receipts still unreviewed, debts past their date,
and panels about to run dry.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot

from . import bills, sales, texts
from .. import db
from ..config import settings
from ..services.nexra_panel import nexra_panel
from ..units import bytes_to_gb

logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo("Asia/Tehran")
LOW_TRAFFIC_GB = 50.0
MAX_LISTED_PANELS = 15


async def build(now: datetime | None = None) -> str:
    now = now or datetime.now(TEHRAN)
    text = texts.DIGEST_HEADER.format(day=sales.format_day(now.date()))

    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = db.list_sales_since(midnight.astimezone(timezone.utc).isoformat())
    if today:
        text += texts.DIGEST_SALES.format(
            amount=sum(s.amount for s in today),
            gb=round(sum(s.gb for s in today), 2),
            count=len(today),
        )
    else:
        text += texts.DIGEST_NO_SALES

    pending = db.list_pending_requests()
    if pending:
        text += texts.DIGEST_PENDING.format(
            count=len(pending), amount=sum(p.toman_amount for p in pending)
        )
    else:
        text += texts.DIGEST_NO_PENDING

    overdue = [b for b in bills.open_bills(now=now) if b.days_overdue(now) is not None]
    if overdue:
        text += texts.DIGEST_OVERDUE.format(
            count=len(overdue), amount=sum(b.amount for b in overdue)
        )
    else:
        text += texts.DIGEST_NO_OVERDUE

    # The only part that needs the panel; an outage costs this section, not the
    # whole message.
    try:
        admins = await nexra_panel.list_all_admins()
    except Exception as exc:
        logger.error(f"digest could not read the panels: {exc}")
        return text + texts.DIGEST_PANELS_UNAVAILABLE

    low = sorted(
        (
            (a["username"], bytes_to_gb(a.get("traffic")))
            for a in admins
            if a.get("is_active") and bytes_to_gb(a.get("traffic")) < LOW_TRAFFIC_GB
        ),
        key=lambda entry: entry[1],
    )
    if not low:
        return text + texts.DIGEST_NO_LOW_PANELS

    listed = "".join(
        texts.DIGEST_LOW_PANEL_LINE.format(username=username, remaining_gb=remaining)
        for username, remaining in low[:MAX_LISTED_PANELS]
    )
    text += texts.DIGEST_LOW_PANELS.format(threshold=LOW_TRAFFIC_GB, panels=listed)
    if len(low) > MAX_LISTED_PANELS:
        text += texts.DIGEST_MORE_PANELS.format(count=len(low) - MAX_LISTED_PANELS)
    return text


async def tick(bot: Bot) -> bool:
    now = datetime.now(TEHRAN)
    if now.hour != settings.digest_hour:
        return False
    # Stamped by day so a restart inside the hour doesn't send it twice.
    stamp = now.strftime("%Y-%m-%d")
    if db.get_setting("digest_date") == stamp:
        return False

    text = await build(now)
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(superadmin_id, text)
        except Exception as exc:
            logger.error(f"failed sending the digest to {superadmin_id}: {exc}")
    db.set_setting("digest_date", stamp)
    return True


async def run_digest_scheduler(bot: Bot) -> None:
    while True:
        try:
            if await tick(bot):
                logger.info("daily digest sent")
        except Exception as exc:  # a bad day must not kill the loop
            logger.error(f"digest scheduler failed: {exc}")
        await asyncio.sleep(300)
