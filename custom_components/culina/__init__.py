"""Culina: the kitchen speaker follows the recipe you are cooking."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CulinaApi, CulinaApiError, CulinaAuthError
from .const import CONF_TOKEN
from .coordinator import CulinaCoordinator

PLATFORMS = [Platform.SENSOR]

type CulinaConfigEntry = ConfigEntry[CulinaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: CulinaConfigEntry) -> bool:
    api = CulinaApi(async_get_clientsession(hass), entry.data[CONF_TOKEN])
    coordinator = CulinaCoordinator(hass, entry, api)
    try:
        await coordinator.async_setup()
    except CulinaAuthError as err:
        raise ConfigEntryAuthFailed from err
    except (CulinaApiError, TimeoutError) as err:
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady(f"Culina is not reachable: {err}") from err
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CulinaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: CulinaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
