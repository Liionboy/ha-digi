"""Exercise real aiohttp cookie jars without contacting DIGI."""

import aiohttp
import pytest
from yarl import URL

from custom_components.digi_ro.api import DigiApiClient


@pytest.mark.asyncio
async def test_account_sessions_are_isolated_and_do_not_close_ha_session():
    async with aiohttp.ClientSession() as shared:
        first = DigiApiClient(shared)
        second = DigiApiClient(shared)
        try:
            first.import_cookie_header("DGROSESSV3PRI=first-test-session")
            second.import_cookie_header("DGROSESSV3PRI=second-test-session")
            assert first.export_cookies()[0]["value"] == "first-test-session"
            assert second.export_cookies()[0]["value"] == "second-test-session"
            assert not shared.cookie_jar.filter_cookies(URL("https://www.digi.ro"))
            await first.close()
            assert not shared.closed and not second._session.closed
            assert second.export_cookies()[0]["value"] == "second-test-session"
        finally:
            await first.close()
            await second.close()


@pytest.mark.asyncio
async def test_exported_session_survives_client_recreation():
    async with aiohttp.ClientSession() as shared:
        first = DigiApiClient(shared)
        restored = DigiApiClient(shared)
        try:
            first.import_cookie_header("DGROSESSV3PRI=fresh-test-session; other=keep")
            restored.import_cookies(first.export_cookies())
            await first.close()
            assert {c["key"]: c["value"] for c in restored.export_cookies()} == {
                "DGROSESSV3PRI": "fresh-test-session",
                "other": "keep",
            }
            assert not shared.closed
        finally:
            await first.close()
            await restored.close()
