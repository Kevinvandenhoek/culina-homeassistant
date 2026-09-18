"""Announcements and music on or off, the same settings as in the options."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CulinaConfigEntry
from .const import CONF_ANNOUNCEMENTS, CONF_MUSIC
from .entity import CulinaEntity

SWITCHES = (
    ("announcements", CONF_ANNOUNCEMENTS, "mdi:bullhorn"),
    ("music", CONF_MUSIC, "mdi:radio"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: CulinaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(CulinaSwitch(entry, key, option, icon) for key, option, icon in SWITCHES)


class CulinaSwitch(CulinaEntity, SwitchEntity):
    """Reads and writes one boolean option of the config entry."""

    def __init__(self, entry: CulinaConfigEntry, key: str, option: str, icon: str) -> None:
        super().__init__(entry, key)
        self._option = option
        self._attr_icon = icon

    @property
    def is_on(self) -> bool:
        return bool(self.entry.options.get(self._option, True))

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.update_option(self._option, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.update_option(self._option, False)
