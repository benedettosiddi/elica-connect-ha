"""Sensor platform for Elica Connect (filter efficiency)."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ElicaConnectCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ElicaConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ElicaFilterSensor(coordinator, entry)])


class ElicaFilterSensor(CoordinatorEntity, SensorEntity):
    """Filter efficiency sensor — 100% = clean, lower = needs cleaning.

    Data comes from device JSON filters[0].efficiency (not a dataModel capability).
    """

    _attr_has_entity_name = True
    _attr_name = "Filter"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:air-filter"

    def __init__(self, coordinator: ElicaConnectCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.data['device_id']}_filter"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["device_id"])},
            "name": coordinator.device_name,
            "manufacturer": MANUFACTURER,
            "model": "Elica Connect Hood",
            "serial_number": entry.data["device_id"],
        }

    @property
    def native_value(self) -> int | None:
        filters = self.coordinator.device_raw.get("filters") or []
        if not filters:
            return None
        return filters[0].get("efficiency")

    @property
    def available(self) -> bool:
        filters = self.coordinator.device_raw.get("filters") or []
        return bool(filters and filters[0].get("efficiency") is not None)

    @property
    def extra_state_attributes(self) -> dict:
        filters = self.coordinator.device_raw.get("filters") or []
        if not filters:
            return {}
        f = filters[0]
        return {
            "status": f.get("status"),
            "filter_type": f.get("type"),
            "last_reset": f.get("lastReset"),
        }
