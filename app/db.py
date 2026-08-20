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


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """Add a column to an already-created table. There are no migrations here,
    so this is what lets an existing deployment pick up new columns on restart."""
    existing = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS password_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_telegram_id INTEGER NOT NULL,
                admin_username TEXT,
                new_password TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                applied_at TEXT,
                applied_by INTEGER
            )
            """
        )
        # 'topup' = buying traffic; 'settlement' = paying off a weekly-credit debt.
        _ensure_column(conn, "topup_requests", "kind", "TEXT NOT NULL DEFAULT 'topup'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_payment (
                username TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Wallet belongs to the person, not the panel: one human with several
        # panels tops up once and spends it across all of them.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wallets (
                telegram_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        # Money belongs to the person, so the wallet is keyed by Telegram ID —
        # unlike debts, which are per-panel because traffic is per-panel.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wallets (
                telegram_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS debts (
                username TEXT PRIMARY KEY,
                telegram_id INTEGER,
                amount INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS traffic_warnings (
                username TEXT PRIMARY KEY,
                last_bucket TEXT NOT NULL,
                notified_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tutorials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content_type TEXT NOT NULL,
                text TEXT,
                file_id TEXT,
                created_at TEXT NOT NULL
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
    kind: str = "topup"


def create_request(
    *,
    admin_telegram_id: int,
    admin_username: str | None,
    requested_gb: float,
    toman_amount: int,
    receipt_path: str,
    kind: str = "topup",
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO topup_requests
                (admin_telegram_id, admin_username, requested_gb, toman_amount, receipt_path,
                 status, created_at, kind)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (admin_telegram_id, admin_username, requested_gb, toman_amount, receipt_path, now, kind),
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


def get_setting(key: str) -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO bot_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


@dataclass
class PasswordRequest:
    id: int
    admin_telegram_id: int
    admin_username: str | None
    new_password: str
    status: str
    created_at: str
    applied_at: str | None
    applied_by: int | None


def create_password_request(
    *, admin_telegram_id: int, admin_username: str | None, new_password: str
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO password_requests
                (admin_telegram_id, admin_username, new_password, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (admin_telegram_id, admin_username, new_password, now),
        )
        return cur.lastrowid


def get_password_request(request_id: int) -> PasswordRequest | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM password_requests WHERE id = ?", (request_id,)
        ).fetchone()
        return PasswordRequest(**dict(row)) if row else None


def mark_password_applied(request_id: int, *, applied_by: int | None) -> bool:
    """Atomically flip a pending password request to applied.

    Returns False (no-op) if it was already applied — the guard against a
    double-tapped confirm re-sending the panel update.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE password_requests
            SET status = 'applied', applied_at = ?, applied_by = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now, applied_by, request_id),
        )
        return cur.rowcount == 1


def revert_password_request(request_id: int) -> None:
    """Roll back to pending if the panel API call failed after being marked applied."""
    with _connect() as conn:
        conn.execute(
            "UPDATE password_requests SET status = 'pending', applied_at = NULL, applied_by = NULL WHERE id = ?",
            (request_id,),
        )


