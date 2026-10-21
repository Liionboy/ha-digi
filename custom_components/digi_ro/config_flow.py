"""Digi setup and in-place session recovery, including interactive 2FA."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    DigiApiClient,
    DigiAuthError,
    DigiReauthRequired,
    DigiTwoFactorError,
    TwoFactorContext,
)
from .const import (
    AUTH_METHOD_COOKIE,
    AUTH_METHOD_LOGIN,
    CONF_AUTH_METHOD,
    CONF_COOKIE,
    CONF_COOKIES,
    CONF_PASSWORD,
    CONF_SELECTED_ADDRESS,
    CONF_UPDATE_INTERVAL,
    CONF_USERNAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)


class DigiConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._api: DigiApiClient | None = None
        self._auth_data: dict[str, Any] = {}
        self._twofa_context: TwoFactorContext | None = None
        self._address_options: list[tuple[str, str]] = []
        self._entry: ConfigEntry | None = None
        self._success_reason = "reauth_successful"

    async def _async_close_api(self) -> None:
        api, self._api = self._api, None
        if api is not None:
            await api.close()

    @callback
    def async_remove(self) -> None:
        """Release the private session when the user cancels a dialog."""
        super().async_remove()
        if self._api is not None:
            self.hass.async_create_task(self._async_close_api())

    async def _async_select_method(self, step_id, user_input=None):
        if user_input is None:
            default = AUTH_METHOD_LOGIN
            if self._entry is not None and not self._entry.data.get(CONF_USERNAME):
                default = AUTH_METHOD_COOKIE
            fields = {
                vol.Required(CONF_AUTH_METHOD, default=default): vol.In(
                    [AUTH_METHOD_LOGIN, AUTH_METHOD_COOKIE]
                )
            }
            if step_id == "user":
                fields[
                    vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL)
                ] = vol.All(int, vol.Range(min=300, max=86400))
            return self.async_show_form(step_id=step_id, data_schema=vol.Schema(fields))
        if self._entry is None:
            self._auth_data[CONF_UPDATE_INTERVAL] = user_input.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
            )
        if user_input[CONF_AUTH_METHOD] == AUTH_METHOD_LOGIN:
            return await self.async_step_login()
        return await self.async_step_cookie()

    async def async_step_user(self, user_input=None):
        return await self._async_select_method("user", user_input)

    def _prepare_existing_entry(self) -> bool:
        self._entry = self.hass.config_entries.async_get_entry(
            self.context.get("entry_id", "")
        )
        if self._entry is None or self._entry.domain != DOMAIN:
            return False
        self._auth_data = {
            CONF_UPDATE_INTERVAL: self._entry.data.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
            ),
            CONF_SELECTED_ADDRESS: self._entry.data.get(CONF_SELECTED_ADDRESS, ""),
        }
        return True

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """Recover expired authentication through the shared login/2FA flow."""
        if not self._prepare_existing_entry():
            return self.async_abort(reason="reauth_unsuccessful")
        self._success_reason = "reauth_successful"
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._async_select_method("reauth_confirm", user_input)

    async def async_step_reconfigure(self, user_input=None):
        """Expose Reconfigure even without a pending automatic reauth dialog."""
        if self._entry is None and not self._prepare_existing_entry():
            return self.async_abort(reason="reauth_unsuccessful")
        self._success_reason = "reconfigure_successful"
        return await self._async_select_method("reconfigure", user_input)

    async def async_step_cookie(self, user_input=None):
        schema = vol.Schema({vol.Required(CONF_COOKIE): str})
        errors = {}
        if user_input is not None:
            await self._async_close_api()
            self._api = DigiApiClient(
                async_get_clientsession(self.hass),
                selected_address=self._auth_data.get(CONF_SELECTED_ADDRESS),
            )
            try:
                self._api.import_cookie_header(user_input[CONF_COOKIE])
                await self._api.fetch_latest_invoice()
            except (DigiAuthError, DigiReauthRequired):
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                return await self._async_finish()
            await self._async_close_api()
        return self.async_show_form(step_id="cookie", data_schema=schema, errors=errors)

    def _login_schema(self):
        username = self._auth_data.get(CONF_USERNAME, "")
        if not username and self._entry is not None:
            username = self._entry.data.get(CONF_USERNAME, "")
        return vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=username): str,
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )

    async def async_step_login(self, user_input=None):
        errors = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            saved_username = (
                self._entry.data.get(CONF_USERNAME) if self._entry else None
            )
            if (
                saved_username
                and username.casefold() != saved_username.strip().casefold()
            ):
                return self.async_show_form(
                    step_id="login",
                    data_schema=self._login_schema(),
                    errors={"base": "account_mismatch"},
                )
            await self._async_close_api()
            self._twofa_context = None
            self._address_options = []
            self._api = DigiApiClient(
                async_get_clientsession(self.hass),
                selected_address=self._auth_data.get(CONF_SELECTED_ADDRESS),
            )
            self._auth_data[CONF_USERNAME] = username
            self._auth_data[CONF_PASSWORD] = user_input[CONF_PASSWORD]
            try:
                final_url, html = await self._api.begin_login(
                    username, user_input[CONF_PASSWORD]
                )
                if "/auth/2fa" in final_url:
                    self._twofa_context = await self._api.get_2fa_context(html)
                    return await self.async_step_2fa_method()
                if "/auth/address-select" in final_url:
                    return await self.async_step_address_select({"html": html})
                return await self.async_step_finalize_login()
            except DigiAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            await self._async_close_api()
        return self.async_show_form(
            step_id="login", data_schema=self._login_schema(), errors=errors
        )

    async def async_step_2fa_method(self, user_input=None):
        methods = list(self._twofa_context.methods) if self._twofa_context else []
        if not methods:
            await self._async_close_api()
            return self.async_abort(reason="cannot_connect")
        schema = vol.Schema(
            {vol.Required("method", default=methods[0]): vol.In(methods)}
        )
        errors = {}
        if user_input is not None:
            assert self._api is not None
            try:
                await self._api.send_2fa_code(self._twofa_context, user_input["method"])
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                self._auth_data["method"] = user_input["method"]
                return await self.async_step_2fa_code()
        return self.async_show_form(
            step_id="2fa_method", data_schema=schema, errors=errors
        )

    async def async_step_2fa_code(self, user_input=None):
        schema = vol.Schema({vol.Required("code"): str})
        errors = {}
        if user_input is not None:
            assert self._api is not None
            try:
                final_url, html = await self._api.validate_2fa_code(
                    self._twofa_context,
                    self._auth_data.get("method", "sms"),
                    user_input["code"],
                )
                if "/auth/2fa" in final_url or "/auth/login" in final_url:
                    errors["base"] = "invalid_auth"
                elif "/auth/address-select" in final_url:
                    return await self.async_step_address_select({"html": html})
                else:
                    return await self.async_step_finalize_login()
            except (DigiTwoFactorError, DigiAuthError, DigiReauthRequired):
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="2fa_code", data_schema=schema, errors=errors
        )

    async def async_step_address_select(self, user_input=None):
        assert self._api is not None
        html = user_input.get("html") if user_input else None
        try:
            if not self._address_options:
                options = await self._api.get_address_options(html)
                self._address_options = [(opt.value, opt.label) for opt in options] or [
                    ("", "Toate adresele")
                ]
            saved_address = self._auth_data.get(CONF_SELECTED_ADDRESS, "")
            if self._entry is not None and saved_address:
                if saved_address not in dict(self._address_options):
                    await self._async_close_api()
                    return self.async_abort(reason="address_unavailable")
                user_input = {"address": saved_address}
            if user_input is not None and "address" in user_input:
                address_id = user_input["address"]
                if address_id:
                    await self._api.confirm_address(address_id)
                self._auth_data[CONF_SELECTED_ADDRESS] = address_id
                self._api.selected_address = address_id
                return await self.async_step_finalize_login()
        except Exception:
            await self._async_close_api()
            return self.async_abort(reason="cannot_connect")
        return self.async_show_form(
            step_id="address_select",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "address", default=self._address_options[0][0]
                    ): vol.In(dict(self._address_options))
                }
            ),
        )

    async def async_step_finalize_login(self):
        assert self._api is not None
        try:
            await self._api.fetch_latest_invoice()
        except (DigiAuthError, DigiReauthRequired):
            await self._async_close_api()
            return self.async_abort(reason="invalid_auth")
        except Exception:
            await self._async_close_api()
            return self.async_abort(reason="cannot_connect")
        return await self._async_finish()

    async def _async_finish(self):
        """Persist only verified sessions; keep existing IDs and custom settings."""
        assert self._api is not None
        data = {
            CONF_COOKIES: self._api.export_cookies(),
            CONF_SELECTED_ADDRESS: self._auth_data.get(CONF_SELECTED_ADDRESS, ""),
            CONF_UPDATE_INTERVAL: self._auth_data.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
            ),
        }
        if self._auth_data.get(CONF_USERNAME):
            data[CONF_USERNAME] = self._auth_data[CONF_USERNAME]
            data[CONF_PASSWORD] = self._auth_data[CONF_PASSWORD]
        await self._async_close_api()
        if self._entry is not None:
            self.hass.config_entries.async_update_entry(
                self._entry, data={**self._entry.data, **data}
            )
            await self.hass.config_entries.async_reload(self._entry.entry_id)
            return self.async_abort(reason=self._success_reason)
        return self.async_create_entry(
            title=f"Digi România ({self._auth_data[CONF_USERNAME]})"
            if self._auth_data.get(CONF_USERNAME)
            else "Digi România",
            data=data,
        )
