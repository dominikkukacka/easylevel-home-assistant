# EasyLevel Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/dominikkukacka/easylevel-home-assistant/actions/workflows/validate.yaml/badge.svg)](https://github.com/dominikkukacka/easylevel-home-assistant/actions/workflows/validate.yaml)

Home Assistant integration for the [EasyLevel](https://easylevel.com) caravan and motorhome leveling sensor by [CaraTech AB](https://www.caratechab.com).

The EasyLevel sensor is a Bluetooth Low Energy (BLE) accelerometer that mounts on your caravan or motorhome and broadcasts real-time tilt angles so you can level it precisely — no app required once this integration is set up.

---

## Sensors

| Entity | Unit | Description | Enabled by default |
|---|---|---|---|
| `sensor.easylevel_pitch` | ° | Front/back tilt, 5-sample smoothed | ✅ |
| `sensor.easylevel_roll` | ° | Left/right tilt, 5-sample smoothed | ✅ |
| `sensor.easylevel_pitch_raw` | ° | Instantaneous pitch (no smoothing) | ❌ |
| `sensor.easylevel_roll_raw` | ° | Instantaneous roll (no smoothing) | ❌ |
| `sensor.easylevel_gravity_magnitude` | — | Raw accelerometer vector length (~16384 at rest) | ❌ |

Positive pitch = nose up. Positive roll = right side up.

---

## Requirements

- Home Assistant **2024.1.0** or newer
- A Bluetooth adapter or [Bluetooth proxy](https://www.home-assistant.io/integrations/bluetooth/) within range of your sensor

> **Important:** This integration makes an **active GATT connection** to the sensor to read data. Broadcast-only (passive) Bluetooth proxies are **not** supported — you need either a direct Bluetooth adapter on your HA host or a connectable ESPHome proxy.

---

## Installation via HACS

1. Open **HACS** in Home Assistant
2. Click the three-dot menu (⋮) → **Custom repositories**
3. Paste `https://github.com/dominikkukacka/easylevel-home-assistant`, set type to **Integration**, click **Add**
4. Find **EasyLevel** in the HACS list and click **Download**
5. Restart Home Assistant

## Manual Installation

```bash
# From the root of this repository:
cp -r custom_components/easylevel /config/custom_components/
# Then restart Home Assistant
```

---

## Setup

1. Power on your EasyLevel sensor and bring it within Bluetooth range of your HA host
2. Go to **Settings → Devices & Services**
3. HA auto-discovers the sensor and shows a notification banner — click **Configure** to confirm
4. If not auto-discovered: click **+ Add Integration**, search for **EasyLevel**, and select your device from the list

---

## Options

After setup, click **Configure** on the EasyLevel integration card to adjust:

| Option | Default | Description |
|---|---|---|
| **Enable polling** | On | Uncheck to stop connecting to the sensor entirely. Existing sensor values are kept but stop updating. Useful when parked and leveled — re-enable when you move pitch. |
| **Poll interval** | 30 s | How often to connect and take a fresh reading. Range: 5 – 3600 seconds. Lower = more frequent updates, more battery use. |

Changes take effect immediately — no restart required.

---

## How It Works

The sensor (BLE device name prefix: `CARATI`) exposes a proprietary GATT service. The integration:

1. Listens passively for BLE advertisements to detect when the sensor is nearby
2. Every *poll interval* seconds, makes an active GATT connection
3. Subscribes to notifications on characteristic `faf52c21-5078-11e9-b475-0800200c9a66` for ~2 seconds (~60 packets at 30 Hz)
4. Applies a 5-sample moving average to smooth out MEMS noise (raw accuracy ≈ ±0.1°, smoothed ≈ ±0.02°)
5. Disconnects to preserve sensor battery life

Each 12-byte notification packet contains 6 × int16 little-endian values: `[accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z]`. Tilt angles are derived via the standard 3-axis accelerometer formula:

```
pitch = atan2(-accel_x, sqrt(accel_y² + accel_z²))   # front/back
roll  = atan2( accel_y, sqrt(accel_x² + accel_z²))   # left/right
```

The second service (`5f672748-...`) contains static calibration data and a writable config register — these are read on first connection but not used for angle calculation.

---

## License

MIT
