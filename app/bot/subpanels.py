"""Panels resellers ask for in the bot (routers/sub_panel.py) are only made
once their traffic is paid for, so none ever exists empty.

The request waits in db.pending_subpanels under the new username, and the
usual top-up runs with that username as its panel. Whichever way the money
comes in — wallet, weekly credit, or a card receipt the superadmin approves —
the payment goes through credit(), which makes the panel with the traffic
paid for instead of topping one up, and sends the login details.
"""

from __future__ import annotations

import logging

from aiogram import Bot

from . import texts
from .. import db
from ..config import settings
from ..services.nexra_panel import nexra_panel

logger = logging.getLogger(__name__)

# The least a new panel can be made with, whatever MIN_GB is set to.
MIN_GB = 200.0


def pending(telegram_id: int, username: str) -> db.PendingSubpanel | None:
    return db.get_pending_subpanel(username, telegram_id)


def min_gb_for(telegram_id: int, username: str) -> float:
    if pending(telegram_id, username):
        return max(settings.min_gb, MIN_GB)
    return settings.min_gb


def receipt_note(telegram_id: int, username: str) -> str:
    """A line for the superadmin's copy of a receipt, when it pays for a new panel."""
    spec = pending(telegram_id, username)
    if not spec:
        return ""
    return texts.SUBPANEL_RECEIPT_NOTE.format(
        kind=texts.SUBPANEL_KIND_PLAIN if spec.white_label else texts.SUBPANEL_KIND_NEXRA,
        source=spec.source,
    )


def credentials(spec: db.PendingSubpanel, traffic_gb: float, expiry: str | None) -> str:
    """The message the reseller forwards to their colleague."""
    expiry_line = texts.CREATE_ADMIN_EXPIRY_LINE.format(expiry=expiry[:10]) if expiry else ""
    if spec.white_label:
        return texts.SUBPANEL_SUCCESS_PLAIN.format(
            username=spec.username,
            password=spec.password,
            traffic_gb=traffic_gb,
            panel_url=texts.PANEL_URL_WHITE_LABEL,
            expiry_line=expiry_line,
        )
    return texts.CREATE_ADMIN_SUCCESS.format(
        username=spec.username,
        password=spec.password,
        traffic_gb=traffic_gb,
        panel_url=settings.panel_login_link,
        alarm_bot=settings.alarm_bot,
        manager_bot=settings.manager_bot,
        expiry_line=expiry_line,
    )


async def credit(bot: Bot, telegram_id: int, gb: float, username: str) -> dict:
    """Put paid-for traffic on a panel: top it up, or make it if it is one
    still waiting to be made. Raises NexraPanelError like nexra_panel.topup,
    so the callers' refund and retry paths hold for both."""
    spec = pending(telegram_id, username)
    if spec is None:
        return await nexra_panel.topup(telegram_id, gb, username=username)

    result = await nexra_panel.create_sub_admin(
        telegram_id=telegram_id,
        source_username=spec.source,
        username=spec.username,
        password=spec.password,
        white_label=spec.white_label,
        traffic_gb=gb,
    )
    db.delete_pending_subpanel(spec.username)
    db.set_user_linked(telegram_id, True)
    try:
        # Alone, so it can be forwarded to the colleague as it is.
        await bot.send_message(telegram_id, credentials(spec, gb, result.get("expiry_date")))
        await bot.send_message(
            telegram_id,
            texts.SUBPANEL_CREATED_NOTE.format(username=spec.username, traffic_gb=gb),
        )
    except Exception as exc:
        logger.error("could not send new panel %s to %s: %s", spec.username, telegram_id, exc)
    return result
