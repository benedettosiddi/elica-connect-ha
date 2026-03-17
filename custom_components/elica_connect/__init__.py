"""Elica Connect integration for Home Assistant.

Protocol analysis:
  - Device: ESP32-C6, hostname ELC-HOOD-ESP32C6-F0F5BD02CF3D
  - Cloud MQTT broker: cloudprodmqtt.elica.com:8883 (TLS)
  - Backend: AWS ELB eu-central-1 (Reply S.p.A. eiot platform)
  - REST API: https://cloudprod.elica.com/eiot-api/v1/
  - No local API available
"""
from __future__ import annotations

import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_DEVICE_ID, CONF_DEVICE_NAME
from .coordinator import ElicaConnectAPI, ElicaConnectCoordinator  # noqa: F401

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.FAN, Platform.LIGHT, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Elica Connect from a config entry."""
    session = async_get_clientsession(hass)
    api = ElicaConnectAPI(
        session,
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )

    coordinator = ElicaConnectCoordinator(
        hass,
        api,
        device_id=entry.data[CONF_DEVICE_ID],
        device_name=entry.data[CONF_DEVICE_NAME],
    )

    await coordinator.async_config_entry_first_refresh()

    # Start MQTT push updates (cuid is now available from first REST poll)
    coordinator.async_start_mqtt()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: ElicaConnectCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.stop_mqtt()
    return unloaded
