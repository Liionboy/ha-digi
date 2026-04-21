from __future__ import annotations

import re
from urllib.parse import quote
from html import unescape

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

        # Extragere rapidă istoric facturi din lista principală
        html_plain = re.sub(r"<[^>]+>", " ", html)
        html_plain = re.sub(r"\s+", " ", html_plain).strip()
        recent_invoices: list[dict] = []
        for m in re.finditer(
            r"(\d{2}[-./]\d{2}[-./]\d{4})\s+([A-ZĂÂÎȘȚa-zăâîșț ]{3,40})\s+"
            r"(\d{2}[-./]\d{2}[-./]\d{4})\s+([0-9]+(?:[.,][0-9]{2})?)\s+lei",
            html_plain,
            re.I,
        ):
            issue_date, category, due_date, amount = m.groups()
            recent_invoices.append(
                {
                    "issue_date": issue_date,
                    "category": category.strip(),
                    "due_date": due_date,
                    "amount_lei": amount.replace(",", "."),
                }
            )
            if len(recent_invoices) >= 5:
                break

        account_name = None
        try:
            bulk_raw = await self._post_text(
                "/app-user-info-bulk-xhr",
                {"disableUserInfo": "", "isBusinessSection": "0"},
                "/my-account/invoices",
            )
            bulk = __import__("json").loads(bulk_raw)
            my_user_html = bulk.get("my-user", "") if isinstance(bulk, dict) else ""
            my_user_plain = re.sub(r"<[^>]+>", " ", my_user_html)
            my_user_plain = re.sub(r"\s+", " ", my_user_plain).strip()
            if my_user_plain:
                account_name = re.split(
                    r"\b(Serviciile mele|Administrare cont|Facturile mele|Comenzile mele|Logout)\b",
                    my_user_plain,
                    maxsplit=1,
                )[0].strip() or None
        except Exception:
            account_name = None

        address_match = re.search(r"Toate adresele\s+(.+?)\s+Serviciile mele", html_plain, re.I | re.S)
        current_address = re.sub(r"\s+", " ", address_match.group(1)).strip() if address_match else None
        invoices_count = len(invoice_ids)

        inv = invoice_ids[0]
        details_path = f"/my-account/invoices/details?invoice_id={inv}"
        payload = {
            "url": quote(details_path, safe=""),
            "id": inv,
        }
        details_html = await self._post_text(details_path, payload, "/my-account/invoices")
        details_html = unescape(details_html)
        plain = re.sub(r"<[^>]+>", " ", details_html)
        plain = re.sub(r"\s+", " ", plain).strip()

        # Normalizează formate gen "51 .86" / "51 ,86" / "51&period;86"
        plain_norm = re.sub(r"(\d)\s*[\.,]\s*(\d{2})", r"\1.\2", plain)

        date_match = re.search(r"din data de\s+([0-9]{2}[-./][0-9]{2}[-./][0-9]{4})", plain_norm, re.I)
        invoice_no_match = re.search(r"\bFactura\s+([A-Z0-9\- ]{4,})\b", plain_norm)
        total_match = re.search(r"\bTotal\s+([0-9]+(?:[.,][0-9]{2})?)\s+LEI", plain_norm, re.I)
        rest_match = re.search(r"\bRest\s+([0-9]+(?:[.,][0-9]{2})?)\s+LEI", plain_norm, re.I)
        status_match = re.search(r"\bStatus\s+([A-Za-zĂÂÎȘȚăâîșț\-]+)", plain_norm)
        due_match = re.search(r"\bScaden(?:ta|ță|\u021b\u0103)\s*[:\-]?\s*([0-9]{2}[-./][0-9]{2}[-./][0-9]{4})", plain_norm, re.I)

        services_count = len(set(re.findall(r"\b1\.([0-9]{1,2})\b", plain_norm)))
        status = status_match.group(1) if status_match else None
        is_paid = None
        if status:
            status_l = status.lower()
            is_paid = ("achitat" in status_l) or ("platit" in status_l) or ("plătit" in status_l)

        has_debt = None
        if rest_match:
            try:
                has_debt = float(rest_match.group(1).replace(",", ".")) > 0
            except ValueError:
                has_debt = None

        return {
            "invoice_id": inv,
            "invoice_number": invoice_no_match.group(1).strip() if invoice_no_match else None,
            "date": date_match.group(1) if date_match else None,
            "due_date": due_match.group(1) if due_match else None,
            "total_lei": total_match.group(1).replace(",", ".") if total_match else None,
            "rest_lei": rest_match.group(1).replace(",", ".") if rest_match else None,
            "status": status,
            "is_paid": is_paid,
            "has_debt": has_debt,
            "services_count": services_count,
            "account_name": account_name,
            "current_address": current_address,
            "invoices_count": invoices_count,
            "recent_invoices": recent_invoices,
            "raw_excerpt": plain[:800],
        }
