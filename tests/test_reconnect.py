"""Regression checks for setup, reconfigure, reauth and session cleanup."""

import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.digi_ro.api import (
    DigiAuthError,
    DigiReauthRequired,
    DigiTwoFactorError,
)
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

pytestmark = pytest.mark.asyncio
CREDS = {"username": "first@example.invalid", "password": "new-test-password"}


async def start_login(flow, source, entry):
    if source == "reauth":
        result = await flow.async_step_reauth(entry.data)
        assert result["step_id"] == "reauth_confirm"
        result = await flow.async_step_reauth_confirm({"auth_method": "login"})
    else:
        result = await flow.async_step_reconfigure()
        assert result["step_id"] == "reconfigure"
        result = await flow.async_step_reconfigure({"auth_method": "login"})
    assert result["step_id"] == "login"
    return await flow.async_step_login(CREDS)


@pytest.mark.parametrize("source", ["reauth", "reconfigure"])
async def test_reconnect_2fa_preserves_entry(flow, api, entry, hass, source):
    original = deepcopy(entry.data)
    other = SimpleNamespace(
        entry_id="entry-nicole",
        domain="digi_ro",
        title="DIGI Nicole",
        data={"cookies": ["other"]},
    )
    hass.entries[other.entry_id] = other
    assert (await start_login(flow, source, entry))["step_id"] == "2fa_method"
    assert entry.data == original
    assert (await flow.async_step_2fa_method({"method": "sms"}))[
        "step_id"
    ] == "2fa_code"
    assert entry.data == original
    result = await flow.async_step_2fa_code({"code": "123456"})
    assert result == {"type": "abort", "reason": source + "_successful"}
    assert entry.title == "DIGI Orasys" and entry.entry_id == "entry-orasys"
    for key in ("selected_address", "update_interval", "legacy_field"):
        assert entry.data[key] == original[key]
    assert entry.data["password"] == CREDS["password"]
    assert entry.data["cookies"] == api.export_cookies.return_value
    assert other.data == {"cookies": ["other"]}
    assert len(hass.entries) == 2
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
    api.confirm_address.assert_awaited_once_with("address-1")
    api.close.assert_awaited_once()


async def test_invalid_code_can_retry_without_saving(flow, api, entry, hass):
    original = deepcopy(entry.data)
    await start_login(flow, "reconfigure", entry)
    await flow.async_step_2fa_method({"method": "sms"})
    api.validate_2fa_code.side_effect = DigiTwoFactorError("test invalid code")
    result = await flow.async_step_2fa_code({"code": "bad"})
    assert result["step_id"] == "2fa_code" and result["errors"] == {
        "base": "invalid_auth"
    }
    assert entry.data == original
    hass.config_entries.async_update_entry.assert_not_called()
    api.validate_2fa_code.side_effect = None
    assert (await flow.async_step_2fa_code({"code": "123456"}))[
        "reason"
    ] == "reconfigure_successful"


@pytest.mark.parametrize("url", ["/auth/2fa", "/auth/login"])
async def test_2fa_redirect_does_not_save(flow, api, entry, hass, url):
    await start_login(flow, "reauth", entry)
    await flow.async_step_2fa_method({"method": "sms"})
    api.validate_2fa_code.return_value = (url, "")
    result = await flow.async_step_2fa_code({"code": "123456"})
    assert result["errors"] == {"base": "invalid_auth"}
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.parametrize(
    "failure,error",
    [(DigiAuthError("test"), "invalid_auth"), (TimeoutError(), "cannot_connect")],
)
async def test_login_errors_preserve_data(flow, api, entry, hass, failure, error):
    original = deepcopy(entry.data)
    api.begin_login.side_effect = failure
    result = await start_login(flow, "reconfigure", entry)
    assert result["step_id"] == "login" and result["errors"]["base"] == error
    assert entry.data == original
    api.close.assert_awaited_once()
    hass.config_entries.async_reload.assert_not_awaited()


async def test_different_username_rejected(flow, api, entry):
    await flow.async_step_reconfigure()
    result = await flow.async_step_login({**CREDS, "username": "other@example.invalid"})
    assert result["errors"] == {"base": "account_mismatch"}
    api.begin_login.assert_not_awaited()


async def test_password_is_masked_and_not_prefilled(flow, entry):
    await flow.async_step_reconfigure()
    result = await flow.async_step_login()
    schema = result["data_schema"]
    field, validator = next(
        (key, val) for key, val in schema.schema.items() if key.schema == "password"
    )
    assert validator.config["type"] == "password"
    with pytest.raises(Exception):
        schema({"username": entry.data["username"]})


