from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DigiApiClient, DigiApiError, DigiReauthRequired


class DigiCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, api: DigiApiClient, update_interval: timedelta) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name="digi_ro",
            update_interval=update_interval,
        )
        self.api = api
        self.auth_ok = True

    async def _async_update_data(self) -> dict:
        try:
            data = await self.api.fetch_latest_invoice()
            self.auth_ok = True
            return data
        except DigiReauthRequired as err:
            self.auth_ok = False
            raise ConfigEntryAuthFailed(str(err)) from err
        except DigiApiError as err:
            raise UpdateFailed(str(err)) from err
