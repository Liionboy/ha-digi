from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin

import aiohttp
from yarl import URL

from .const import (
    ADDRESS_CONFIRM_URL,
    ADDRESS_SELECT_URL,
    API_BASE,
    INVOICES_URL,
    LOGIN_URL,
    TWO_FA_SEND_URL,
    TWO_FA_URL,
    TWO_FA_VALIDATE_URL,
)

RE_INPUT_TAG = re.compile(r"<input[^>]*>", re.I | re.S)
RE_LABEL_FOR = re.compile(r'<label[^>]+for=["\']([^"\']+)["\'][^>]*>(.*?)</label>', re.I | re.S)
RE_ADDRESS_OPTION = re.compile(r'<option[^>]+id=["\'](address-[^"\']+)["\'][^>]*>(.*?)</option>', re.I | re.S)
RE_SCRIPT_CFG = re.compile(r'<script[^>]+id=["\']client-invoices-cfg["\'][^>]*>(.*?)</script>', re.I | re.S)
RE_ROW = re.compile(
    r'<div class=["\']my-account-tbl-row["\'][^>]*data-invoice-address=["\']([^"\']+)["\'][^>]*>\s*'
    r'<div class=["\']my-account-tbl-col date["\']>\s*(.*?)\s*</div>\s*'
    r'<div class=["\']my-account-tbl-col description["\']>\s*(.*?)\s*<span>\s*(.*?)\s*</span>\s*</div>\s*'
    r'<div class=["\']my-account-tbl-col amount["\']>\s*(.*?)\s*</div>',
    re.I | re.S,
)
RE_CURRENT_ROW = re.compile(
    r'<div class=["\']my-account-tbl-row["\'][^>]*data-invoice-address=["\']([^"\']+)["\'][^>]*>\s*'
    r'<div class=["\']my-account-tbl-col select check["\']>\s*'
    r'<button[^>]*data-invoices-id=["\'](\d+)["\'][^>]*>.*?</button>\s*</div>\s*'
    r'<div class=["\']my-account-tbl-col date["\']>\s*(.*?)\s*</div>\s*'
    r'<div class=["\']my-account-tbl-col description["\']>\s*(.*?)\s*<span>\s*(.*?)\s*</span>\s*</div>\s*'
    r'<div class=["\']my-account-tbl-col amount["\']>\s*(.*?)\s*</div>',
    re.I | re.S,
)
RE_DETAILS_TITLE = re.compile(r"Factura\s+([^<]+?)\s+din data de\s+([0-9.\-/]+)", re.I | re.S)
RE_PDF = re.compile(r'href=["\']([^"\']*?/my-account/invoices/pdf-download[^"\']+)["\']', re.I)
RE_SERVICE_ROW = re.compile(
    r'<div class=["\']popup-content-item["\']>\s*<div class=["\']name["\']>\s*(.*?)\s*</div>\s*'
    r'<div class=["\']price["\']>\s*(.*?)\s*</div>',
    re.I | re.S,
)
RE_HEX32 = re.compile(r"\b[a-f0-9]{32}\b", re.I)
RE_PHONE_PARAM = re.compile(r'(?:phone|form-phone-number-confirm|phone-number-confirm)[^a-f0-9]{0,40}([a-f0-9]{32})', re.I | re.S)
RE_LABEL_VALUE_MONEY = re.compile(r'>\s*(Total|Rest)\s*<.*?>\s*([0-9]+(?:(?:[.,]|&period;)[0-9]{2})?)\s*LEI', re.I | re.S)
RE_LABEL_VALUE_TEXT = re.compile(r'>\s*Status\s*<.*?>\s*([^<]+)', re.I | re.S)


class DigiApiError(Exception):
    pass


class DigiAuthError(DigiApiError):
    pass


class DigiTwoFactorRequired(DigiApiError):
    pass


class DigiTwoFactorError(DigiApiError):
    pass


class DigiAccountSelectionRequired(DigiApiError):
    pass


class DigiReauthRequired(DigiApiError):
    pass


@dataclass(slots=True)
class TwoFactorContext:
    methods: dict[str, dict[str, Any]]
    html: str


