"""Backing up everything the bot owns: its database and the receipt images.

The database is snapshotted through sqlite's own backup API rather than copied
off disk, so the archive can't catch a half-written transaction while the bot is
serving requests.
"""

from __future__ import annotations

import os
import sqlite3
import tarfile
import tempfile
from datetime import datetime

from .config import settings

# Bots can upload documents up to 50 MB; stay clear of the edge.
MAX_UPLOAD_BYTES = 45 * 1024 * 1024


def _snapshot_db(destination: str) -> None:
    source = sqlite3.connect(settings.sqlite_path)
    target = sqlite3.connect(destination)
    try:
        with target:
            source.backup(target)
    finally:
        target.close()
        source.close()


def create_backup(stamp: str | None = None) -> tuple[str, bool]:
    """Build a .tar.gz of the bot's state.

    Returns (archive_path, media_included). Media is dropped — rather than the
    whole backup failing — when including it would exceed Telegram's upload cap,
    since the database is the part that actually can't be reconstructed.
    """
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    workdir = tempfile.mkdtemp(prefix="nexra-backup-")
    db_snapshot = os.path.join(workdir, "topup_bot.db")
    _snapshot_db(db_snapshot)

    media_dir = settings.media_dir
    media_size = 0
    if os.path.isdir(media_dir):
        for root, _, files in os.walk(media_dir):
            for name in files:
                media_size += os.path.getsize(os.path.join(root, name))

    include_media = os.path.isdir(media_dir) and media_size < MAX_UPLOAD_BYTES
    archive_path = os.path.join(workdir, f"nexra-bot-backup-{stamp}.tar.gz")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(db_snapshot, arcname="topup_bot.db")
        if include_media:
            tar.add(media_dir, arcname="media")

    return archive_path, include_media
