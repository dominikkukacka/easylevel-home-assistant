"""EasyLevel BLE coordinator — timed DataUpdateCoordinator with GATT polling."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CHAR_ACCEL,
    CHAR_DEVICE_INFO,
    CONF_POLL_INTERVAL,
    CONF_POLLING_ENABLED,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POLLING_ENABLED,
)
from .sensor_data import EasyLevelParser

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)


class EasyLevelCoordinator(DataUpdateCoordinator[None]):
    """
    Standard DataUpdateCoordinator that polls the EasyLevel sensor via BLE GATT.

    Using DataUpdateCoordinator (not ActiveBluetoothDataUpdateCoordinator) because:
    - The device sends no useful data in BLE advertisements
    - We need predictable timed polling, not advertisement-driven polling
    - DataUpdateCoordinator gives us last_update_success, async_add_listener,
      and CoordinatorEntity compatibility for free

    The update_interval is updated live when the user changes poll_interval.
    When polling_enabled is False the _async_update_data returns immediately
    without connecting, preserving the last known values.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        ble_device: BLEDevice,
        entry: ConfigEntry,
    ) -> None:
        self._entry = entry
        self._ble_device = ble_device
        self.parser = EasyLevelParser(smoothing_window=5)
        self.firmware_info: str | None = None

        # Live state — written by Switch/Number entities
        self.polling_enabled: bool = entry.options.get(
            CONF_POLLING_ENABLED, DEFAULT_POLLING_ENABLED
        )
        self.poll_interval: int = int(
            entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        )

        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name="EasyLevel",
            update_interval=timedelta(seconds=self.poll_interval),
        )

    # ── Options persistence ───────────────────────────────────────────────────

    async def async_save_options(self) -> None:
        """Persist current live state to config entry options."""
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={
                CONF_POLLING_ENABLED: self.polling_enabled,
                CONF_POLL_INTERVAL: self.poll_interval,
            },
        )
        # Apply new interval immediately
        self.update_interval = timedelta(seconds=self.poll_interval)

    # ── DataUpdateCoordinator hook ────────────────────────────────────────────

    async def _async_update_data(self) -> None:
        """Called by the coordinator on every update_interval tick."""
        if not self.polling_enabled:
            _LOGGER.debug("EasyLevel: polling disabled, skipping")
            return None   # keep last values, don't raise

        device = bluetooth.async_ble_device_from_address(
            self.hass, self._ble_device.address, connectable=True
        ) or self._ble_device

        _LOGGER.debug("EasyLevel: polling %s (interval=%ds)", device.address, self.poll_interval)

        try:
            async with BleakClient(device, timeout=15.0) as client:
                # One-time firmware read
                if self.firmware_info is None:
                    try:
                        raw = await client.read_gatt_char(CHAR_DEVICE_INFO)
                        self.firmware_info = raw.hex("-")
                        _LOGGER.debug("EasyLevel: firmware: %s", self.firmware_info)
                    except BleakError as err:
                        _LOGGER.debug("EasyLevel: firmware read skipped: %s", err)

                # Collect GATT notifications via queue for 2 seconds
                queue: asyncio.Queue[bytes] = asyncio.Queue()

                def _on_notify(_sender, data: bytearray) -> None:
                    try:
                        queue.put_nowait(bytes(data))
                    except asyncio.QueueFull:
                        pass

                await client.start_notify(CHAR_ACCEL, _on_notify)
                _LOGGER.debug("EasyLevel: collecting notifications for 2s…")

                deadline = asyncio.get_event_loop().time() + 2.0
                packets = 0
                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        raw = await asyncio.wait_for(queue.get(), timeout=remaining)
                        self.parser.update(raw)
                        packets += 1
                    except asyncio.TimeoutError:
                        break

                await client.stop_notify(CHAR_ACCEL)
                _LOGGER.debug(
                    "EasyLevel: done — %d packets, pitch=%.2f°, roll=%.2f°",
                    packets,
                    self.parser.pitch or 0.0,
                    self.parser.roll or 0.0,
                )
                return None

        except BleakError as err:
            raise UpdateFailed(f"BLE connection error: {err}") from err
        except asyncio.TimeoutError as err:
            raise UpdateFailed("Connection timed out after 15s") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err
