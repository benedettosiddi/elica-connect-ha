"""Constants for Elica Connect integration."""

DOMAIN = "elica_connect"
MANUFACTURER = "Elica S.p.A."

# Cloud API
API_BASE = "https://cloudprod.elica.com/eiot-api/v1"
API_OAUTH_TOKEN = f"{API_BASE}/oauth/token"
API_DEVICES = f"{API_BASE}/devices"
API_COMMANDS = f"{API_BASE}/devices/{{device_id}}/commands"
API_DEVICE_STATE = f"{API_BASE}/devices/{{device_id}}"

# OAuth2 client credentials (eiot platform, extracted via mitmproxy)
OAUTH_CLIENT_ID = "eiot-app"
OAUTH_CLIENT_SECRET = "VqwG1KTB77UeROu"
OAUTH_APP_UUID = "c48d13c2352cc536"

# Update interval (seconds)
SCAN_INTERVAL = 30

# Config entry keys
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"

# Hood capability codes (confirmed via mitmproxy on real device, dataModelIdx=8)
CAP_FAN_SPEED = 110    # 0=off, 1=low, 2=medium, 3=high (not used for boost)
CAP_FAN_MODE = 64      # 1=normal operation, 4=boost mode
CAP_LIGHT_BRIGHTNESS = 96  # light brightness 0–100 (%; 0=off)

# Fan speed levels (0=off, 1-3=normal, 4=boost)
FAN_SPEED_TO_PCT = {0: 0, 1: 25, 2: 50, 3: 75, 4: 100}

# Fan commands (capability payloads) as observed from app
FAN_CMD = {
    0: {64: 1, 110: 0},   # off
    1: {64: 1, 110: 1},   # low
    2: {64: 1, 110: 2},   # medium
    3: {64: 1, 110: 3},   # high
    4: {64: 4},            # boost
}

# Light
LIGHT_BRIGHTNESS_MAX_HA = 255
LIGHT_BRIGHTNESS_MAX_ELICA = 100  # capability 96: 0–100 (%)

# Command type
COMMAND_TYPE = "Hood"
COMMAND_TIMEOUT = 30000  # ms

# MQTT (cloud push, confirmed via APK reverse engineering + live capture)
MQTT_HOST = "cloudprodmqtt.elica.com"
MQTT_PORT = 8883
MQTT_TOPIC_STATE = "v1/device/{cuid}/statusjson"
# Fallback poll interval when MQTT is connected (5 min sanity check)
SCAN_INTERVAL_MQTT = 300
