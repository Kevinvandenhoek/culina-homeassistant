"""Follows the household's cooking session and drives the speaker."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from radios import RadioBrowser

from .api import CulinaApi, CulinaApiError, CulinaNotFoundError, CulinaSocket
from .radio import USER_AGENT, RadioStation, find_station, register_click
from .const import (
    CONF_ANNOUNCEMENTS,
    CONF_CUISINE_MEDIA,
    CONF_MEDIA_PLAYER,
    CONF_MUSIC,
    CONF_TOKEN,
    CONF_TTS_ENTITY,
    DOMAIN,
    ENDING_SOON_MIN_DURATION,
    ENDING_SOON_SECONDS,
    EVENT_ALL_DONE,
    EVENT_STEP_DONE,
    EVENT_STEP_ENDING_SOON,
    STATE_COOKING,
    STATE_IDLE,
    STATE_PAUSED,
)
from .session import (
    KIND_ALL_DONE,
    KIND_ENDING_SOON,
    Announcement,
    Recipe,
    Session,
    Step,
    active_steps,
    group_announcements,
    plan_announcements,
    render,
)

_LOGGER = logging.getLogger(__name__)

RECIPE_RETRY_SECONDS = 5
RECIPE_MAX_RETRIES = 6

_EVENT_FOR_KIND = {
    KIND_ENDING_SOON: EVENT_STEP_ENDING_SOON,
    KIND_ALL_DONE: EVENT_ALL_DONE,
}


@dataclass
class CookingState:
    """What the sensor shows."""

    state: str = STATE_IDLE
    session: Session | None = None
    recipe: Recipe | None = None
    elapsed: float = 0.0
    active: list[Step] = field(default_factory=list)
    ends_at: datetime | None = None


class CulinaCoordinator(DataUpdateCoordinator[CookingState]):
    """One per household token. Push only, nothing is polled."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: CulinaApi) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None)
        self.entry = entry
        self.api = api
        self.household: dict[str, Any] = {}
        self.templates: dict[str, str] = {}
        self.language: str | None = None
        self.session: Session | None = None
        self.recipe: Recipe | None = None
        self.skew_ms = 0.0
        self._timers: list[CALLBACK_TYPE] = []
        self._recipe_retry: CALLBACK_TYPE | None = None
        self._recipe_retries = 0
        self._music_started = False
        self._lock = asyncio.Lock()
        self._radio = RadioBrowser(user_agent=USER_AGENT, session=async_get_clientsession(hass))
        self._stations: dict[str, RadioStation | None] = {}
        self._socket = CulinaSocket(
            entry.data[CONF_TOKEN],
            on_connect=self._on_connect,
            on_session_updated=self._on_session_updated,
            http_session=async_get_clientsession(hass),
        )

    # Lifecycle

    async def async_setup(self) -> None:
        self.household = await self.api.household()
        self.templates = self.household.get("announcements") or {}
        self.language = (self.household.get("language") or {}).get("id")
        self.async_set_updated_data(self._snapshot())
        await self._socket.connect()

    async def async_shutdown(self) -> None:
        self._cancel_timers()
        self._cancel_recipe_retry()
        await self._socket.disconnect()
        await super().async_shutdown()

    @property
    def household_id(self) -> str | None:
        return self.household.get("householdId")

    # Socket handlers

    async def _on_connect(self) -> None:
        """Sessions live in the API's memory, so ask on every (re)connect."""
        try:
            data = await self.api.sessions()
        except CulinaApiError as err:
            _LOGGER.warning("Could not fetch cooking sessions: %s", err)
            return
        self._apply_server_now(data.get("serverNow"))
        sessions = data.get("sessions") or []
        async with self._lock:
            current = self._pick(sessions)
            if current is None:
                if self.session is not None:
                    await self._stop()
            else:
                await self._apply(current)

    async def _on_session_updated(self, payload: dict[str, Any]) -> None:
        self._apply_server_now(payload.get("serverNow"))
        session = payload.get("session")
        recipe_id = payload.get("recipeId")
        async with self._lock:
            if session is None:
                if self.session is None or (recipe_id and self.session.recipe_id != recipe_id):
                    return
                await self._stop()
            else:
                await self._apply(session)

    def _pick(self, sessions: list[dict[str, Any]]) -> dict[str, Any] | None:
        """One session at a time: the one we follow, else the most recently touched."""
        if not sessions:
            return None
        if self.session is not None:
            for item in sessions:
                if item.get("recipeId") == self.session.recipe_id:
                    return item
        return max(sessions, key=lambda item: item.get("updatedAt") or 0)

    # State changes, always under the lock

    async def _apply(self, data: dict[str, Any]) -> None:
        new = Session.from_api(data)
        previous = self.session
        self.session = new
        recipe_changed = previous is None or previous.recipe_id != new.recipe_id
        if recipe_changed:
            self._music_started = False
        if recipe_changed or self.recipe is None or self.recipe.id != new.recipe_id:
            await self._load_recipe(new.recipe_id)
        if not new.paused and not self._music_started:
            await self._start_music()
        self._reschedule()
        self._publish()

    async def _stop(self) -> None:
        self._cancel_timers()
        self._cancel_recipe_retry()
        had_music = self._music_started
        self.session = None
        self.recipe = None
        self._music_started = False
        if had_music:
            await self._stop_music()
        self._publish()

    async def _load_recipe(self, recipe_id: str) -> None:
        self._cancel_recipe_retry()
        try:
            data = await self.api.recipe(recipe_id)
        except CulinaNotFoundError:
            _LOGGER.debug("Recipe %s is not being cooked (404)", recipe_id)
            self.recipe = None
            return
        except CulinaApiError as err:
            _LOGGER.warning("Could not fetch recipe %s: %s", recipe_id, err)
            self.recipe = None
            self._schedule_recipe_retry()
            return
        self.recipe = Recipe.from_api(data)
        if self.recipe.translation_pending:
            self._schedule_recipe_retry()
        else:
            self._recipe_retries = 0

    def _schedule_recipe_retry(self) -> None:
        if self._recipe_retries >= RECIPE_MAX_RETRIES:
            return
        self._recipe_retries += 1
        self._recipe_retry = async_call_later(self.hass, RECIPE_RETRY_SECONDS, self._retry_recipe)

    async def _retry_recipe(self, _now: datetime) -> None:
        self._recipe_retry = None
        async with self._lock:
            if self.session is None:
                return
            await self._load_recipe(self.session.recipe_id)
            self._reschedule()
            self._publish()

    def _cancel_recipe_retry(self) -> None:
        if self._recipe_retry is not None:
            self._recipe_retry()
            self._recipe_retry = None

    # Clock

    def _apply_server_now(self, server_now: Any) -> None:
        if isinstance(server_now, (int, float)):
            self.skew_ms = server_now - time.time() * 1000

    def _server_now_ms(self) -> float:
        return time.time() * 1000 + self.skew_ms

    def _elapsed(self) -> float:
        if self.session is None:
            return 0.0
        return self.session.elapsed_at(self._server_now_ms())

    # Timers

    def _reschedule(self) -> None:
        self._cancel_timers()
        if self.session is None or self.session.paused or self.recipe is None:
            return
        elapsed = self._elapsed()
        plan = plan_announcements(
            self.recipe.steps,
            ending_soon_seconds=ENDING_SOON_SECONDS,
            ending_soon_min_duration=ENDING_SOON_MIN_DURATION,
        )
        for group in group_announcements(plan):
            delay = group[0].at - elapsed
            if delay <= 0:
                continue
            self._timers.append(async_call_later(self.hass, delay, partial(self._fire, group)))

    def _cancel_timers(self) -> None:
        for cancel in self._timers:
            cancel()
        self._timers = []

    async def _fire(self, group: list[Announcement], _now: datetime) -> None:
        async with self._lock:
            if self.session is None or self.session.paused or self.recipe is None:
                return
            texts = []
            for item in group:
                text = render(self.templates, item)
                texts.append(text)
                self.hass.bus.async_fire(
                    _EVENT_FOR_KIND.get(item.kind, EVENT_STEP_DONE),
                    {
                        "recipe_id": self.recipe.id,
                        "recipe": self.recipe.title,
                        "step": item.step.name if item.step else None,
                        "next_step": item.next_step.name if item.next_step else None,
                        "count": item.count,
                        "text": text,
                    },
                )
            if self.entry.options.get(CONF_ANNOUNCEMENTS, True):
                await self._speak(". ".join(texts))
            self._publish()

    # Speaker

    async def _speak(self, text: str) -> None:
        tts_entity = self.entry.options.get(CONF_TTS_ENTITY)
        if not tts_entity:
            return
        data: dict[str, Any] = {
            "entity_id": tts_entity,
            "media_player_entity_id": self.entry.data[CONF_MEDIA_PLAYER],
            "message": text,
            "cache": True,
        }
        if self.language:
            data["language"] = self.language
        try:
            await self.hass.services.async_call("tts", "speak", data, blocking=True)
        except HomeAssistantError as err:
            if "language" not in data:
                _LOGGER.warning("Announcement failed: %s", err)
                return
            _LOGGER.debug("Retrying announcement without language %s: %s", self.language, err)
            data.pop("language")
            try:
                await self.hass.services.async_call("tts", "speak", data, blocking=True)
            except HomeAssistantError as retry_err:
                _LOGGER.warning("Announcement failed: %s", retry_err)

    async def _start_music(self) -> None:
        """A mapping from the options wins; otherwise a radio station for the cuisine."""
        if not self.entry.options.get(CONF_MUSIC, True) or self.recipe is None:
            return
        cuisine_id = self.recipe.cuisine_id
        media = (self.entry.options.get(CONF_CUISINE_MEDIA) or {}).get(cuisine_id or "")
        station: RadioStation | None = None
        if media:
            content_id, content_type = media["media_content_id"], media["media_content_type"]
            what = f"mapped media for {cuisine_id}"
        else:
            station = await self._radio_station(cuisine_id)
            if station is None:
                _LOGGER.info("No music for cuisine %s", cuisine_id)
                return
            content_id, content_type = station.url, "music"
            what = f"radio station {station.name}"
        player = self.entry.data[CONF_MEDIA_PLAYER]
        try:
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": player,
                    "media_content_id": content_id,
                    "media_content_type": content_type,
                },
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Could not play %s on %s: %s", what, player, err)
            return
        _LOGGER.info("Playing %s on %s", what, player)
        self._music_started = True
        if station is not None:
            await register_click(station, browser=self._radio)
            return
        try:
            await self.hass.services.async_call(
                "media_player", "repeat_set", {"entity_id": player, "repeat": "all"}, blocking=True
            )
        except HomeAssistantError as err:
            _LOGGER.debug("Speaker %s does not repeat: %s", player, err)

    async def _radio_station(self, cuisine_id: str | None) -> RadioStation | None:
        if not cuisine_id:
            return None
        if cuisine_id not in self._stations:
            try:
                self._stations[cuisine_id] = await find_station(cuisine_id, browser=self._radio)
            except Exception as err:  # noqa: BLE001 - Radio Browser is best effort
                _LOGGER.warning("Radio Browser lookup for %s failed: %s", cuisine_id, err)
                return None
        return self._stations[cuisine_id]

    async def _stop_music(self) -> None:
        player = self.entry.data[CONF_MEDIA_PLAYER]
        try:
            await self.hass.services.async_call(
                "media_player", "repeat_set", {"entity_id": player, "repeat": "off"}, blocking=True
            )
        except HomeAssistantError:
            pass
        try:
            await self.hass.services.async_call(
                "media_player", "media_stop", {"entity_id": player}, blocking=True
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Could not stop music: %s", err)

    # Sensor data

    def _snapshot(self) -> CookingState:
        if self.session is None:
            return CookingState()
        elapsed = self._elapsed()
        steps = self.recipe.steps if self.recipe else ()
        ends_at = None
        if self.recipe and not self.session.paused:
            ends_at = dt_util.utcnow() + timedelta(seconds=max(0.0, self.recipe.total_duration - elapsed))
        return CookingState(
            state=STATE_PAUSED if self.session.paused else STATE_COOKING,
            session=self.session,
            recipe=self.recipe,
            elapsed=elapsed,
            active=active_steps(steps, elapsed),
            ends_at=ends_at,
        )

    def _publish(self) -> None:
        self.async_set_updated_data(self._snapshot())
