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

    async def get_admin(self, telegram_id: int) -> dict | None:
        async with httpx.AsyncClient(
            base_url=self._base_url, headers=self._headers, timeout=15.0
        ) as client:
            resp = await client.get(f"/bot/admin/{telegram_id}")
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise NexraPanelError(f"{resp.status_code}: {resp.text}")
        return resp.json()["data"]

    async def topup(self, telegram_id: int, added_gb: float) -> dict:
        async with httpx.AsyncClient(
            base_url=self._base_url, headers=self._headers, timeout=15.0
        ) as client:
            resp = await client.post(
                "/bot/admin/topup",
                json={"telegram_id": telegram_id, "added_gb": added_gb},
            )
        if resp.status_code >= 400:
            raise NexraPanelError(f"{resp.status_code}: {resp.text}")
        return resp.json()["data"]

    async def change_password(self, telegram_id: int, new_password: str) -> dict:
        async with httpx.AsyncClient(
            base_url=self._base_url, headers=self._headers, timeout=15.0
        ) as client:
            resp = await client.post(
                "/bot/admin/change-password",
                json={"telegram_id": telegram_id, "new_password": new_password},
            )
        if resp.status_code >= 400:
            raise NexraPanelError(f"{resp.status_code}: {resp.text}")
        return resp.json()["data"]

    async def get_all_credentials(self) -> list[dict]:
        async with httpx.AsyncClient(
            base_url=self._base_url, headers=self._headers, timeout=15.0
        ) as client:
            resp = await client.get("/bot/admins/credentials")
        if resp.status_code >= 400:
            raise NexraPanelError(f"{resp.status_code}: {resp.text}")
        return resp.json()["data"]

    async def sync_telegram_ids(self) -> dict:
        async with httpx.AsyncClient(
            base_url=self._base_url, headers=self._headers, timeout=30.0
        ) as client:
            resp = await client.post("/bot/admins/sync-telegram-ids")
        if resp.status_code >= 400:
            raise NexraPanelError(f"{resp.status_code}: {resp.text}")
        return resp.json()["data"]


nexra_panel = NexraPanelClient()
