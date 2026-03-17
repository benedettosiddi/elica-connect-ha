"""Light platform for Elica Connect (integrated LED panel)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    CAP_LIGHT_BRIGHTNESS,
    LIGHT_BRIGHTNESS_MAX_HA,
    LIGHT_BRIGHTNESS_MAX_ELICA,
)
from .coordinator import ElicaConnectCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ElicaConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ElicaHoodLight(coordinator, entry)])


class ElicaHoodLight(CoordinatorEntity, LightEntity):
    """Elica hood integrated light.

    cap 96 = brightness 0–100 (%; 0 = off).
    Uses optimistic state to avoid stale reads immediately after a command.
    """

    _attr_has_entity_name = True
    _attr_name = "Light"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator: ElicaConnectCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.data['device_id']}_light"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["device_id"])},
            "name": coordinator.device_name,
            "manufacturer": MANUFACTURER,
            "model": "Elica Connect Hood",
            "serial_number": entry.data["device_id"],
        }
        # Optimistic brightness override (cleared on next coordinator update)
        self._optimistic_brightness: int | None = None

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state when real data arrives."""
        self._optimistic_brightness = None
        super()._handle_coordinator_update()

    @property
    def _brightness_elica(self) -> int:
        if self._optimistic_brightness is not None:
            return self._optimistic_brightness
        return (self.coordinator.data or {}).get(CAP_LIGHT_BRIGHTNESS, 0)

    @property
    def is_on(self) -> bool:
        return self._brightness_elica > 0

    @property
    def brightness(self) -> int | None:
        return round(self._brightness_elica * LIGHT_BRIGHTNESS_MAX_HA / LIGHT_BRIGHTNESS_MAX_ELICA)

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness_ha = kwargs.get(ATTR_BRIGHTNESS)
        if brightness_ha is not None:
            elica_val = round(brightness_ha * LIGHT_BRIGHTNESS_MAX_ELICA / LIGHT_BRIGHTNESS_MAX_HA)
            elica_val = max(1, min(elica_val, LIGHT_BRIGHTNESS_MAX_ELICA))
        else:
            current = self._brightness_elica
            elica_val = current if current > 0 else LIGHT_BRIGHTNESS_MAX_ELICA

        self._optimistic_brightness = elica_val
        self.async_write_ha_state()
        await self.coordinator.api.async_send_command(
            self.coordinator.device_id, {CAP_LIGHT_BRIGHTNESS: elica_val}
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._optimistic_brightness = 0
        self.async_write_ha_state()
        await self.coordinator.api.async_send_command(
            self.coordinator.device_id, {CAP_LIGHT_BRIGHTNESS: 0}
        )
