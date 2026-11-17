"""Usage forecasting: how fast a panel is burning traffic and when it runs out.

Remaining traffic alone can't tell you consumption, because topping a panel up
also raises it. Since a grant raises the granted total by exactly the same
amount, consumption over a window is recoverable as:

    used = (remaining_then - remaining_now) + (granted_now - granted_then)

Daily snapshots of both numbers are taken by the hourly warning scan.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from . import keyboards, texts
from .. import db
from ..config import settings
from ..services.nexra_panel import nexra_panel
from ..units import bytes_to_gb

logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo("Asia/Tehran")
WINDOW_DAYS = 7
RUN_HOUR = 10
# Keep a little more than the window so a missed day doesn't empty the history.
RETENTION_DAYS = 30


def today_stamp() -> str:
    return datetime.now(TEHRAN).strftime("%Y-%m-%d")


def forecast_for(username: str, remaining_bytes: int) -> dict | None:
    """Average daily usage and days remaining, or None if there isn't enough
    history yet to say anything honest."""
    since = (datetime.now(TEHRAN) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    history = db.get_traffic_history(username, since)
    if len(history) < 2:
        return None

    first, last = history[0], history[-1]
    span_days = (
        datetime.strptime(last["date"], "%Y-%m-%d") - datetime.strptime(first["date"], "%Y-%m-%d")
    ).days
    if span_days < 1:
        return None

    used = (first["traffic_bytes"] - last["traffic_bytes"]) + (
        last["initial_bytes"] - first["initial_bytes"]
    )
    # Returned traffic from deleted users can push this negative; that isn't
    # consumption, it's a refund.
    used = max(0, used)

    daily = used / span_days
    days_left = int(remaining_bytes // daily) if daily > 0 else None

    return {
        "span_days": span_days,
        "used_gb": bytes_to_gb(used),
        "daily_gb": bytes_to_gb(daily),
        "days_left": days_left,
    }


def render(username: str, remaining_bytes: int) -> tuple[str, bool] | None:
    """The forecast message for one panel, plus whether it warrants a buy button."""
    data = forecast_for(username, remaining_bytes)
    remaining_gb = bytes_to_gb(remaining_bytes)

    if data is None:
        return texts.FORECAST_NO_DATA.format(username=username, remaining_gb=remaining_gb), False

    if data["days_left"] is None:
        return (
            texts.FORECAST_NO_USAGE.format(username=username, remaining_gb=remaining_gb),
            False,
        )

    return (
        texts.FORECAST_BODY.format(
            username=username,
            span_days=data["span_days"],
            used_gb=data["used_gb"],
            daily_gb=data["daily_gb"],
            remaining_gb=remaining_gb,
            days_left=data["days_left"],
        ),
        True,
    )


# A daily forecast for every panel was most of what the bot sent, and buried the
# messages that matter. It now goes out unasked only for a panel that will run
# out within this many days, once per decline; the menu button still shows the
# full forecast whenever someone wants it.
ALERT_DAYS = 3


def _alert_key(username: str) -> str:
    return f"forecast_alerted:{username}"


async def send_daily_forecasts(bot: Bot) -> int:
    """Warn each owner, in one message, about the panels about to run dry."""
    try:
        admins = await nexra_panel.list_all_admins()
    except Exception as exc:
        logger.warning(f"forecast run skipped: {exc}")
        return 0

    due: dict[int, list[tuple[str, str]]] = {}
    for admin in admins:
        username, telegram_id = admin.get("username"), admin.get("telegram_id")
        if not username or not telegram_id or not admin.get("is_active", True):
            continue
        data = forecast_for(username, admin.get("traffic") or 0)
        running_out = bool(data and data["days_left"] is not None and data["days_left"] <= ALERT_DAYS)
        if not running_out:
            # Topped up, or slowed down: the next decline may warn again.
            if db.get_setting(_alert_key(username)):
                db.set_setting(_alert_key(username), "")
            continue
        if db.get_setting(_alert_key(username)):
            continue  # already warned on this decline
        rendered = render(username, admin.get("traffic") or 0)
        if rendered is None:
            continue
        due.setdefault(telegram_id, []).append((username, rendered[0]))

    sent = 0
    for telegram_id, panels in due.items():
        try:
            await bot.send_message(
                telegram_id,
                texts.FORECAST_ALERT_TITLE + "\n\n".join(body for _, body in panels),
                reply_markup=keyboards.topup_panels_kb([name for name, _ in panels]),
            )
            sent += 1
        except Exception:
            pass
        # Stamped either way, so a blocked chat isn't retried every day.
        for name, _ in panels:
            db.set_setting(_alert_key(name), today_stamp())
    return sent


async def tick(bot: Bot) -> None:
    now = datetime.now(TEHRAN)
    if now.hour != RUN_HOUR:
        return
    stamp = now.strftime("%Y-%m-%d")
    if db.get_setting("forecast_sent_date") == stamp:
        return

    count = await send_daily_forecasts(bot)
    db.set_setting("forecast_sent_date", stamp)
    db.prune_traffic_history((now - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d"))
    logger.info(f"forecast alerts sent: {count}")


async def run_forecast_scheduler(bot: Bot) -> None:
    while True:
        try:
            await tick(bot)
        except Exception as exc:
            logger.error(f"forecast scheduler failed: {exc}")
        await asyncio.sleep(600)
