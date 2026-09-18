"""The cooking session sensor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CulinaConfigEntry
from .const import DOMAIN, STATE_COOKING, STATE_IDLE, STATE_PAUSED
from .coordinator import CulinaCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: CulinaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([CulinaCookingSensor(entry.runtime_data, entry)])


class CulinaCookingSensor(CoordinatorEntity[CulinaCoordinator], SensorEntity):
    """idle, cooking or paused, with the recipe and the active steps as attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "cooking_session"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [STATE_IDLE, STATE_COOKING, STATE_PAUSED]

    def __init__(self, coordinator: CulinaCoordinator, entry: CulinaConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_cooking_session"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Culina",
            manufacturer="Culina",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://culina.cloud",
        )

    @property
    def native_value(self) -> str:
        return self.coordinator.data.state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        recipe = data.recipe
        return {
            "recipe_id": data.session.recipe_id if data.session else None,
            "recipe": recipe.title if recipe else None,
            "cuisine": recipe.cuisine_id if recipe else None,
            "cuisine_name": recipe.cuisine_name if recipe else None,
            "elapsed_seconds": round(data.elapsed) if data.session else None,
            "remaining_seconds": (
                round(max(0.0, recipe.total_duration - data.elapsed)) if recipe and data.session else None
            ),
            "ends_at": data.ends_at.isoformat() if data.ends_at else None,
            "active_steps": [step.name for step in data.active],
            "active_step_descriptions": [step.description for step in data.active],
            "hands_off": all(step.hands_off for step in data.active) if data.active else None,
        }
