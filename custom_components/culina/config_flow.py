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
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import CulinaApi, CulinaApiError, CulinaAuthError
from .const import (
    CONF_ANNOUNCEMENTS,
    CONF_MEDIA_PLAYER,
    CONF_MUSIC,
    CONF_TOKEN,
    CONF_TTS_ENTITY,
    DOMAIN,
)

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


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
                    options={CONF_ANNOUNCEMENTS: True, CONF_MUSIC: True},
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
    """One form: the voice, and announcements and music on or off."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = self.config_entry.options
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_TTS_ENTITY: user_input.get(CONF_TTS_ENTITY),
                    CONF_ANNOUNCEMENTS: user_input[CONF_ANNOUNCEMENTS],
                    CONF_MUSIC: user_input[CONF_MUSIC],
                },
            )
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TTS_ENTITY,
                    description={"suggested_value": current.get(CONF_TTS_ENTITY)},
                ): EntitySelector(EntitySelectorConfig(domain="tts")),
                vol.Required(
                    CONF_ANNOUNCEMENTS, default=current.get(CONF_ANNOUNCEMENTS, True)
                ): BooleanSelector(),
                vol.Required(CONF_MUSIC, default=current.get(CONF_MUSIC, True)): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
