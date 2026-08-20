"""HTTP client for calling Nexra Panel's bot-facing API (shared-secret auth)."""

from __future__ import annotations

import httpx

from ..config import settings


class NexraPanelError(Exception):
    pass


class NexraPanelClient:
    def __init__(self) -> None:
        self._base_url = settings.nexra_panel_api_url.rstrip("/")
        self._headers = {"X-Bot-Api-Key": settings.nexra_panel_bot_api_key}

    def _client(self, timeout: float = 15.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=timeout)

    @staticmethod
    def _ok(resp: httpx.Response) -> dict | list:
        if resp.status_code >= 400:
            raise NexraPanelError(f"{resp.status_code}: {resp.text}")
        return resp.json()["data"]

    async def get_admins(self, telegram_id: int) -> list[dict]:
        """Every panel this Telegram account owns — empty list if none."""
        async with self._client() as client:
            resp = await client.get(f"/bot/admin/{telegram_id}")
        if resp.status_code == 404:
            return []
        return self._ok(resp)

    async def get_admin(self, telegram_id: int) -> dict | None:
        """Their single panel, or None. Returns None when they own several, since
        no one panel is 'the' answer — callers needing that case use get_admins."""
        admins = await self.get_admins(telegram_id)
        return admins[0] if len(admins) == 1 else None

    async def list_all_admins(self) -> list[dict]:
        async with self._client(30.0) as client:
            resp = await client.get("/bot/admins")
        return self._ok(resp)

    async def topup(self, telegram_id: int, added_gb: float, username: str | None = None) -> dict:
        async with self._client() as client:
            resp = await client.post(
                "/bot/admin/topup",
                json={"telegram_id": telegram_id, "added_gb": added_gb, "username": username},
            )
        return self._ok(resp)

    async def grant(self, username: str, added_gb: float) -> dict:
        async with self._client() as client:
            resp = await client.post(
                "/bot/admin/grant", json={"username": username, "added_gb": added_gb}
            )
        return self._ok(resp)

    async def change_password(
        self, telegram_id: int, current_password: str, new_password: str, username: str | None = None
    ) -> dict:
        async with self._client() as client:
            resp = await client.post(
                "/bot/admin/change-password",
                json={
                    "telegram_id": telegram_id,
                    "current_password": current_password,
                    "new_password": new_password,
                    "username": username,
                },
            )
        return self._ok(resp)

    async def get_all_credentials(self) -> list[dict]:
        async with self._client() as client:
            resp = await client.get("/bot/admins/credentials")
        return self._ok(resp)

    async def sync_telegram_ids(self) -> dict:
        async with self._client(30.0) as client:
            resp = await client.post("/bot/admins/sync-telegram-ids")
        return self._ok(resp)


nexra_panel = NexraPanelClient()
