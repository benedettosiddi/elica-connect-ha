# Elica Connect — Home Assistant Integration

Unofficial Home Assistant custom component for **Elica Connect** range hoods (ESP32-C6 based, app `com.replyconnect.elica`).

> Tested on: **Elica Cappa Connect** (dataModelIdx 8, PRF0199706)

## Features

| Entity | Type | Description |
|--------|------|-------------|
| Fan | `fan` | 4 speeds + boost (100%) |
| Light | `light` | On/off + brightness 0–100% |
| Filter | `sensor` | Grease filter efficiency % |

## Installation

### HACS (recommended)
1. In HACS → Custom repositories → add `benedettosiddi/elica-connect-ha` as **Integration**
2. Install **Elica Connect**
3. Restart Home Assistant

### Manual
Copy `custom_components/elica_connect/` into your HA `custom_components/` directory and restart.

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Elica Connect**
3. Enter the email and password of your Elica Connect app account

## Fan speeds

| HA percentage | Speed |
|---|---|
| 0% | Off |
| 25% | Low |
| 50% | Medium |
| 75% | High |
| 100% | Boost |

## Capability codes (dataModelIdx 8)

| Code | Description | Range |
|------|-------------|-------|
| 64 | Fan mode | 1=normal, 4=boost |
| 96 | Light brightness | 0–100 (%; 0=off) |
| 110 | Fan speed | 0=off, 1–3=speeds |

## Notes

- Cloud polling every 30 seconds — no local API
- Optimistic state updates (UI reflects commands instantly; syncs on next poll)
- Filter efficiency is read from the `filters[0].efficiency` field, not a capability code

## Disclaimer

This integration reverse-engineered the Elica Connect cloud API via mitmproxy. It is not affiliated with or endorsed by Elica S.p.A.
