"""Culina: the kitchen speaker follows the recipe you are cooking."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER, ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

import logging

from .api import CulinaApi, CulinaApiError, CulinaAuthError
from .const import CONF_TOKEN
from .coordinator import CulinaCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
RADIO_BROWSER = "radio_browser"

type CulinaConfigEntry = ConfigEntry[CulinaCoordinator]


async def _async_ensure_radio_browser(hass: HomeAssistant) -> None:
    """The music plays through Home Assistant's Radio Browser integration.

    It needs no configuration, so add it when it is missing instead of asking
    the user to. Sonos refuses the bare stream URL that is the fallback.
    """
    if hass.config_entries.async_entries(RADIO_BROWSER):
        return
    try:
        result = await hass.config_entries.flow.async_init(
            RADIO_BROWSER, context={"source": SOURCE_USER}, data={}
        )
    except Exception as err:  # noqa: BLE001 - never block Culina on this
        _LOGGER.warning("Could not add the Radio Browser integration: %s", err)
        return
    if result.get("type") == "create_entry":
        _LOGGER.info("Added the Radio Browser integration for the cooking music")
    else:
        _LOGGER.warning("Radio Browser integration not added: %s", result.get("reason") or result.get("type"))


async def async_setup_entry(hass: HomeAssistant, entry: CulinaConfigEntry) -> bool:
    await _async_ensure_radio_browser(hass)
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
