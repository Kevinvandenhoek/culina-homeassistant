"""Base for the setting entities: they live on the Culina device and mirror the options."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from . import CulinaConfigEntry
from .const import DOMAIN


def device_info(entry: CulinaConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Culina",
        manufacturer="Culina",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://culina.cloud",
    )


class CulinaEntity(Entity):
    """An entity whose state is one option of the config entry."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: CulinaConfigEntry, key: str) -> None:
        self.entry = entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        # Options can also change through the options flow: refresh then too.
        self.async_on_remove(self.entry.add_update_listener(self._async_entry_updated))

    async def _async_entry_updated(self, hass: HomeAssistant, entry: CulinaConfigEntry) -> None:
        """Update listeners are awaited by Home Assistant, so this must be a coroutine."""
        self.async_write_ha_state()

    def update_option(self, option: str, value: Any) -> None:
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, option: value}
        )
        self.async_write_ha_state()
