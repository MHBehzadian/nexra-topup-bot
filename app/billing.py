"""Money movement between a person's wallet and their panels' weekly debts."""

from __future__ import annotations

from . import db


def apply_wallet_to_debts(telegram_id: int) -> list[dict]:
    """Pay down this person's outstanding debts from their wallet, oldest panel
    first, spending only what the wallet actually holds.

    Runs both at weekly settlement and the moment a wallet top-up is approved, so
    money that arrives after the reminder still clears the debt straight away
    instead of waiting a whole week.

    Returns one entry per debt touched: {username, paid, remaining}.
    """
    results: list[dict] = []
    for debt in db.list_outstanding_debts():
        if debt["telegram_id"] != telegram_id:
            continue
        if db.get_wallet_balance(telegram_id) <= 0:
            break
        paid = db.drain_wallet(telegram_id, debt["amount"])
        if paid <= 0:
            continue
        remaining = db.reduce_debt(debt["username"], paid)
        results.append({"username": debt["username"], "paid": paid, "remaining": remaining})
    return results
