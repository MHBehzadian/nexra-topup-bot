"""The superadmin adding traffic to a panel, or taking it back, by hand.

Shared by every place that does it — the panels section and a customer's
profile card — so each change is written down and reported to the panel's
owner the same way wherever it was made.
"""

from __future__ import annotations

import logging

from aiogram import Bot

from . import sales, texts
from .. import db
from ..services.nexra_panel import DeductUnsupported, NexraPanelError, nexra_panel
from ..units import bytes_to_gb

logger = logging.getLogger(__name__)

ADD = "add"
SUB = "sub"


async def find_panel(username: str) -> dict | None:
    """One panel by its username, with its current numbers. Raises
    NexraPanelError if the panel can't be reached."""
    admins = await nexra_panel.list_all_admins()
    return next((a for a in admins if a.get("username") == username), None)


async def change(bot: Bot, username: str, gb: float, mode: str) -> tuple[bool, str]:
    """Add (ADD) or remove (SUB) `gb` gigabytes on one panel.

    Returns whether it worked and what to tell the superadmin.
    """
    try:
        if mode == ADD:
            result = await nexra_panel.grant(username, gb)
        else:
            result = await nexra_panel.deduct(username, gb)
    except DeductUnsupported:
        return False, texts.DEDUCT_TRAFFIC_UNSUPPORTED
    except NexraPanelError as exc:
        failed = texts.GRANT_FAILED if mode == ADD else texts.DEDUCT_TRAFFIC_FAILED
        return False, failed.format(error=exc)

    new_gb = bytes_to_gb(result.get("new_traffic_bytes"))
    owner = result.get("telegram_id")
    if mode == ADD:
        # More traffic: the low-traffic warnings already sent no longer apply.
        db.clear_warning_bucket(username)
    # No money changed hands either way, but it belongs in the panel's history.
    db.record_sale(
        telegram_id=owner,
        username=username,
        gb=gb if mode == ADD else -gb,
        amount=0,
        method=sales.GRANT if mode == ADD else sales.DEDUCT,
    )

    if mode == ADD:
        done = texts.GRANT_SUCCESS.format(added_gb=gb, username=username, new_gb=new_gb)
        notice = texts.GRANT_NOTIFY_ADMIN.format(username=username, added_gb=gb, new_gb=new_gb)
    else:
        done = texts.DEDUCT_TRAFFIC_SUCCESS.format(removed_gb=gb, username=username, new_gb=new_gb)
        notice = texts.DEDUCT_NOTIFY_ADMIN.format(username=username, removed_gb=gb, new_gb=new_gb)

    if owner:
        try:
            await bot.send_message(owner, notice)
        except Exception as exc:
            logger.warning("traffic change notice to %s not delivered: %s", owner, exc)
    return True, done
