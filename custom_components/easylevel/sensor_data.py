"""
EasyLevel BLE sensor data parser.

This module is HA-independent so it can be unit-tested standalone.
It decodes the raw GATT characteristic bytes into tilt angles.

Protocol (reverse-engineered from live BLE capture):
  Characteristic faf52c21 — 12 bytes = 6 × int16 little-endian
    [0] accel_x  — raw accelerometer X axis (~16384 = 1g)
    [1] accel_y  — raw accelerometer Y axis
    [2] accel_z  — raw accelerometer Z axis  (≈16365 at rest, sensor flat)
    [3] gyro_x   — raw gyroscope X (near 0 at rest)
    [4] gyro_y   — raw gyroscope Y
    [5] gyro_z   — raw gyroscope Z

  Tilt angles are derived via standard 3-axis accelerometer formula:
    pitch = atan2(-accel_x, sqrt(accel_y² + accel_z²))   front/back tilt
    roll  = atan2( accel_y, sqrt(accel_x² + accel_z²))   left/right tilt

  Characteristic faf52c22 — 20 bytes (static, never changes during use)
    Believed to be the zero-level calibration set by the user in the app.
    [0] pitch_offset × 100  (int16)
    [1] roll_offset  × 100  (int16)
    … remaining bytes unknown

  Characteristic 36ba807d — 8 bytes — device info / firmware version
"""

from __future__ import annotations

import math
import struct
from collections import deque
from dataclasses import dataclass


@dataclass
class EasyLevelData:
    """Parsed sensor reading."""

    pitch: float          # degrees, front/back tilt  (+ = nose up)
    roll: float           # degrees, left/right tilt  (+ = right side up)
    accel_x: int          # raw int16
    accel_y: int          # raw int16
    accel_z: int          # raw int16
    gyro_x: int           # raw int16
    gyro_y: int           # raw int16
    gyro_z: int           # raw int16
    gravity_magnitude: float  # should be ~16384 when still


def _accel_to_angles(ax: int, ay: int, az: int) -> tuple[float, float]:
    """
    Convert raw accelerometer int16 to tilt angles in degrees.

    Uses the full 3-axis formula which is stable at all orientations:
      pitch = atan2(-ax, sqrt(ay² + az²))
      roll  = atan2( ay, sqrt(ax² + az²))
    """
    pitch = math.degrees(math.atan2(-ax, math.sqrt(ay * ay + az * az)))
    roll = math.degrees(math.atan2(ay, math.sqrt(ax * ax + az * az)))
    return round(pitch, 2), round(roll, 2)


def parse_accel_packet(data: bytes) -> EasyLevelData | None:
    """
    Parse the 12-byte CHAR_ACCEL characteristic value.

    Returns None if the packet is too short or malformed.
    """
    if len(data) < 12:
        return None

    try:
        ax, ay, az, gx, gy, gz = struct.unpack_from("<6h", data)
    except struct.error:
        return None

    pitch, roll = _accel_to_angles(ax, ay, az)
    mag = math.sqrt(ax * ax + ay * ay + az * az)

    return EasyLevelData(
        pitch=pitch,
        roll=roll,
        accel_x=ax,
        accel_y=ay,
        accel_z=az,
        gyro_x=gx,
        gyro_y=gy,
        gyro_z=gz,
        gravity_magnitude=round(mag, 1),
    )


class MovingAverage:
    """Simple fixed-window moving average for smoothing noisy sensor readings."""

    def __init__(self, window: int = 5) -> None:
        self._q: deque[float] = deque(maxlen=window)

    def update(self, value: float) -> float:
        """Add a new value and return the current average."""
        self._q.append(value)
        return round(sum(self._q) / len(self._q), 2)

    @property
    def ready(self) -> bool:
        """True once the window is full."""
        return len(self._q) == self._q.maxlen


class EasyLevelParser:
    """
    Stateful parser that maintains moving averages across packets.

    One instance per device, lives in the coordinator.
    """

    def __init__(self, smoothing_window: int = 5) -> None:
        self._pitch_avg = MovingAverage(smoothing_window)
        self._roll_avg = MovingAverage(smoothing_window)
        self.last_raw: EasyLevelData | None = None
        self.pitch: float | None = None
        self.roll: float | None = None

    def update(self, data: bytes) -> EasyLevelData | None:
        """
        Parse a new packet and update smoothed angles.

        Returns the raw parsed data (unsmoothed), or None on parse failure.
        Smoothed values are available via self.pitch / self.roll.
        """
        parsed = parse_accel_packet(data)
        if parsed is None:
            return None

        self.last_raw = parsed
        self.pitch = self._pitch_avg.update(parsed.pitch)
        self.roll = self._roll_avg.update(parsed.roll)
        return parsed
