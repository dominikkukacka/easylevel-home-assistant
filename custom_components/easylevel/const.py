"""Constants for the EasyLevel integration."""

DOMAIN = "easylevel"
DEVICE_NAME_PREFIX = "CARATI"

# ── GATT UUIDs (discovered via nRF Connect) ───────────────────────────────────

# Service 1 — accelerometer / tilt data
SERVICE_TILT = "faf52c20-5078-11e9-b475-0800200c9a66"

# 12 bytes, NOTIFY+READ — live IMU data: [accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z] int16 LE
CHAR_ACCEL = "faf52c21-5078-11e9-b475-0800200c9a66"

# 20 bytes, NOTIFY+READ — static calibration / zero-offset data (set by app)
CHAR_CALIB_STATIC = "faf52c22-5078-11e9-b475-0800200c9a66"

# Service 2 — device config / info
SERVICE_CONFIG = "5f672748-a643-4076-8b51-356af86e598e"

# 8 bytes, READ — device info / firmware version
CHAR_DEVICE_INFO = "36ba807d-0198-47fd-ab90-ccf88d990cf1"

# 9 bytes, READ+WRITE — mode/config register (byte[0]=2 = normal operation)
CHAR_CONFIG = "4ef2f24e-5b15-4502-9734-c68b7ba042d2"

# 20 bytes, READ+WRITE — user zero-level calibration storage
CHAR_ZERO_CALIB = "3535cf62-9e3a-4239-8027-c85c281eaa83"

# 4 bytes, READ+NOTIFY — unknown, always 0
CHAR_UNKNOWN = "04e2cc0e-7f56-4fb0-8a0b-0742c3fb0661"

# ── Sensor keys ───────────────────────────────────────────────────────────────

KEY_PITCH = "pitch"
KEY_ROLL = "roll"
KEY_PITCH_RAW = "pitch_raw"
KEY_ROLL_RAW = "roll_raw"
KEY_SIGNAL_STRENGTH = "signal_strength"

# ── Physics constant ──────────────────────────────────────────────────────────

# Nominal 1g in raw accelerometer counts (2^14 = 16384 for a ±2g 14-bit sensor)
ONE_G_RAW = 16384.0

# ── Polling ───────────────────────────────────────────────────────────────────

# How often (seconds) to reconnect and re-subscribe when connection is lost
POLL_INTERVAL = 30
