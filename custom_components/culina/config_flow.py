"""Config and options flow for Culina."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    MediaSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import CulinaApi, CulinaApiError, CulinaAuthError
from .const import (
    CONF_ANNOUNCEMENTS,
    CONF_CUISINE_MEDIA,
    CONF_MEDIA_PLAYER,
    CONF_MUSIC,
    CONF_TOKEN,
    CONF_TTS_ENTITY,
    DOMAIN,
)
from .cuisines import CUISINES

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
CUISINE_OPTIONS = [
    SelectOptionDict(value=cuisine_id, label=name)
    for cuisine_id, name in sorted(CUISINES.items(), key=lambda item: item[1])
]


async def _validate_token(hass, token: str) -> tuple[dict[str, Any] | None, str | None]:
    """Return (household, None) or (None, error key)."""
    try:
        household = await CulinaApi(async_get_clientsession(hass), token).household()
    except CulinaAuthError:
        return None, "invalid_auth"
    except CulinaApiError:
        return None, "cannot_connect"
    return household, None


class CulinaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Token plus speaker. Everything else lives in the options."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            household, error = await _validate_token(self.hass, token)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(household["householdId"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=household.get("name") or "Culina",
                    data={CONF_TOKEN: token, CONF_MEDIA_PLAYER: user_input[CONF_MEDIA_PLAYER]},
                    options={CONF_ANNOUNCEMENTS: True, CONF_MUSIC: True, CONF_CUISINE_MEDIA: {}},
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
                vol.Required(CONF_MEDIA_PLAYER): EntitySelector(
                    EntitySelectorConfig(domain="media_player")
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            household, error = await _validate_token(self.hass, token)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(household["householdId"])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_TOKEN: token}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CulinaOptionsFlow()


class CulinaOptionsFlow(OptionsFlow):
    """A menu that loops until Save, so several cuisines can be added in one go."""

    def __init__(self) -> None:
        self._options: dict[str, Any] | None = None

    @property
    def options(self) -> dict[str, Any]:
        if self._options is None:
            current = self.config_entry.options
            self._options = {
                **current,
                CONF_CUISINE_MEDIA: dict(current.get(CONF_CUISINE_MEDIA) or {}),
            }
        return self._options

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        menu = ["settings", "add_music"]
        if self.options[CONF_CUISINE_MEDIA]:
            menu.append("remove_music")
        menu.append("done")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self.options[CONF_TTS_ENTITY] = user_input.get(CONF_TTS_ENTITY)
            self.options[CONF_ANNOUNCEMENTS] = user_input[CONF_ANNOUNCEMENTS]
            self.options[CONF_MUSIC] = user_input[CONF_MUSIC]
            return await self.async_step_init()
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TTS_ENTITY,
                    description={"suggested_value": self.options.get(CONF_TTS_ENTITY)},
                ): EntitySelector(EntitySelectorConfig(domain="tts")),
                vol.Required(
                    CONF_ANNOUNCEMENTS, default=self.options.get(CONF_ANNOUNCEMENTS, True)
                ): BooleanSelector(),
                vol.Required(CONF_MUSIC, default=self.options.get(CONF_MUSIC, True)): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)

    async def async_step_add_music(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            media = user_input["media"]
            self.options[CONF_CUISINE_MEDIA][user_input["cuisine"]] = {
                "media_content_id": media["media_content_id"],
                "media_content_type": media["media_content_type"],
            }
            return await self.async_step_init()
        schema = vol.Schema(
            {
                vol.Required("cuisine"): SelectSelector(
                    SelectSelectorConfig(options=CUISINE_OPTIONS, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required("media"): MediaSelector(),
            }
        )
        return self.async_show_form(step_id="add_music", data_schema=schema)

    async def async_step_remove_music(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            for cuisine_id in user_input["cuisines"]:
                self.options[CONF_CUISINE_MEDIA].pop(cuisine_id, None)
            return await self.async_step_init()
        options = [
            SelectOptionDict(value=cuisine_id, label=CUISINES.get(cuisine_id, cuisine_id))
            for cuisine_id in sorted(self.options[CONF_CUISINE_MEDIA])
        ]
        schema = vol.Schema(
            {
                vol.Required("cuisines"): SelectSelector(
                    SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.LIST)
                )
            }
        )
        return self.async_show_form(step_id="remove_music", data_schema=schema)

    async def async_step_done(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=self.options)