@pytest.mark.parametrize("failure", [DigiReauthRequired("test"), TimeoutError()])
async def test_invalid_cookie_is_not_saved(flow, api, entry, hass, failure):
    original = deepcopy(entry.data)
    await flow.async_step_reconfigure()
    api.fetch_latest_invoice.side_effect = failure
    result = await flow.async_step_cookie({"cookie": "session=test"})
    assert result["type"] == "form" and result["errors"]
    assert entry.data == original
    hass.config_entries.async_update_entry.assert_not_called()
    api.close.assert_awaited_once()


async def test_valid_cookie_preserves_credentials_and_settings(flow, api, entry, hass):
    old_password = entry.data["password"]
    await flow.async_step_reconfigure()
    assert (await flow.async_step_cookie({"cookie": "session=test"}))[
        "reason"
    ] == "reconfigure_successful"
    assert entry.data["password"] == old_password
    assert entry.data["selected_address"] == "address-1"
    assert entry.data["update_interval"] == 2700


async def test_cookie_only_entry_can_enable_login(flow, api, entry):
    entry.data.pop("username")
    entry.data.pop("password")
    api.begin_login.return_value = ("https://www.digi.ro/my-account/invoices", "")
    await flow.async_step_reconfigure()
    result = await flow.async_step_login(CREDS)
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["username"] == CREDS["username"]


async def test_no_2fa_reconnect(flow, api, entry):
    api.begin_login.return_value = ("https://www.digi.ro/my-account/invoices", "")
    assert (await start_login(flow, "reconfigure", entry))[
        "reason"
    ] == "reconfigure_successful"
    api.send_2fa_code.assert_not_awaited()


async def test_missing_saved_address_never_switches(flow, api, entry, hass):
    api.begin_login.return_value = ("https://www.digi.ro/auth/address-select", "")
    api.get_address_options.return_value = []
    assert (await start_login(flow, "reconfigure", entry))[
        "reason"
    ] == "address_unavailable"
    hass.config_entries.async_update_entry.assert_not_called()
    api.confirm_address.assert_not_awaited()
    api.close.assert_awaited_once()


async def test_initial_setup_still_creates_entry(flow, api):
    api.begin_login.return_value = ("https://www.digi.ro/auth/address-select", "")
    await flow.async_step_user({"auth_method": "login", "update_interval": 1800})
    result = await flow.async_step_login(CREDS)
    assert result["step_id"] == "address_select"
    result = await flow.async_step_address_select({"address": "address-1"})
    assert result["type"] == "create_entry"
    assert result["data"]["selected_address"] == "address-1"
    api.close.assert_awaited_once()


async def test_initial_cookie_setup(flow, api):
    await flow.async_step_user({"auth_method": "cookie"})
    result = await flow.async_step_cookie({"cookie": "session=test"})
    assert result["type"] == "create_entry" and "username" not in result["data"]


@pytest.mark.parametrize("source", ["reauth", "reconfigure"])
async def test_missing_entry_aborts(flow, api, source):
    flow.context["entry_id"] = "missing"
    result = (
        await flow.async_step_reauth({})
        if source == "reauth"
        else await flow.async_step_reconfigure()
    )
    assert result["reason"] == "reauth_unsuccessful"
    api.begin_login.assert_not_awaited()


async def test_cancel_closes_private_session(flow, api, entry, hass):
    await start_login(flow, "reconfigure", entry)
    flow.async_remove()
    await asyncio.gather(*hass.tasks)
    api.close.assert_awaited_once()
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.parametrize("failure", ["2fa", "credentials", "network"])
async def test_failed_auto_login_closes_temporary_client(
    hass, api, monkeypatch, failure
):
    from custom_components.digi_ro import coordinator as mod

    old_api = SimpleNamespace(selected_address="address-1", close=AsyncMock())
    monkeypatch.setattr(mod, "DigiApiClient", Mock(return_value=api))
    if failure == "credentials":
        api.begin_login.side_effect = DigiAuthError("test")
    elif failure == "network":
        api.begin_login.side_effect = TimeoutError()
    co = mod.DigiCoordinator(
        hass, old_api, timedelta(seconds=1800), "test-user", "test-password"
    )
    assert await co._try_auto_relogin() is False
    api.close.assert_awaited_once()
    old_api.close.assert_not_awaited()


