from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import DigiApiClient
from .const import CONF_COOKIE, CONF_COOKIES, CONF_SELECTED_ADDRESS, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import DigiCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = DigiApiClient(session, selected_address=entry.data.get(CONF_SELECTED_ADDRESS))

    if entry.data.get(CONF_COOKIES):
        api.import_cookies(entry.data[CONF_COOKIES])
    elif entry.data.get(CONF_COOKIE):
        api.import_cookie_header(entry.data[CONF_COOKIE])

    interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator = DigiCoordinator(hass, api, timedelta(seconds=interval))

    try:
        await coordinator.async_config_entry_first_refresh()
    except UpdateFailed:
        await api.close()
        return False

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        if coordinator is not None:
            await coordinator.api.close()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
