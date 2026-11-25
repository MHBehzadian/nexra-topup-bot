"""Running commands on the servers the superadmin added (SSH).

The bot lives in Docker, so even "this server" is reached over SSH, the same
way as any other one. Only fixed command templates are run; anything typed in
the bot goes into them through shlex.quote.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

import asyncssh

log = logging.getLogger(__name__)


class RemoteError(Exception):
    pass


@dataclass
class Target:
    host: str
    port: int = 22
    username: str = "root"
    secret: str = ""  # password, or a private key (text) when it has "PRIVATE KEY" in it

    @property
    def is_key(self) -> bool:
        return "PRIVATE KEY" in self.secret

    @classmethod
    def from_row(cls, row) -> "Target":
        return cls(host=row["host"], port=int(row["port"]), username=row["username"], secret=row["secret"])


async def _connect(t: Target) -> asyncssh.SSHClientConnection:
    kw: dict = dict(host=t.host, port=t.port, username=t.username, known_hosts=None, connect_timeout=20,
                    keepalive_interval=30)
    if t.is_key:
        try:
            kw["client_keys"] = [asyncssh.import_private_key(t.secret)]
        except (asyncssh.KeyImportError, ValueError) as e:
            raise RemoteError(f"کلید خصوصی قابل خواندن نیست: {e}") from None
        kw["password"] = None
    else:
        kw["password"] = t.secret
        kw["client_keys"] = None
    try:
        return await asyncssh.connect(**kw)
    except asyncssh.PermissionDenied:
        raise RemoteError("نام کاربری یا رمز SSH اشتباه است") from None
    except (OSError, asyncssh.Error, asyncio.TimeoutError) as e:
        raise RemoteError(f"اتصال SSH به {t.host}:{t.port} برقرار نشد: {e or type(e).__name__}") from None


def _as_root(t: Target, command: str) -> str:
    """Everything here needs root; a non-root login goes through sudo."""
    if t.username == "root":
        return command
    return "sudo -n bash -c " + shlex.quote(command)


async def run(t: Target, command: str, timeout: float = 120) -> tuple[int, str]:
    """Run one command; returns (exit status, stdout+stderr)."""
    command = _as_root(t, command)
    conn = await _connect(t)
    try:
        r = await asyncio.wait_for(conn.run(command, check=False), timeout)
    except asyncio.TimeoutError:
        raise RemoteError(f"دستور بعد از {int(timeout)} ثانیه تمام نشد") from None
    finally:
        conn.close()
    out = (r.stdout or "") + (r.stderr or "")
    return (r.exit_status if r.exit_status is not None else 255), str(out)


async def stream(
    t: Target,
    command: str,
    on_progress: Callable[[list[str]], Awaitable[None]],
    timeout: float = 1200,
    every: float = 4.0,
) -> tuple[int, str]:
    """Run a long command (an install), calling on_progress with the output so
    far every few seconds. Returns (exit status, whole output)."""
    command = _as_root(t, command)
    conn = await _connect(t)
    lines: list[str] = []
    last = 0.0
    try:
        proc = await conn.create_process(command, stderr=asyncssh.STDOUT)

        async def pump() -> None:
            nonlocal last
            async for line in proc.stdout:
                lines.append(line.rstrip("\n"))
                if time.monotonic() - last >= every:
                    last = time.monotonic()
                    try:
                        await on_progress(lines)
                    except Exception:  # a failed message edit must not stop the install
                        log.debug("progress update failed", exc_info=True)

        try:
            await asyncio.wait_for(pump(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise RemoteError(f"بعد از {int(timeout // 60)} دقیقه تمام نشد") from None
        await proc.wait()
        code = proc.exit_status if proc.exit_status is not None else 255
    finally:
        conn.close()
    return code, "\n".join(lines)


async def fetch(t: Target, path: str, limit: int = 48 * 1024 * 1024) -> bytes:
    """Read a remote file (a backup) over SFTP."""
    conn = await _connect(t)
    try:
        async with conn.start_sftp_client() as sftp:
            attrs = await sftp.stat(path)
            if attrs.size and attrs.size > limit:
                raise RemoteError(f"فایل {path} بزرگ‌تر از حد ارسال در تلگرام است")
            async with sftp.open(path, "rb") as fh:
                return await fh.read()
    except asyncssh.SFTPError as e:
        raise RemoteError(f"خواندن {path}: {e}") from None
    finally:
        conn.close()