def get_wallet_balance(telegram_id: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT balance FROM wallets WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return row["balance"] if row else 0


def add_wallet_balance(telegram_id: int, amount: int) -> int:
    """Credit the wallet and return the new balance."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO wallets (telegram_id, balance, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                balance = balance + excluded.balance,
                updated_at = excluded.updated_at
            """,
            (telegram_id, amount, now),
        )
        row = conn.execute(
            "SELECT balance FROM wallets WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return row["balance"]


def spend_wallet(telegram_id: int, amount: int) -> bool:
    """Deduct the full amount, or nothing at all if the balance won't cover it.

    The balance check and the write happen in one statement so two concurrent
    spends can't both pass a check that only one of them could afford.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE wallets SET balance = balance - ?, updated_at = ? "
            "WHERE telegram_id = ? AND balance >= ?",
            (amount, now, telegram_id, amount),
        )
        return cur.rowcount == 1


def drain_wallet(telegram_id: int, up_to: int) -> int:
    """Spend as much of `up_to` as the wallet holds; returns the amount taken."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT balance FROM wallets WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        available = row["balance"] if row else 0
        taken = min(available, up_to)
        if taken > 0:
            conn.execute(
                "UPDATE wallets SET balance = balance - ?, updated_at = ? WHERE telegram_id = ?",
                (taken, now, telegram_id),
            )
        return taken


def is_weekly_enabled(username: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT enabled FROM weekly_payment WHERE username = ?", (username,)
        ).fetchone()
        return bool(row["enabled"]) if row else False


def set_weekly_enabled(username: str, enabled: bool) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO weekly_payment (username, enabled) VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET enabled = excluded.enabled
            """,
            (username, 1 if enabled else 0),
        )


def list_weekly_enabled() -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT username FROM weekly_payment WHERE enabled = 1").fetchall()
        return [r["username"] for r in rows]


def get_debt(username: str) -> int:
    with _connect() as conn:
        row = conn.execute("SELECT amount FROM debts WHERE username = ?", (username,)).fetchone()
        return row["amount"] if row else 0


def add_debt(username: str, telegram_id: int, amount: int) -> int:
    """Add to what this panel owes and return the new total."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO debts (username, telegram_id, amount, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                amount = amount + excluded.amount,
                telegram_id = excluded.telegram_id,
                updated_at = excluded.updated_at
            """,
            (username, telegram_id, amount, now),
        )
        row = conn.execute("SELECT amount FROM debts WHERE username = ?", (username,)).fetchone()
        return row["amount"]


def reduce_debt(username: str, amount: int) -> int:
    """Pay part of a debt down (never below zero); returns what's still owed."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE debts SET amount = MAX(0, amount - ?), updated_at = ? WHERE username = ?",
            (amount, now, username),
        )
        row = conn.execute("SELECT amount FROM debts WHERE username = ?", (username,)).fetchone()
        return row["amount"] if row else 0


def clear_debt(username: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE debts SET amount = 0, updated_at = ? WHERE username = ?", (now, username)
        )


def list_outstanding_debts() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT username, telegram_id, amount FROM debts WHERE amount > 0 ORDER BY username"
        ).fetchall()
        return [dict(r) for r in rows]


def get_warning_bucket(username: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT last_bucket FROM traffic_warnings WHERE username = ?", (username,)
        ).fetchone()
        return row["last_bucket"] if row else None


def set_warning_bucket(username: str, bucket: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO traffic_warnings (username, last_bucket, notified_at) VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                last_bucket = excluded.last_bucket,
                notified_at = excluded.notified_at
            """,
            (username, bucket, now),
        )


def clear_warning_bucket(username: str) -> None:
    """Called once a panel is topped back up, so the next drop warns again."""
    with _connect() as conn:
        conn.execute("DELETE FROM traffic_warnings WHERE username = ?", (username,))


def list_known_users() -> list[int]:
    """Telegram IDs of everyone who has ever started the bot (broadcast targets)."""
    with _connect() as conn:
        rows = conn.execute("SELECT telegram_id FROM bot_users").fetchall()
        return [r["telegram_id"] for r in rows]


@dataclass
class Tutorial:
    id: int
    title: str
    content_type: str
    text: str | None
    file_id: str | None
    created_at: str


def add_tutorial(
    *, title: str, content_type: str, text: str | None, file_id: str | None
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO tutorials (title, content_type, text, file_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, content_type, text, file_id, now),
        )
        return cur.lastrowid


def list_tutorials() -> list[Tutorial]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM tutorials ORDER BY created_at").fetchall()
        return [Tutorial(**dict(row)) for row in rows]


def get_tutorial(tutorial_id: int) -> Tutorial | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM tutorials WHERE id = ?", (tutorial_id,)
        ).fetchone()
        return Tutorial(**dict(row)) if row else None
