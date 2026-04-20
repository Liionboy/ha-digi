from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DigiApiClient, DigiApiError


class DigiCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, api: DigiApiClient, update_interval: timedelta) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name="digi_ro",
            update_interval=update_interval,
        )
        self.api = api

    async def _async_update_data(self) -> dict:
        try:
            return await self.api.fetch_latest_invoice()
        except DigiApiError as err:
            raise UpdateFailed(str(err)) from err
