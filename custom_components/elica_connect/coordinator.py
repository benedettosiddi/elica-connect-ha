"""DataUpdateCoordinator for Elica Connect."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    SCAN_INTERVAL,
    API_OAUTH_TOKEN,
    API_DEVICES,
    API_COMMANDS,
    API_DEVICE_STATE,
    COMMAND_TYPE,
    COMMAND_TIMEOUT,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_APP_UUID,
)

_LOGGER = logging.getLogger(__name__)


class ElicaConnectAPI:
    """Low-level REST client for cloudprod.elica.com/eiot-api/v1."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None

    async def async_login(self) -> str:
        """Authenticate via OAuth2 password grant and return the Bearer token."""
        payload = {
            "grant_type": "password",
            "username": self._email,
            "password": self._password,
            "scope": "default",
            "app_uuid": OAUTH_APP_UUID,
        }
        async with self._session.post(
            API_OAUTH_TOKEN,
            data=payload,
            auth=aiohttp.BasicAuth(OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET),
        ) as resp:
            if resp.status == 401:
                raise InvalidAuth("Invalid credentials")
            resp.raise_for_status()
            data = await resp.json()

        token = data.get("access_token")
        if not token:
            raise InvalidAuth(f"Token not found in login response: {list(data.keys())}")
        self._token = token
        return token

    @property
    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def _ensure_token(self) -> None:
        if not self._token:
            await self.async_login()

    async def async_get_devices(self) -> list[dict]:
        """Return list of devices associated to the account."""
        await self._ensure_token()
        async with self._session.get(API_DEVICES, headers=self._auth_headers) as resp:
            if resp.status == 401:
                await self.async_login()
                async with self._session.get(API_DEVICES, headers=self._auth_headers) as resp2:
                    resp2.raise_for_status()
                    data = await resp2.json()
            else:
                resp.raise_for_status()
                data = await resp.json()
        if isinstance(data, list):
            return data
        return data.get("devices") or data.get("data") or []

    async def async_get_device_state(self, device_id: str) -> dict:
        """Return full device JSON (includes dataModel and filters)."""
        await self._ensure_token()
        url = API_DEVICE_STATE.format(device_id=device_id)
        async with self._session.get(url, headers=self._auth_headers) as resp:
            if resp.status == 401:
                await self.async_login()
                async with self._session.get(url, headers=self._auth_headers) as resp2:
                    resp2.raise_for_status()
                    return await resp2.json()
            resp.raise_for_status()
            return await resp.json()

    async def async_send_command(self, device_id: str, capabilities: dict) -> None:
        """Send a capability command to the device."""
        await self._ensure_token()
        url = API_COMMANDS.format(device_id=device_id)
        # API expects string keys in capabilities
        str_caps = {str(k): v for k, v in capabilities.items()}
        payload = {
            "async": True,
            "capabilities": str_caps,
            "name": "capabilities",
            "timeout": COMMAND_TIMEOUT,
            "type": COMMAND_TYPE,
        }
        _LOGGER.debug("Sending command to %s: %s", device_id, capabilities)
        async with self._session.post(url, json=payload, headers=self._auth_headers) as resp:
            if resp.status == 401:
                await self.async_login()
                async with self._session.post(url, json=payload, headers=self._auth_headers) as resp2:
                    resp2.raise_for_status()
            else:
                resp.raise_for_status()


class ElicaConnectCoordinator(DataUpdateCoordinator):
    """Coordinator: polls device state every SCAN_INTERVAL seconds."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: ElicaConnectAPI,
        device_id: str,
        device_name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api = api
        self.device_id = device_id
        self.device_name = device_name
        # Full device JSON from last poll (for filter info etc.)
        self._device_raw: dict = {}

    @property
    def device_raw(self) -> dict:
        return self._device_raw

    async def _async_update_data(self) -> dict:
        """Fetch device state from API. Returns dataModel as {int_key: value}."""
        try:
            raw = await self.api.async_get_device_state(self.device_id)
        except aiohttp.ClientResponseError as err:
            raise UpdateFailed(f"API error {err.status}: {err.message}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error: {err}") from err

        self._device_raw = raw

        # State is in the dataModel field (confirmed via mitmproxy)
        data_model = raw.get("dataModel") or {}
        # Keys may be strings — normalise to int
        return {int(k): v for k, v in data_model.items()}


class InvalidAuth(Exception):
    """Raised when credentials are rejected."""
