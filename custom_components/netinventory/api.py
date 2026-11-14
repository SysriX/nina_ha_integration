"""Small async client for the NetInventory API (/api/ha/v1)."""
from __future__ import annotations

from typing import Any

import aiohttp


class NetInventoryError(Exception):
    """Communication or API error."""


class NetInventoryAuthError(NetInventoryError):
    """API key rejected."""


class NetInventoryApi:
    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, token: str,
                 ssl: bool = False, verify_ssl: bool = True) -> None:
        self._session = session
        self._token = token
        self._verify = verify_ssl
        self.base = f"{'https' if ssl else 'http'}://{host}:{port}"

    async def _call(self, method: str, path: str, data: dict | None = None, timeout: int = 20) -> Any:
        try:
            async with self._session.request(
                method, f"{self.base}/api/ha/v1{path}", json=data if method != "GET" else None,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=aiohttp.ClientTimeout(total=timeout), ssl=None if self._verify else False,
            ) as r:
                if r.status in (401, 403):
                    raise NetInventoryAuthError(await self._detail(r))
                if r.status >= 400:
                    raise NetInventoryError(f"HTTP {r.status}: {await self._detail(r)}")
                return await r.json()
        except NetInventoryError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise NetInventoryError(f"{self.base} not reachable: {err}") from err

    @staticmethod
    async def _detail(r: aiohttp.ClientResponse) -> str:
        try:
            d = await r.json()
            return str(d.get("detail") or d)
        except Exception:  # noqa: BLE001
            return await r.text()

    async def info(self) -> dict:
        return await self._call("GET", "/info")

    async def devices(self) -> dict:
        return await self._call("GET", "/geraete")

    async def wake(self, device_id: int) -> dict:
        return await self._call("POST", f"/geraete/{device_id}/wecken", {})

    async def command(self, device_id: int, command: str, value: Any = None) -> dict:
        return await self._call("POST", f"/geraete/{device_id}/befehl", {"befehl": command, "wert": value})

    async def check(self, device_id: int) -> dict:
        return await self._call("POST", f"/geraete/{device_id}/pruefen", {})

    async def scan(self, network_id: int | None = None) -> dict:
        return await self._call("POST", "/scan", {"netzwerk_id": network_id} if network_id else {}, timeout=900)
