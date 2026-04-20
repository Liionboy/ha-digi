from __future__ import annotations

import re
from urllib.parse import quote

from aiohttp import ClientSession, ClientTimeout

from .const import API_BASE


class DigiApiError(Exception):
    pass


class DigiApiClient:
    def __init__(self, cookie: str) -> None:
        self._cookie = cookie.strip()
        self._timeout = ClientTimeout(total=25)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cookie": self._cookie,
        }

    async def _get_text(self, path: str) -> str:
        async with ClientSession(timeout=self._timeout) as s:
            async with s.get(f"{API_BASE}{path}", headers=self._headers) as r:
                txt = await r.text()
                if r.status != 200:
                    raise DigiApiError(f"GET {path} failed: {r.status}")
                return txt

    async def _post_text(self, path: str, data: dict[str, str], referer: str) -> str:
        headers = {
            **self._headers,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": API_BASE,
            "Referer": f"{API_BASE}{referer}",
        }
        async with ClientSession(timeout=self._timeout) as s:
            async with s.post(f"{API_BASE}{path}", headers=headers, data=data) as r:
                txt = await r.text()
                if r.status != 200:
                    raise DigiApiError(f"POST {path} failed: {r.status}")
                return txt

    async def fetch_latest_invoice(self) -> dict:
        html = await self._get_text("/my-account/invoices")
        invoice_ids = sorted(set(re.findall(r"invoice_id=(\d+)", html)), reverse=True)
        if not invoice_ids:
            raise DigiApiError("Nu am găsit invoice_id. Posibil sesiune expirată.")

        inv = invoice_ids[0]
        details_path = f"/my-account/invoices/details?invoice_id={inv}"
        payload = {
            "url": quote(details_path, safe=""),
            "id": inv,
        }
        details_html = await self._post_text(details_path, payload, "/my-account/invoices")
        plain = re.sub(r"<[^>]+>", " ", details_html)
        plain = re.sub(r"\s+", " ", plain).strip()

        date_match = re.search(r"din data de\s+([0-9]{2}[-./][0-9]{2}[-./][0-9]{4})", plain, re.I)
        total_match = re.search(r"\bTotal\s+([0-9]+(?:[.,][0-9]{2})?)\s+LEI", plain, re.I)
        rest_match = re.search(r"\bRest\s+([0-9]+(?:[.,][0-9]{2})?)\s+LEI", plain, re.I)
        status_match = re.search(r"\bStatus\s+([A-Za-zĂÂÎȘȚăâîșț\-]+)", plain)

        return {
            "invoice_id": inv,
            "date": date_match.group(1) if date_match else None,
            "total_lei": total_match.group(1).replace(",", ".") if total_match else None,
            "rest_lei": rest_match.group(1).replace(",", ".") if rest_match else None,
            "status": status_match.group(1) if status_match else None,
            "raw_excerpt": plain[:800],
        }
