"""DataUpdateCoordinator for Elica Connect."""
from __future__ import annotations

import base64
import json
import logging
import ssl
import threading
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    SCAN_INTERVAL,
    SCAN_INTERVAL_MQTT,
    API_OAUTH_TOKEN,
    API_DEVICES,
    API_COMMANDS,
    API_DEVICE_STATE,
    COMMAND_TYPE,
    COMMAND_TIMEOUT,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_APP_UUID,
    MQTT_HOST,
    MQTT_PORT,
    MQTT_TOPIC_STATE,
)

_LOGGER = logging.getLogger(__name__)


def _decode_jwt(token: str) -> dict:
    """Decode JWT payload (no signature verification)."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _make_mqtt_client(client_id: str):
    """Create paho-mqtt client, compatible with paho-mqtt 1.x and 2.x."""
    import paho.mqtt.client as mqtt  # noqa: PLC0415

    try:
        # paho-mqtt >= 2.0
        return mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
    except AttributeError:
        # paho-mqtt < 2.0
        return mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)


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
    def token(self) -> str | None:
        return self._token

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
    """Coordinator: MQTT push updates + REST fallback poll."""

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
        self._device_raw: dict = {}
        # cuid extracted from REST API response (needed for MQTT topic)
        self._cuid: str | None = None
        # Full merged state (REST full state + MQTT deltas)
        self._state_cache: dict[int, int] = {}
        # paho-mqtt client running in a daemon thread
        self._mqtt_client = None
        self._mqtt_thread: threading.Thread | None = None

    @property
    def device_raw(self) -> dict:
        return self._device_raw

    async def _async_update_data(self) -> dict:
        """Fetch device state from REST API (fallback/sanity check)."""
        try:
            raw = await self.api.async_get_device_state(self.device_id)
        except aiohttp.ClientResponseError as err:
            raise UpdateFailed(f"API error {err.status}: {err.message}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error: {err}") from err

        self._device_raw = raw

        # Extract cuid for MQTT (available after first REST call)
        if not self._cuid:
            self._cuid = raw.get("cuid") or raw.get("serialNumber")

        data_model = raw.get("dataModel") or {}
        new_state = {int(k): v for k, v in data_model.items()}
        # Merge REST data into cache (REST is authoritative for full state)
        self._state_cache.update(new_state)
        return dict(self._state_cache)

    def async_start_mqtt(self) -> None:
        """Start MQTT subscription for real-time push updates.

        Called from the HA event loop after first_refresh succeeds.
        Runs the paho-mqtt loop in a daemon thread.
        """
        if not self._cuid:
            _LOGGER.warning("Elica MQTT: cuid not available, skipping MQTT setup")
            return

        token = self.api.token
        if not token:
            _LOGGER.warning("Elica MQTT: no token available, skipping MQTT setup")
            return

        try:
            jwt = _decode_jwt(token)
        except Exception as ex:
            _LOGGER.warning("Elica MQTT: JWT decode failed: %s", ex)
            return

        mqtt_usr = jwt.get("mqtt_usr")
        mqtt_psw = jwt.get("mqtt_psw")
        if not mqtt_usr or not mqtt_psw:
            _LOGGER.warning("Elica MQTT: credentials not in JWT, skipping MQTT setup")
            return

        topic = MQTT_TOPIC_STATE.format(cuid=self._cuid)
        _LOGGER.debug("Elica MQTT: subscribing to %s", topic)

        # Switch to slower REST fallback poll now that MQTT is active
        self.update_interval = timedelta(seconds=SCAN_INTERVAL_MQTT)

        def on_connect(client, userdata, flags, rc):
            rc_val = rc if isinstance(rc, int) else getattr(rc, "value", 0)
            if rc_val == 0:
                client.subscribe(topic, qos=1)
                _LOGGER.debug("Elica MQTT: connected and subscribed to %s", topic)
            else:
                _LOGGER.warning("Elica MQTT: connection refused rc=%s", rc_val)

        def on_disconnect(client, userdata, rc):
            _LOGGER.debug("Elica MQTT: disconnected rc=%s", rc)

        def on_message(client, userdata, msg):
            try:
                payload = json.loads(msg.payload)
                # Payload: [{"dataModel": {"64": 1, "110": 0, ...}}]
                data_model = payload[0]["dataModel"]
                self._state_cache.update({int(k): v for k, v in data_model.items()})
                new_data = dict(self._state_cache)
                # Push update to HA entities from the MQTT thread
                self.hass.loop.call_soon_threadsafe(
                    self.async_set_updated_data, new_data
                )
                _LOGGER.debug("Elica MQTT: state update %s", data_model)
            except Exception as ex:
                _LOGGER.debug("Elica MQTT: message parse error: %s", ex)

        client = _make_mqtt_client(mqtt_usr)
        client.username_pw_set(mqtt_usr, mqtt_psw)
        client.tls_set_context(ssl.create_default_context())
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        self._mqtt_client = client

        def _run() -> None:
            try:
                client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
                client.loop_forever()
            except Exception as ex:
                _LOGGER.error("Elica MQTT thread error: %s", ex)

        self._mqtt_thread = threading.Thread(
            target=_run, daemon=True, name=f"elica_mqtt_{self._cuid}"
        )
        self._mqtt_thread.start()
        _LOGGER.debug("Elica MQTT: thread started for cuid=%s", self._cuid)

    def stop_mqtt(self) -> None:
        """Disconnect MQTT client (called on integration unload)."""
        if self._mqtt_client:
            try:
                self._mqtt_client.disconnect()
            except Exception:
                pass
            self._mqtt_client = None


class InvalidAuth(Exception):
    """Raised when credentials are rejected."""
