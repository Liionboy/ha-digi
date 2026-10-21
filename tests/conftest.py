"""Small HA API doubles: no Home Assistant install or live DIGI requests.

These tests cover integration logic, not the actual HA frontend/runtime. The
flow hooks and selectors were checked against HA 2026.3.4 upstream source.
"""

import asyncio
import sys
from enum import StrEnum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    sys.modules[name] = result
    return result


class ConfigFlow:
    def __init_subclass__(cls, **kwargs):
        pass

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_remove(self):
        pass


class ConfigEntryAuthFailed(Exception):
    pass


class ConfigEntryNotReady(Exception):
    pass


class UpdateFailed(Exception):
    pass


class DataUpdateCoordinator:
    def __init__(self, hass, **kwargs):
        self.hass = hass

    async def async_config_entry_first_refresh(self):
        self.data = await self._async_update_data()


class TextSelectorType(StrEnum):
    PASSWORD = "password"


class TextSelector:
    def __init__(self, config):
        self.config = config

    def __call__(self, value):
        if not isinstance(value, str):
            raise ValueError("Expected text")
        return value


module("homeassistant")
module(
    "homeassistant.config_entries", ConfigFlow=ConfigFlow, ConfigEntry=SimpleNamespace
)
module("homeassistant.core", HomeAssistant=SimpleNamespace, callback=lambda fn: fn)
module(
    "homeassistant.exceptions",
    ConfigEntryAuthFailed=ConfigEntryAuthFailed,
    ConfigEntryNotReady=ConfigEntryNotReady,
)
module("homeassistant.helpers")
module(
    "homeassistant.helpers.aiohttp_client",
    async_get_clientsession=lambda hass: hass.session,
)
module(
    "homeassistant.helpers.selector",
    TextSelector=TextSelector,
    TextSelectorConfig=dict,
    TextSelectorType=TextSelectorType,
)
module(
    "homeassistant.helpers.update_coordinator",
    DataUpdateCoordinator=DataUpdateCoordinator,
    UpdateFailed=UpdateFailed,
)


@pytest.fixture
def entry():
    return SimpleNamespace(
        entry_id="entry-orasys",
        domain="digi_ro",
        title="DIGI Orasys",
        data={
            "username": "first@example.invalid",
            "password": "old-test-password",
            "cookies": [{"key": "session", "value": "expired-test-session"}],
            "selected_address": "address-1",
            "update_interval": 2700,
            "legacy_field": "keep",
        },
    )


@pytest.fixture
def hass(entry):
    entries = {entry.entry_id: entry}
    manager = SimpleNamespace(
        async_get_entry=lambda entry_id: entries.get(entry_id),
        async_update_entry=Mock(
            side_effect=lambda entry, data: setattr(entry, "data", data)
        ),
        async_reload=AsyncMock(return_value=True),
        async_forward_entry_setups=AsyncMock(),
    )
    tasks = []

    def create_task(coro):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    return SimpleNamespace(
        config_entries=manager,
        session=object(),
        data={},
        async_create_task=create_task,
        tasks=tasks,
        entries=entries,
    )


@pytest.fixture
def flow(hass, entry):
    from custom_components.digi_ro.config_flow import DigiConfigFlow

    result = DigiConfigFlow()
    result.hass = hass
    result.context = {"entry_id": entry.entry_id}
    return result


@pytest.fixture
def api(monkeypatch):
    from custom_components.digi_ro import config_flow
    from custom_components.digi_ro.api import AddressOption, TwoFactorContext

    result = SimpleNamespace(
        begin_login=AsyncMock(
            return_value=("https://www.digi.ro/auth/2fa", "2fa HTML")
        ),
        get_2fa_context=AsyncMock(
            return_value=TwoFactorContext(methods={"sms": {}}, html="2fa HTML")
        ),
        send_2fa_code=AsyncMock(),
        validate_2fa_code=AsyncMock(
            return_value=("https://www.digi.ro/auth/address-select", "addresses")
        ),
        get_address_options=AsyncMock(
            return_value=[AddressOption("address-1", "First address")]
        ),
        confirm_address=AsyncMock(),
        fetch_latest_invoice=AsyncMock(return_value={"invoice_id": "test-invoice"}),
        export_cookies=Mock(
            return_value=[{"key": "session", "value": "new-test-session"}]
        ),
        import_cookie_header=Mock(),
        import_cookies=Mock(),
        close=AsyncMock(),
        selected_address="address-1",
    )
    constructor = Mock(return_value=result)
    monkeypatch.setattr(config_flow, "DigiApiClient", constructor)
    result.constructor = constructor
    return result
