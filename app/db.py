"""SQLite persistence for top-up requests: audit trail + idempotency guard.

A single small table, plain sqlite3 (no ORM needed). The request must survive
bot restarts because manual card-to-card review can take hours/days, and the
atomic pending->approved/rejected flip is what stops a double-tapped Approve
button from double-crediting an admin's traffic balance.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .config import settings


def _connect() -> sqlite3.Connection:
    directory = os.path.dirname(settings.sqlite_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS topup_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_telegram_id INTEGER NOT NULL,
                admin_username TEXT,
                requested_gb REAL NOT NULL,
                toman_amount INTEGER NOT NULL,
                receipt_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                reviewed_by INTEGER,
                reject_reason TEXT,
                created_at TEXT NOT NULL,
                reviewed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
            """
        )


@dataclass
class TopupRequest:
    id: int
    admin_telegram_id: int
    admin_username: str | None
    requested_gb: float
    toman_amount: int
    receipt_path: str
    status: str
    reviewed_by: int | None
    reject_reason: str | None
    created_at: str
    reviewed_at: str | None


def create_request(
    *,
    admin_telegram_id: int,
    admin_username: str | None,
    requested_gb: float,
    toman_amount: int,
    receipt_path: str,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO topup_requests
                (admin_telegram_id, admin_username, requested_gb, toman_amount, receipt_path, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (admin_telegram_id, admin_username, requested_gb, toman_amount, receipt_path, now),
        )
        return cur.lastrowid


def get_request(request_id: int) -> TopupRequest | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM topup_requests WHERE id = ?", (request_id,)
        ).fetchone()
        return TopupRequest(**dict(row)) if row else None


def mark_reviewed(
    request_id: int, *, status: str, reviewed_by: int, reason: str | None = None
) -> bool:
    """Atomically flip a pending request to approved/rejected.

    Returns False (no-op) if the request was already handled — this is the
    guard against a redelivered/double-tapped callback double-crediting traffic.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE topup_requests
            SET status = ?, reviewed_by = ?, reviewed_at = ?, reject_reason = ?
            WHERE id = ? AND status = 'pending'
            """,
            (status, reviewed_by, now, reason, request_id),
        )
        return cur.rowcount == 1


def revert_to_pending(request_id: int) -> None:
    """Roll back to pending if the panel API call failed after approval was recorded locally."""
    with _connect() as conn:
        conn.execute(
            "UPDATE topup_requests SET status = 'pending', reviewed_by = NULL, reviewed_at = NULL WHERE id = ?",
            (request_id,),
        )


def user_exists(telegram_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM bot_users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return row is not None


def upsert_user(telegram_id: int, username: str | None, full_name: str | None) -> None:
    """Record/refresh a bot user's info — needed so a superadmin can message them later."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO bot_users (telegram_id, username, full_name, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                last_seen = excluded.last_seen
            """,
            (telegram_id, username, full_name, now, now),
        )


def list_pending_requests() -> list[TopupRequest]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM topup_requests WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [TopupRequest(**dict(row)) for row in rows]
