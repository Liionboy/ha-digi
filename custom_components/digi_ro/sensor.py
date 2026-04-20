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
        DigiInvoiceSensor(coordinator, "total_lei", "Digi total ultima factură", "lei"),
        DigiInvoiceSensor(coordinator, "rest_lei", "Digi rest de plată", "lei"),
        DigiInvoiceSensor(coordinator, "status", "Digi status ultima factură", None),
        DigiInvoiceSensor(coordinator, "date", "Digi data ultimei facturi", None),
    ])


class DigiInvoiceSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, key: str, name: str, unit: str | None) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"digi_ro_{key}"
        if unit:
            self._attr_native_unit_of_measurement = unit

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
