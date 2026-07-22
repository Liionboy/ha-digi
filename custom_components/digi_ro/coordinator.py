from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DigiApiClient, DigiApiError, DigiAuthError, DigiReauthRequired, DigiTwoFactorRequired
from .const import CONF_COOKIES, CONF_PASSWORD, CONF_SELECTED_ADDRESS, CONF_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class DigiCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
        hass: HomeAssistant,
        api: DigiApiClient,
        update_interval: timedelta,
        username: str | None = None,
        password: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name="digi_ro",
            update_interval=update_interval,
        )
        self.api = api
        self.auth_ok = True
        self._username = username
        self._password = password
        self._entry_id = entry_id

    async def _try_auto_relogin(self) -> bool:
        """Attempt automatic re-login using saved credentials."""
        if not self._username or not self._password:
            return False

        _LOGGER.info("Session expired for Digi, attempting auto re-login for %s", self._username)
        try:
            # Create a fresh API client to clear old cookies
            session = async_get_clientsession(self.hass)
            new_api = DigiApiClient(session, selected_address=self.api.selected_address)

            final_url, html = await new_api.begin_login(self._username, self._password)

            # If 2FA is required, we can't auto-relogin
            if "/auth/2fa" in final_url:
                _LOGGER.warning("Digi auto re-login blocked by 2FA for %s", self._username)
                return False

            # If address selection is needed, confirm it
            if "/auth/address-select" in final_url:
                if self.api.selected_address:
                    await new_api.confirm_address(self.api.selected_address)

            # Verify the new session works
            await new_api.fetch_latest_invoice()

            # Success! Replace the old API client
            await self.api.close()
            self.api = new_api
            self.auth_ok = True

            # Persist new cookies to config entry
            if self._entry_id:
                entry = self.hass.config_entries.async_get_entry(self._entry_id)
                if entry is not None:
                    new_data = {**entry.data, CONF_COOKIES: new_api.export_cookies()}
                    self.hass.config_entries.async_update_entry(entry, data=new_data)
                    _LOGGER.info("Digi auto re-login successful for %s, cookies updated", self._username)

            return True

        except DigiAuthError:
            _LOGGER.error("Digi auto re-login failed: invalid credentials for %s", self._username)
            return False
        except DigiTwoFactorRequired:
            _LOGGER.warning("Digi auto re-login blocked by 2FA for %s", self._username)
            return False
        except Exception as err:
            _LOGGER.error("Digi auto re-login error for %s: %s", self._username, err)
            return False

    async def _async_update_data(self) -> dict:
        try:
            data = await self.api.fetch_latest_invoice()
            self.auth_ok = True
            return data
        except DigiReauthRequired:
            # Try auto re-login first
            if await self._try_auto_relogin():
                try:
                    data = await self.api.fetch_latest_invoice()
                    self.auth_ok = True
                    return data
                except DigiApiError as err:
                    raise UpdateFailed(str(err)) from err

            # Auto re-login failed — need manual reauth
            self.auth_ok = False
            raise ConfigEntryAuthFailed("Session expired and auto re-login failed")
        except DigiApiError as err:
            raise UpdateFailed(str(err)) from err