@dataclass(slots=True)
class AddressOption:
    value: str
    label: str


@dataclass(slots=True)
class InvoiceSummary:
    invoice_id: str
    address_key: str
    address: str
    issue_date: str
    due_date: str
    description: str
    amount: float


@dataclass(slots=True)
class InvoiceDetail:
    invoice_id: str
    invoice_number: str | None
    issue_date: str | None
    due_date: str | None
    total: float | None
    rest: float | None
    status: str | None
    pdf_url: str | None
    services: list[dict[str, Any]]


class DigiApiClient:
    def __init__(self, session: aiohttp.ClientSession, selected_address: str | None = None) -> None:
        connector = session.connector
        if connector is None:
            raise DigiApiError("HTTP session connector is unavailable")
        self._session = aiohttp.ClientSession(
            connector=connector,
            connector_owner=False,
            cookie_jar=aiohttp.CookieJar(),
            timeout=session.timeout,
        )
        self._default_headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": API_BASE,
            "Origin": API_BASE,
        }
        self.selected_address = selected_address

    async def close(self) -> None:
        if not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, url: str, **kwargs: Any) -> aiohttp.ClientResponse:
        headers = dict(self._default_headers)
        headers.update(kwargs.pop("headers", {}))
        return await self._session.request(method, url, headers=headers, **kwargs)

    async def _read_text(self, response: aiohttp.ClientResponse) -> str:
        return await response.text(errors="ignore")

    def import_cookie_header(self, cookie_header: str) -> None:
        self._session.cookie_jar.clear()
        for chunk in (cookie_header or "").split(";"):
            part = chunk.strip()
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            self._session.cookie_jar.update_cookies({k.strip(): v.strip()}, response_url=URL(API_BASE))

    def export_cookies(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for cookie in self._session.cookie_jar:
            out.append(
                {
                    "key": cookie.key,
                    "value": cookie.value,
                    "domain": cookie["domain"],
                    "path": cookie["path"],
                    "secure": bool(cookie["secure"]),
                    "expires": cookie["expires"],
                }
            )
        return out

    def import_cookies(self, cookies: list[dict[str, Any]]) -> None:
        jar = self._session.cookie_jar
        jar.clear()
        for item in cookies or []:
            domain = str(item.get("domain", "")).strip()
            key = str(item.get("key", "")).strip()
            value = str(item.get("value", ""))
            if domain and key:
                jar.update_cookies({key: value}, response_url=URL(f"https://{domain.lstrip('.')}"))

    async def begin_login(self, email: str, password: str) -> tuple[str, str]:
        self._session.cookie_jar.clear()
        payload = {
            "signin-input-app": "0",
            "signin-input-email": email,
            "signin-input-password": password,
            "signin-submit-button": "",
        }
        resp = await self._request(
            "POST",
            LOGIN_URL,
            data=payload,
            allow_redirects=True,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        text = await self._read_text(resp)
        final_url = str(resp.url)

        if "auth/login" in final_url and "2fa" not in final_url:
            raise DigiAuthError("Credentiale invalide")
        return final_url, text

    @staticmethod
    def _parse_attrs(tag: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        pattern = r'(\w+(?:-\w+)*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))'
        for key, value1, value2, value3 in re.findall(pattern, tag, re.I):
            attrs[key.lower()] = value1 or value2 or value3 or ""
        return attrs

    def _extract_hidden_inputs(self, html: str) -> dict[str, str]:
        hidden: dict[str, str] = {}
        for tag in RE_INPUT_TAG.findall(html):
            attrs = self._parse_attrs(tag)
            if attrs.get("type", "").lower() == "hidden" and attrs.get("name"):
                hidden[attrs["name"]] = attrs.get("value", "")
        return hidden

    def _parse_2fa_context(self, html: str) -> dict[str, dict[str, Any]]:
        methods: dict[str, dict[str, Any]] = {}
        hidden = self._extract_hidden_inputs(html)
        phone_value = None
        for key in ("form-phone-number-confirm", "phone", "phone-number-confirm", "form_phone_number_confirm"):
            value = hidden.get(key)
            if value and RE_HEX32.fullmatch(value):
                phone_value = value
                break
        if not phone_value:
            match = RE_PHONE_PARAM.search(html)
            if match:
                phone_value = match.group(1)
        if phone_value:
            methods["sms"] = {
                "send_url": TWO_FA_SEND_URL,
                "send_payload": {"action": "myAccount2FASend", "phone": phone_value},
                "validate_payload": {"action": "myAccount2FAVerify", "phone": phone_value},
            }
        return methods

    async def get_2fa_context(self, html: str | None = None) -> TwoFactorContext:
        if html is None:
            resp = await self._request("GET", TWO_FA_URL, allow_redirects=True)
            html = await self._read_text(resp)
        methods = self._parse_2fa_context(html)
        if not methods:
            raise DigiTwoFactorRequired("Nu am putut detecta metoda 2FA")
        return TwoFactorContext(methods=methods, html=html)

    async def send_2fa_code(self, context: TwoFactorContext, method: str) -> None:
        selected = context.methods.get(method)
        if not selected:
            raise DigiTwoFactorError("Metodă 2FA indisponibilă")
        resp = await self._request(
            "POST",
            selected["send_url"],
            data=selected["send_payload"],
            allow_redirects=True,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        if resp.status >= 400:
            raise DigiTwoFactorError(f"Eroare trimitere cod: HTTP {resp.status}")

    async def validate_2fa_code(self, context: TwoFactorContext, method: str, code: str) -> tuple[str, str]:
        selected = context.methods.get(method)
        if not selected:
            raise DigiTwoFactorError("Metodă 2FA indisponibilă")
        payload = dict(selected["validate_payload"])
        payload["code"] = code.strip()
        resp = await self._request(
            "POST",
            TWO_FA_VALIDATE_URL,
            data=payload,
            allow_redirects=True,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        raw = await self._read_text(resp)
        if resp.status >= 400:
            raise DigiTwoFactorError(f"Eroare validare cod: HTTP {resp.status}")
        try:
            data = json.loads(raw) if raw else {}
            if data and not data.get("success", True):
                raise DigiTwoFactorError(data.get("message") or "Cod invalid")
        except json.JSONDecodeError:
            pass
        follow = await self._request("GET", ADDRESS_SELECT_URL, allow_redirects=True)
        return str(follow.url), await self._read_text(follow)

    def _extract_radio_options(self, html: str) -> list[AddressOption]:
        labels = {key: self._clean_text(val) for key, val in RE_LABEL_FOR.findall(html)}
        options: list[AddressOption] = []
        for tag in RE_INPUT_TAG.findall(html):
            attrs = self._parse_attrs(tag)
            if attrs.get("type", "").lower() == "radio":
                input_id = attrs.get("id", "")
                value = attrs.get("value", "")
                label = labels.get(input_id, "")
                if value and label:
                    options.append(AddressOption(value=value, label=label))
        return options

    async def get_address_options(self, html: str | None = None) -> list[AddressOption]:
        if html is None:
            resp = await self._request("GET", ADDRESS_SELECT_URL, allow_redirects=True)
            html = await self._read_text(resp)
        options = self._extract_radio_options(html)
        if not options:
            for _, label in RE_ADDRESS_OPTION.findall(html):
                clean = self._clean_text(label)
                if clean and clean.lower() != "toate adresele":
                    options.append(AddressOption(value="", label=clean))
        return options

    async def confirm_address(self, address_id: str) -> None:
        payload = {"address": address_id, "order-btn-id": ""}
        resp = await self._request(
            "POST",
            ADDRESS_CONFIRM_URL,
            data=payload,
            allow_redirects=True,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        text = await self._read_text(resp)
        if resp.status >= 400:
            raise DigiAccountSelectionRequired(f"Address confirm failed: HTTP {resp.status}")
        try:
            data = json.loads(text) if text else {}
            if data and not data.get("success", True):
                raise DigiAccountSelectionRequired(data.get("message") or "Address confirm failed")
        except json.JSONDecodeError:
            pass

    async def async_fetch_data(self, history_limit: int = 5) -> dict[str, Any]:
        resp = await self._request("GET", INVOICES_URL, allow_redirects=True)
        html = await self._read_text(resp)
        final_url = str(resp.url)
        if "/auth/login" in final_url or "/auth/2fa" in final_url or "/auth/address-select" in final_url:
            raise DigiReauthRequired("Session expired")

        parsed = self._parse_invoice_page(html)
        rows: list[InvoiceSummary] = parsed["rows"]
        if not rows:
            raise DigiApiError("No invoices found")

        recent_ids_by_address: dict[str, list[str]] = {}
        for row in rows:
            bucket = recent_ids_by_address.setdefault(row.address_key, [])
            if len(bucket) < history_limit:
                bucket.append(row.invoice_id)

        details: dict[str, InvoiceDetail] = {}
        for invoice_id in {item for values in recent_ids_by_address.values() for item in values}:
            details[invoice_id] = await self._fetch_invoice_details(invoice_id)
            await asyncio.sleep(0.1)

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if row.invoice_id not in details:
                continue
            detail = details[row.invoice_id]
            grouped.setdefault(row.address_key, []).append(
                {
                    "invoice_id": row.invoice_id,
                    "address": row.address,
                    "issue_date": detail.issue_date or row.issue_date,
                    "due_date": detail.due_date or row.due_date,
                    "description": row.description,
                    "amount": detail.total if detail.total is not None else row.amount,
                    "rest": detail.rest if detail.rest is not None else 0.0,
                    "status": detail.status,
                    "invoice_number": detail.invoice_number,
                    "pdf_url": detail.pdf_url,
                    "services": detail.services,
                }
            )

        # flatten for current sensors: selected address or first
        keys = list(grouped.keys())
        if not keys:
            raise DigiApiError("No grouped invoices")
        selected_key = self.selected_address if self.selected_address in grouped else keys[0]
        items = sorted(grouped[selected_key], key=lambda x: self._parse_date_for_sort(x.get("issue_date")), reverse=True)
        latest = items[0]

        return {
            "invoice_id": latest.get("invoice_id"),
            "invoice_number": latest.get("invoice_number"),
            "date": latest.get("issue_date"),
            "due_date": latest.get("due_date"),
            "total_lei": latest.get("amount"),
            "rest_lei": latest.get("rest"),
            "status": latest.get("status"),
            "is_paid": (latest.get("rest") or 0) <= 0,
            "has_debt": (latest.get("rest") or 0) > 0,
            "services_count": len(latest.get("services") or []),
            "account_name": None,
            "current_address": latest.get("address"),
            "invoices_count": len(items),
            "recent_invoices": [
                {
                    "issue_date": x.get("issue_date"),
                    "category": x.get("description"),
                    "due_date": x.get("due_date"),
                    "amount_lei": x.get("amount"),
                }
                for x in items[:5]
            ],
            "address_key": selected_key,
        }

    async def fetch_latest_invoice(self) -> dict[str, Any]:
        return await self.async_fetch_data(history_limit=5)

    def _parse_invoice_page(self, html: str) -> dict[str, Any]:
        addresses: dict[str, str] = {key: self._clean_text(label) for key, label in RE_ADDRESS_OPTION.findall(html)}
        rows: list[InvoiceSummary] = []

        current_html = self._extract_section(html, "Facturi curente", "Facturi achitate")
        current_invoice_ids: list[str] = []
        if current_html:
            for address_key, invoice_id, issue_date, description, due_date, amount_text in RE_CURRENT_ROW.findall(current_html):
                current_invoice_ids.append(str(invoice_id))
                rows.append(InvoiceSummary(str(invoice_id), address_key, addresses.get(address_key, address_key), self._clean_text(issue_date), self._clean_text(due_date), self._clean_text(description), self._parse_money(amount_text) or 0.0))

        archive_html = self._extract_section(html, "Facturi achitate", None)
        archive_ids: list[str] = []
        cfg_match = RE_SCRIPT_CFG.search(html)
        if cfg_match:
            try:
                cfg = json.loads(unescape(cfg_match.group(1).strip()))
                all_ids = [str(item["id"]) for item in cfg if item.get("id")]
                current_ids_remaining = list(current_invoice_ids)
                for invoice_id in all_ids:
                    if invoice_id in current_ids_remaining:
                        current_ids_remaining.remove(invoice_id)
                    else:
                        archive_ids.append(invoice_id)
            except json.JSONDecodeError:
                pass

        archive_matches = list(RE_ROW.findall(archive_html if archive_html else html))
        for idx, match in enumerate(archive_matches):
            if idx >= len(archive_ids):
                break
            address_key, issue_date, description, due_date, amount_text = match
            rows.append(InvoiceSummary(archive_ids[idx], address_key, addresses.get(address_key, address_key), self._clean_text(issue_date), self._clean_text(due_date), self._clean_text(description), self._parse_money(amount_text) or 0.0))

        return {"rows": rows}

    async def _fetch_invoice_details(self, invoice_id: str) -> InvoiceDetail:
        payload = {"url": f"/my-account/invoices/details?invoice_id={invoice_id}", "id": invoice_id}
        resp = await self._request(
            "POST",
            f"{API_BASE}/my-account/invoices/details?invoice_id={invoice_id}",
            data=payload,
            allow_redirects=True,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"},
        )
        html = await self._read_text(resp)
        if resp.status >= 400:
            raise DigiApiError(f"Failed invoice details {invoice_id}: HTTP {resp.status}")

        html_unescaped = unescape(html)
        title_match = RE_DETAILS_TITLE.search(html_unescaped)
        pdf_match = RE_PDF.search(html_unescaped)
        label_money_matches = RE_LABEL_VALUE_MONEY.findall(html)
        money_map = {self._clean_text(label).lower(): self._parse_money(value) for label, value in label_money_matches}
        status_match = RE_LABEL_VALUE_TEXT.search(html_unescaped)

        services = []
        for raw_name, raw_price in RE_SERVICE_ROW.findall(html_unescaped):
            price_text = self._clean_text(raw_price)
            services.append({"name": self._clean_text(raw_name), "amount": self._parse_money(price_text), "raw_amount": price_text})

        invoice_number = self._clean_text(title_match.group(1)) if title_match else invoice_id
        issue_date = self._clean_text(title_match.group(2)) if title_match else None

        return InvoiceDetail(
            invoice_id=invoice_id,
            invoice_number=invoice_number,
            issue_date=issue_date,
            due_date=None,
            total=money_map.get("total"),
            rest=money_map.get("rest"),
            status=self._clean_text(status_match.group(1)) if status_match else None,
            pdf_url=urljoin(API_BASE, unescape(pdf_match.group(1))) if pdf_match else None,
            services=services,
        )

    @staticmethod
    def _parse_money(text: str | None) -> float | None:
        if text is None:
            return None
        clean = unescape(text).strip()
        clean = re.sub(r"[^0-9,.\-]", "", clean)
        if not clean:
            return None
        if "," in clean and "." in clean:
            clean = clean.replace(".", "").replace(",", ".") if clean.rfind(",") > clean.rfind(".") else clean.replace(",", "")
        elif "," in clean:
            clean = clean.replace(",", ".")
        elif "." not in clean:
            try:
                return int(clean) / 100
            except ValueError:
                return None
        try:
            return float(clean)
        except ValueError:
            return None

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", unescape(text)).strip()

    @staticmethod
    def _parse_date_for_sort(value: str | None) -> datetime:
        if not value:
            return datetime.min
        parts = value.strip().replace(".", "-").replace("/", "-").split("-")
        if len(parts) != 3:
            return datetime.min
        try:
            day, month, year = [int(part) for part in parts]
            return datetime(year, month, day)
        except ValueError:
            return datetime.min

    @staticmethod
    def _extract_section(html: str, start_marker: str, end_marker: str | None) -> str:
        start_idx = html.find(start_marker)
        if start_idx == -1:
            return ""
        sliced = html[start_idx:]
        if end_marker:
            end_idx = sliced.find(end_marker)
            if end_idx != -1:
                return sliced[:end_idx]
        return sliced
