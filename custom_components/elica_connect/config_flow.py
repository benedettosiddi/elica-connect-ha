"""Config flow for Elica Connect."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_DEVICE_ID, CONF_DEVICE_NAME
from .coordinator import ElicaConnectAPI, InvalidAuth

_LOGGER = logging.getLogger(__name__)


class ElicaConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle setup from the HA UI."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str = ""
        self._password: str = ""
        self._api: ElicaConnectAPI | None = None
        self._devices: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 1: ask for email and password."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]

            session = async_get_clientsession(self.hass)
            self._api = ElicaConnectAPI(session, self._email, self._password)

            try:
                await self._api.async_login()
                self._devices = await self._api.async_get_devices()
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "unknown"

            if not errors:
                if len(self._devices) == 0:
                    errors["base"] = "no_devices"
                elif len(self._devices) == 1:
                    return self._create_entry(self._devices[0])
                else:
                    return await self.async_step_select_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 2 (only if multiple devices): pick the hood."""
        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            device = next(
                (d for d in self._devices if self._device_id(d) == device_id), None
            )
            if device:
                return self._create_entry(device)

        device_options = {
            self._device_id(d): self._device_name(d) for d in self._devices
        }

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_ID): vol.In(device_options)}
            ),
        )

    def _create_entry(self, device: dict) -> config_entries.FlowResult:
        device_id = self._device_id(device)
        device_name = self._device_name(device)
        return self.async_create_entry(
            title=device_name,
            data={
                CONF_EMAIL: self._email,
                CONF_PASSWORD: self._password,
                CONF_DEVICE_ID: device_id,
                CONF_DEVICE_NAME: device_name,
            },
        )

    @staticmethod
    def _device_id(device: dict) -> str:
        return str(
            device.get("id")
            or device.get("deviceId")
            or device.get("serialNumber")
            or device.get("serial")
            or ""
        )

    @staticmethod
    def _device_name(device: dict) -> str:
        return str(
            device.get("name")
            or device.get("deviceName")
            or device.get("alias")
            or device.get("id")
            or "Elica Hood"
        )
