# EasyLevel Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/dominikkukacka/easylevel-home-assistant/actions/workflows/validate.yaml/badge.svg)](https://github.com/dominikkukacka/easylevel-home-assistant/actions/workflows/validate.yaml)

Home Assistant integration for the [EasyLevel](https://easylevel.com) caravan and motorhome leveling sensor by CaraTech AB.

The EasyLevel sensor is a BLE (Bluetooth Low Energy) accelerometer that mounts on your caravan or motorhome and reports tilt angles so you can level it precisely.

## Sensors

| Entity | Unit | Description |
|---|---|---|
| `sensor.easylevel_pitch` | ° | Front/back tilt (smoothed, 5-sample average) |
| `sensor.easylevel_roll` | ° | Left/right tilt (smoothed, 5-sample average) |
| `sensor.easylevel_pitch_raw` | ° | Instantaneous pitch (disabled by default) |
| `sensor.easylevel_roll_raw` | ° | Instantaneous roll (disabled by default) |
| `sensor.easylevel_gravity_magnitude` | — | Raw accelerometer magnitude, ~16384 at rest (disabled by default) |

## Requirements

- Home Assistant 2024.1.0 or newer
- A Bluetooth adapter or [Bluetooth proxy](https://www.home-assistant.io/integrations/bluetooth/) reachable from your HA instance
- An EasyLevel sensor (buy at [easylevel.com](https://easylevel.com))

> **Note:** This integration makes an active GATT connection to the sensor. Broadcast-only Bluetooth proxies are **not** supported — you need a connectable proxy or a direct Bluetooth adapter.

## Installation via HACS

1. Open HACS in Home Assistant
2. Click the three-dot menu → **Custom repositories**
3. Add `https://github.com/dominikkukacka/easylevel-home-assistant` as type **Integration**
4. Click **Download**
5. Restart Home Assistant

## Manual Installation

```bash
# Copy the integration into your HA config directory
cp -r custom_components/easylevel /config/custom_components/
# Then restart Home Assistant
```

## Setup

1. Make sure your EasyLevel sensor is powered on and within Bluetooth range
2. Go to **Settings → Devices & Services**
3. Home Assistant should auto-discover the device and show a notification — click **Configure**
4. If not auto-discovered, click **+ Add Integration**, search for **EasyLevel**, and follow the prompts

## Protocol Notes

The sensor (BLE device name: `CARATII` / `CARATIC` etc.) exposes a custom GATT service. Data is read from characteristic `faf52c21-5078-11e9-b475-0800200c9a66` as 6 × int16 little-endian values representing raw accelerometer (X, Y, Z) and gyroscope (X, Y, Z) axes. Tilt angles are computed via:

```
pitch = atan2(-accel_x, sqrt(accel_y² + accel_z²))
roll  = atan2( accel_y, sqrt(accel_x² + accel_z²))
```

The integration connects every 30 seconds, subscribes to GATT notifications for ~2 seconds, applies a 5-sample moving average, then disconnects to preserve battery life.

## License

MIT
