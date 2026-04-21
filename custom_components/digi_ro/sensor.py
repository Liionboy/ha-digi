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
        DigiInvoiceSensor(coordinator, "total_lei", "Digi total ultima factură", "lei", "mdi:cash-multiple"),
        DigiInvoiceSensor(coordinator, "rest_lei", "Digi rest de plată", "lei", "mdi:cash-clock"),
        DigiInvoiceSensor(coordinator, "status", "Digi status ultima factură", None, "mdi:file-document-check"),
        DigiInvoiceSensor(coordinator, "date", "Digi data ultimei facturi", None, "mdi:calendar"),
        DigiInvoiceSensor(coordinator, "due_date", "Digi scadență ultima factură", None, "mdi:calendar-alert"),
        DigiInvoiceSensor(coordinator, "invoice_id", "Digi invoice ID", None, "mdi:identifier"),
        DigiInvoiceSensor(coordinator, "invoice_number", "Digi număr factură", None, "mdi:barcode"),
        DigiInvoiceSensor(coordinator, "is_paid", "Digi factură achitată", None, "mdi:check-decagram"),
        DigiInvoiceSensor(coordinator, "has_debt", "Digi are rest de plată", None, "mdi:alert-circle"),
        DigiInvoiceSensor(coordinator, "services_count", "Digi poziții servicii factură", None, "mdi:format-list-numbered"),
        DigiInvoiceSensor(coordinator, "account_name", "Digi nume cont", None, "mdi:account"),
        DigiInvoiceSensor(coordinator, "current_address", "Digi adresă curentă", None, "mdi:home-city"),
        DigiInvoiceSensor(coordinator, "invoices_count", "Digi număr facturi detectate", None, "mdi:file-multiple"),
        DigiRecentInvoicesSensor(coordinator),
    ])


class DigiInvoiceSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, key: str, name: str, unit: str | None, icon: str | None = None) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"digi_ro_{key}"
        if unit:
            self._attr_native_unit_of_measurement = unit
        if icon:
            self._attr_icon = icon

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._key)

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        return {
            "invoice_id": d.get("invoice_id"),
            "attribution": ATTRIBUTION,
        }


class DigiRecentInvoicesSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Digi facturi recente"
        self._attr_unique_id = "digi_ro_recent_invoices"
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
