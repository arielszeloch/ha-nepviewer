"""Minimal async client for the (unofficial) NEPViewer cloud API."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import aiohttp

from .const import API_BASE

_LOGGER = logging.getLogger(__name__)

PAGE_SIZE = 50


class NepViewerError(Exception):
    """Generic API error."""


class NepViewerAuthError(NepViewerError):
    """Login failed or token rejected."""


def make_sign(body: str) -> str:
    """Replicate the web app's request signature.

    The API does not currently validate it, but sending the same value the
    web app sends keeps us working if NEP starts checking it.
    """
    s = body.replace(" ", "").replace("\r", "").replace("\n", "").replace("e", "NEP")
    return hashlib.md5(s.encode("utf-8")).hexdigest().upper()


class NepViewerApi:
    """NEPViewer API client (one account)."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None

    async def login(self) -> None:
        data = await self._post(
            "v2/sign-in", {"account": self._email, "password": self._password}, auth=False
        )
        token = (data.get("tokenInfo") or {}).get("token")
        if not token:
            raise NepViewerAuthError("No token in sign-in response")
        self._token = token

    async def _post(
        self, path: str, payload: dict[str, Any], auth: bool = True, retry: bool = True
    ) -> dict[str, Any]:
        if auth and not self._token:
            await self.login()

        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "client": "web",
            "oem": "NEP",
            "app": "0",
            "lan": "3",
            "sign": make_sign(body),
        }
        if auth:
            headers["Authorization"] = self._token or ""

        try:
            async with self._session.post(
                API_BASE + path,
                data=body.encode("utf-8"),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 401:
                    if auth and retry:
                        _LOGGER.debug("Token rejected on %s, logging in again", path)
                        self._token = None
                        return await self._post(path, payload, auth, retry=False)
                    raise NepViewerAuthError(f"HTTP 401 on {path}")
                resp.raise_for_status()
                result = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise NepViewerError(f"{path}: {err}") from err
        except TimeoutError as err:
            raise NepViewerError(f"{path}: timeout") from err

        if not isinstance(result, dict):
            raise NepViewerError(f"{path}: unexpected response")
        code = result.get("code")
        if code != 200:
            msg = result.get("msg")
            if not auth:
                raise NepViewerAuthError(f"{path}: {code} {msg}")
            raise NepViewerError(f"{path}: {code} {msg}")
        return result.get("data") or {}

    async def get_sites(self) -> list[dict[str, Any]]:
        """All plants on the account (each with its SN list)."""
        sites: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self._post(
                "v2/site/listWithSN", {"page": {"page": page, "size": PAGE_SIZE}}
            )
            batch = data.get("list") or []
            sites.extend(batch)
            if len(batch) < PAGE_SIZE:
                return sites
            page += 1

    async def get_site_modules(self, sid: str) -> list[dict[str, Any]]:
        """Every inverter of a plant with per-panel (PV input) live data."""
        data = await self._post("v2/site/modules", {"sid": sid})
        return data.get("list") or []

    async def get_device_history(self, sid: str, sn: str, date: str) -> list[dict[str, Any]]:
        """Inverter readings for one day (YYYY-MM-DD), oldest first."""
        data = await self._post("v2/device/history", {"sid": sid, "sn": sn.lower(), "date": date})
        return data.get("list") or []
