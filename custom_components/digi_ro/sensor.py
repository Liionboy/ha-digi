from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        DigiInvoiceSensor(entry, coordinator, "total_lei", "Digi total ultima factură", "lei", "mdi:cash-multiple"),
        DigiInvoiceSensor(entry, coordinator, "rest_lei", "Digi rest de plată", "lei", "mdi:cash-clock"),
        DigiInvoiceSensor(entry, coordinator, "status", "Digi status ultima factură", None, "mdi:file-document-check"),
        DigiInvoiceSensor(entry, coordinator, "date", "Digi data ultimei facturi", None, "mdi:calendar"),
        DigiInvoiceSensor(entry, coordinator, "due_date", "Digi scadență ultima factură", None, "mdi:calendar-alert"),
        DigiInvoiceSensor(entry, coordinator, "invoice_id", "Digi invoice ID", None, "mdi:identifier"),
        DigiInvoiceSensor(entry, coordinator, "invoice_number", "Digi număr factură", None, "mdi:barcode"),
        DigiInvoiceSensor(entry, coordinator, "is_paid", "Digi factură achitată", None, "mdi:check-decagram"),
        DigiInvoiceSensor(entry, coordinator, "has_debt", "Digi are rest de plată", None, "mdi:alert-circle"),
        DigiInvoiceSensor(entry, coordinator, "services_count", "Digi poziții servicii factură", None, "mdi:format-list-numbered"),
        DigiInvoiceSensor(entry, coordinator, "account_name", "Digi nume cont", None, "mdi:account"),
        DigiInvoiceSensor(entry, coordinator, "current_address", "Digi adresă curentă", None, "mdi:home-city"),
        DigiInvoiceSensor(entry, coordinator, "invoices_count", "Digi număr facturi detectate", None, "mdi:file-multiple"),
        DigiRecentInvoicesSensor(entry, coordinator),
    ])


class DigiInvoiceSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, entry: ConfigEntry, coordinator, key: str, name: str, unit: str | None, icon: str | None = None) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"digi_ro_{entry.entry_id}_{key}"
        if unit:
            self._attr_native_unit_of_measurement = unit
        if icon:
            self._attr_icon = icon

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        value = data.get(self._key)
        if self._key == "due_date" and value in (None, "", "unknown"):
            if data.get("is_paid") is True:
                return "Fără scadență"
        return value

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        return {
            "invoice_id": d.get("invoice_id"),
            "attribution": ATTRIBUTION,
        }


class DigiRecentInvoicesSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, entry: ConfigEntry, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Digi facturi recente"
        self._attr_unique_id = f"digi_ro_{entry.entry_id}_recent_invoices"
        self._attr_icon = "mdi:history"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return len(data.get("recent_invoices") or [])

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        attrs = {
            "invoice_id": d.get("invoice_id"),
            "attribution": ATTRIBUTION,
        }
        recent = d.get("recent_invoices") or []
        for i, inv in enumerate(recent[:5], start=1):
            attrs[f"Factura {i} - data emitere"] = inv.get("issue_date")
            attrs[f"Factura {i} - scadență"] = inv.get("due_date")
            attrs[f"Factura {i} - categorie"] = inv.get("category")
            attrs[f"Factura {i} - valoare (lei)"] = inv.get("amount_lei")
        return attrs
