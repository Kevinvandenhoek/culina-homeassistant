"""Announcement and music volume, the same settings as in the options."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CulinaConfigEntry
from .const import CONF_ANNOUNCEMENT_VOLUME, CONF_MUSIC_VOLUME
from .entity import CulinaEntity

NUMBERS = (
    ("announcement_volume", CONF_ANNOUNCEMENT_VOLUME, "mdi:volume-high"),
    ("music_volume", CONF_MUSIC_VOLUME, "mdi:volume-medium"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: CulinaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(CulinaVolume(entry, key, option, icon) for key, option, icon in NUMBERS)


class CulinaVolume(CulinaEntity, NumberEntity):
    """Reads and writes one volume option, 0 to 100 percent. Empty means the
    speaker's own volume; clearing it is done in the options."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: CulinaConfigEntry, key: str, option: str, icon: str) -> None:
        super().__init__(entry, key)
        self._option = option
        self._attr_icon = icon

    @property
    def native_value(self) -> float | None:
        value = self.entry.options.get(self._option)
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        self.update_option(self._option, int(value))
