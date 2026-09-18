"""Culina bridge API: REST with a household token, and the Socket.IO feed."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
import socketio

from .const import BASE_URL

_LOGGER = logging.getLogger(__name__)


class CulinaApiError(Exception):
    """The API answered with an error or could not be reached."""


class CulinaAuthError(CulinaApiError):
    """The household token was rejected."""


class CulinaNotFoundError(CulinaApiError):
    """The recipe is not being cooked by this household (404)."""


class CulinaApi:
    """The three `/bridge/*` endpoints."""

    def __init__(
        self, session: aiohttp.ClientSession, token: str, base_url: str = BASE_URL
    ) -> None:
        self._session = session
        self._token = token
        self._base_url = base_url.rstrip("/")

    async def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            async with self._session.get(
                url,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status == 401:
                    raise CulinaAuthError("Invalid household token")
                if response.status == 404:
                    raise CulinaNotFoundError(path)
                if response.status >= 400:
                    raise CulinaApiError(f"{path} returned {response.status}")
                return await response.json()
        except aiohttp.ClientError as err:
            raise CulinaApiError(f"Could not reach {url}: {err}") from err

    async def household(self) -> dict[str, Any]:
        return await self._get("/bridge/household")

    async def sessions(self) -> dict[str, Any]:
        return await self._get("/bridge/cooking/sessions")

    async def recipe(self, recipe_id: str) -> dict[str, Any]:
        return await self._get(f"/bridge/recipes/{recipe_id}")


SessionHandler = Callable[[dict[str, Any]], Awaitable[None]]
ConnectHandler = Callable[[], Awaitable[None]]


class CulinaSocket:
    """Listen-only Socket.IO connection to the household's cooking room."""

    def __init__(
        self,
        token: str,
        *,
        on_connect: ConnectHandler,
        on_session_updated: SessionHandler,
        http_session: aiohttp.ClientSession | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        self._token = token
        self._base_url = base_url
        self._sio = socketio.AsyncClient(
            reconnection=True,
            reconnection_delay=1,
            reconnection_delay_max=60,
            http_session=http_session,
            logger=False,
            engineio_logger=False,
        )
        self._sio.on("connect", on_connect)
        self._sio.on("cookingSessionUpdated", on_session_updated)
        self._sio.on("disconnect", self._on_disconnect)
        self._sio.on("connect_error", self._on_connect_error)
        self._last_error: str | None = None

    @property
    def connected(self) -> bool:
        return self._sio.connected

    async def connect(self) -> None:
        try:
            await self._sio.connect(
                self._base_url,
                auth={"householdToken": self._token},
                transports=["websocket"],
                wait_timeout=15,
            )
        except socketio.exceptions.ConnectionError as err:
            detail = self._last_error or str(err)
            if "unauthorized" in detail.lower():
                raise CulinaAuthError("Invalid household token") from err
            raise CulinaApiError(f"Socket connect failed: {detail}") from err

    async def disconnect(self) -> None:
        await self._sio.disconnect()

    async def _on_disconnect(self, *args: Any) -> None:
        _LOGGER.debug("Culina socket disconnected: %s", args)

    async def _on_connect_error(self, data: Any) -> None:
        self._last_error = data.get("message") if isinstance(data, dict) else str(data)
        _LOGGER.warning("Culina socket connect error: %s", self._last_error)
