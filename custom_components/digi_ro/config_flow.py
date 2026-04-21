from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DigiApiClient, DigiAuthError, DigiTwoFactorError, DigiTwoFactorRequired, TwoFactorContext
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
        self._twofa_context: dict[str, Any] | None = None
        self._address_options: list[tuple[str, str]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Required(CONF_AUTH_METHOD, default=AUTH_METHOD_COOKIE): vol.In([AUTH_METHOD_COOKIE, AUTH_METHOD_LOGIN]),
                    vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(int, vol.Range(min=300, max=86400)),
                }
            )
            return self.async_show_form(step_id="user", data_schema=schema)

        self._auth_data[CONF_UPDATE_INTERVAL] = user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        if user_input[CONF_AUTH_METHOD] == AUTH_METHOD_LOGIN:
            return await self.async_step_login()
        return await self.async_step_cookie()

    async def async_step_cookie(self, user_input: dict[str, Any] | None = None):
        if user_input is None:
            schema = vol.Schema({vol.Required(CONF_COOKIE): str})
            return self.async_show_form(step_id="cookie", data_schema=schema)

        session = async_get_clientsession(self.hass)
        api = DigiApiClient(session)
        api.import_cookie_header(user_input[CONF_COOKIE])
        try:
            await api.fetch_latest_invoice()
        except Exception:
            return self.async_show_form(step_id="cookie", data_schema=vol.Schema({vol.Required(CONF_COOKIE): str}), errors={"base": "cannot_connect"})

        return self.async_create_entry(
            title="Digi România",
            data={
                CONF_COOKIES: api.export_cookies(),
                CONF_UPDATE_INTERVAL: self._auth_data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            },
        )

    async def async_step_login(self, user_input: dict[str, Any] | None = None):
        if user_input is None:
            schema = vol.Schema({vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str})
            return self.async_show_form(step_id="login", data_schema=schema)

        session = async_get_clientsession(self.hass)
        self._api = DigiApiClient(session)
        self._auth_data[CONF_USERNAME] = user_input[CONF_USERNAME]

        try:
            final_url, html = await self._api.begin_login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
        except DigiAuthError:
            return self.async_show_form(step_id="login", data_schema=vol.Schema({vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}), errors={"base": "invalid_auth"})
        except Exception:
            return self.async_show_form(step_id="login", data_schema=vol.Schema({vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}), errors={"base": "cannot_connect"})

        if "/auth/2fa" in final_url:
            try:
                ctx = await self._api.get_2fa_context(html)
            except DigiTwoFactorRequired:
                return self.async_show_form(
                    step_id="login",
                    data_schema=vol.Schema({vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}),
                    errors={"base": "cannot_connect"},
                )
            self._twofa_context = {"methods": ctx.methods, "html": ctx.html}
            return await self.async_step_2fa_method()

        if "/auth/address-select" in final_url:
            return await self.async_step_address_select({"html": html})

        return await self.async_step_finalize_login()

    async def async_step_2fa_method(self, user_input: dict[str, Any] | None = None):
        methods = list((self._twofa_context or {}).get("methods", {}).keys())
        if not methods:
            return self.async_abort(reason="cannot_connect")

        if user_input is None:
            schema = vol.Schema({vol.Required("method", default=methods[0]): vol.In(methods)})
            return self.async_show_form(step_id="2fa_method", data_schema=schema)

        assert self._api is not None
        method = user_input["method"]
        await self._api.send_2fa_code(
            TwoFactorContext(methods=self._twofa_context["methods"], html=self._twofa_context.get("html", "")),
            method,
        )
        self._auth_data["method"] = method
        return await self.async_step_2fa_code()

    async def async_step_2fa_code(self, user_input: dict[str, Any] | None = None):
        if user_input is None:
            schema = vol.Schema({vol.Required("code"): str})
            return self.async_show_form(step_id="2fa_code", data_schema=schema)

        assert self._api is not None
        method = self._auth_data.get("method", "sms")
        try:
            final_url, html = await self._api.validate_2fa_code(
                TwoFactorContext(methods=self._twofa_context["methods"], html=self._twofa_context.get("html", "")),
                method,
                user_input["code"],
            )
        except DigiTwoFactorError:
            return self.async_show_form(step_id="2fa_code", data_schema=vol.Schema({vol.Required("code"): str}), errors={"base": "invalid_auth"})

        if "/auth/address-select" in final_url:
            return await self.async_step_address_select({"html": html})

        return await self.async_step_finalize_login()

    async def async_step_address_select(self, user_input: dict[str, Any] | None = None):
        assert self._api is not None
        html = user_input.get("html") if user_input else None

        if not self._address_options:
            options = await self._api.get_address_options(html)
            self._address_options = [(opt.value, opt.label) for opt in options] or [("", "Toate adresele")]

        if user_input is None or "address" not in user_input:
            schema = vol.Schema({vol.Required("address", default=self._address_options[0][0]): vol.In({k: v for k, v in self._address_options})})
            return self.async_show_form(step_id="address_select", data_schema=schema)

        address_id = user_input["address"]
        if address_id:
            await self._api.confirm_address(address_id)
        self._auth_data[CONF_SELECTED_ADDRESS] = address_id
        return await self.async_step_finalize_login()

    async def async_step_finalize_login(self):
        assert self._api is not None
        try:
            await self._api.fetch_latest_invoice()
        except Exception:
            return self.async_abort(reason="cannot_connect")

        return self.async_create_entry(
            title=f"Digi România ({self._auth_data.get(CONF_USERNAME, 'cont')})",
            data={
                CONF_COOKIES: self._api.export_cookies(),
                CONF_SELECTED_ADDRESS: self._auth_data.get(CONF_SELECTED_ADDRESS, ""),
                CONF_UPDATE_INTERVAL: self._auth_data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            },
        )

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None):
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reauth_unsuccessful")

        if user_input is not None:
            data = {**entry.data}
            if CONF_COOKIE in user_input:
                session = async_get_clientsession(self.hass)
                api = DigiApiClient(session)
                api.import_cookie_header(user_input[CONF_COOKIE])
                data[CONF_COOKIES] = api.export_cookies()
            self.hass.config_entries.async_update_entry(entry, data=data)
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        schema = vol.Schema({vol.Required(CONF_COOKIE): str})
        return self.async_show_form(step_id="reauth", data_schema=schema)
