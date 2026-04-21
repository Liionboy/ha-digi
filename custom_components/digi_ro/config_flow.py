from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow

from .const import CONF_COOKIE, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN


class DigiConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="Digi România", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_COOKIE): str,
                vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(int, vol.Range(min=300, max=86400)),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None):
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reauth_unsuccessful")

        if user_input is not None:
            data = {**entry.data}
            data[CONF_COOKIE] = user_input[CONF_COOKIE]
            if CONF_UPDATE_INTERVAL in user_input:
                data[CONF_UPDATE_INTERVAL] = user_input[CONF_UPDATE_INTERVAL]
            self.hass.config_entries.async_update_entry(entry, data=data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        schema = vol.Schema(
            {
                vol.Required(CONF_COOKIE): str,
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): vol.All(int, vol.Range(min=300, max=86400)),
            }
        )
        return self.async_show_form(step_id="reauth", data_schema=schema)