async def test_successful_auto_login_keeps_new_client(hass, api, entry, monkeypatch):
    from custom_components.digi_ro import coordinator as mod

    old_api = SimpleNamespace(selected_address="address-1", close=AsyncMock())
    monkeypatch.setattr(mod, "DigiApiClient", Mock(return_value=api))
    api.begin_login.return_value = ("https://www.digi.ro/my-account/invoices", "")
    co = mod.DigiCoordinator(
        hass,
        old_api,
        timedelta(seconds=1800),
        "test-user",
        "test-password",
        entry.entry_id,
    )
    assert await co._try_auto_relogin() is True
    assert co.api is api
    api.close.assert_not_awaited()
    old_api.close.assert_awaited_once()


async def test_expired_session_requests_manual_auth(hass, api):
    from custom_components.digi_ro.coordinator import DigiCoordinator

    api.fetch_latest_invoice.side_effect = DigiReauthRequired("test")
    co = DigiCoordinator(hass, api, timedelta(seconds=1800))
    with pytest.raises(ConfigEntryAuthFailed):
        await co._async_update_data()
    assert co.auth_ok is False


@pytest.mark.parametrize("failure", [ConfigEntryAuthFailed, ConfigEntryNotReady])
async def test_setup_failure_closes_client(hass, api, entry, monkeypatch, failure):
    import custom_components.digi_ro as mod

    monkeypatch.setattr(mod, "DigiApiClient", Mock(return_value=api))
    co = SimpleNamespace(
        api=api,
        async_config_entry_first_refresh=AsyncMock(side_effect=failure("test")),
    )
    monkeypatch.setattr(mod, "DigiCoordinator", Mock(return_value=co))
    with pytest.raises(failure):
        await mod.async_setup_entry(hass, entry)
    api.close.assert_awaited_once()
    hass.config_entries.async_forward_entry_setups.assert_not_awaited()


async def test_malformed_cookie_shows_form_error(flow, api, entry, hass):
    await flow.async_step_reconfigure()
    original = deepcopy(entry.data)
    api.import_cookie_header.side_effect = ValueError("malformed test cookie")
    result = await flow.async_step_cookie({"cookie": "invalid cookie=test"})
    assert result["step_id"] == "cookie" and result["errors"]
    assert entry.data == original
    hass.config_entries.async_update_entry.assert_not_called()
    api.close.assert_awaited_once()


async def test_2fa_context_failure_does_not_save(flow, api, entry, hass):
    api.get_2fa_context.side_effect = TimeoutError()
    result = await start_login(flow, "reconfigure", entry)
    assert result["step_id"] == "login"
    assert result["errors"]["base"] == "cannot_connect"
    hass.config_entries.async_update_entry.assert_not_called()
    api.close.assert_awaited_once()


async def test_send_code_can_retry(flow, api, entry):
    await start_login(flow, "reconfigure", entry)
    api.send_2fa_code.side_effect = TimeoutError()
    result = await flow.async_step_2fa_method({"method": "sms"})
    assert result["step_id"] == "2fa_method" and result["errors"]
    api.send_2fa_code.side_effect = None
    assert (await flow.async_step_2fa_method({"method": "sms"}))[
        "step_id"
    ] == "2fa_code"


async def test_network_failure_validating_code_can_retry(flow, api, entry, hass):
    await start_login(flow, "reconfigure", entry)
    await flow.async_step_2fa_method({"method": "sms"})
    api.validate_2fa_code.side_effect = TimeoutError()
    result = await flow.async_step_2fa_code({"code": "123456"})
    assert result["errors"]["base"] == "cannot_connect"
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.parametrize(
    "failure,reason",
    [(DigiReauthRequired("test"), "invalid_auth"), (TimeoutError(), "cannot_connect")],
)
async def test_unverified_login_never_commits(flow, api, entry, hass, failure, reason):
    original = deepcopy(entry.data)
    api.begin_login.return_value = ("https://www.digi.ro/my-account/invoices", "")
    api.fetch_latest_invoice.side_effect = failure
    result = await start_login(flow, "reconfigure", entry)
    assert result["reason"] == reason
    assert entry.data == original
    hass.config_entries.async_update_entry.assert_not_called()
    api.close.assert_awaited_once()


@pytest.mark.parametrize("operation", ["get_address_options", "confirm_address"])
async def test_address_network_failure_does_not_commit(
    flow, api, entry, hass, operation
):
    api.begin_login.return_value = ("https://www.digi.ro/auth/address-select", "")
    getattr(api, operation).side_effect = TimeoutError()
    result = await start_login(flow, "reconfigure", entry)
    assert result["reason"] == "cannot_connect"
    hass.config_entries.async_update_entry.assert_not_called()
    api.close.assert_awaited_once()
