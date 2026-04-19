"""EasyLevel BLE coordinator — timed DataUpdateCoordinator with GATT polling."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

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
    Timed DataUpdateCoordinator for the EasyLevel BLE sensor.

    Connects every poll_interval seconds, subscribes to GATT notifications
    for 2 seconds, then disconnects. Entities update automatically via the
    standard CoordinatorEntity mechanism.
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

        # Live state — written directly by Switch/Number/Button entities
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

    # ── Persist options ───────────────────────────────────────────────────────

    async def async_save_options(self) -> None:
        """Persist current live state to config entry options."""
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={
                CONF_POLLING_ENABLED: self.polling_enabled,
                CONF_POLL_INTERVAL: self.poll_interval,
            },
        )
        self.update_interval = timedelta(seconds=self.poll_interval)

    # ── Core poll method ──────────────────────────────────────────────────────

    async def _async_update_data(self) -> None:
        """Called by coordinator on every update_interval tick."""
        if not self.polling_enabled:
            _LOGGER.debug("EasyLevel: polling disabled, skipping")
            return None

        device = bluetooth.async_ble_device_from_address(
            self.hass, self._ble_device.address, connectable=True
        ) or self._ble_device

        _LOGGER.debug(
            "EasyLevel: polling %s (interval=%ds)", device.address, self.poll_interval
        )

        await self._connect_and_read(device)
        return None

    # ── Shared GATT logic (also called by the refresh button) ─────────────────

    async def async_refresh_now(self) -> None:
        """Trigger an immediate poll outside the normal schedule."""
        device = bluetooth.async_ble_device_from_address(
            self.hass, self._ble_device.address, connectable=True
        ) or self._ble_device
        try:
            await self._connect_and_read(device)
        except UpdateFailed as err:
            _LOGGER.warning("EasyLevel: manual refresh failed: %s", err)
        # Notify entities regardless so UI refreshes
        self.async_set_updated_data(None)

    async def _connect_and_read(self, device) -> None:
        """Connect via GATT, collect 2s of notifications."""
        try:
            client = await establish_connection(
                BleakClient,
                device,
                device.address,
                max_attempts=2,
            )
        except Exception as err:
            raise UpdateFailed(f"Could not connect: {err}") from err

        try:
            # One-time firmware read
            if self.firmware_info is None:
                try:
                    raw = await client.read_gatt_char(CHAR_DEVICE_INFO)
                    self.firmware_info = raw.hex("-")
                    _LOGGER.debug("EasyLevel: firmware: %s", self.firmware_info)
                except BleakError as err:
                    _LOGGER.debug("EasyLevel: firmware read skipped: %s", err)

            # Collect notifications via queue (Bleak callback is not async-safe)
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

        except BleakError as err:
            raise UpdateFailed(f"BLE error: {err}") from err
        except asyncio.TimeoutError as err:
            raise UpdateFailed("Read timed out") from err
        finally:
            await client.disconnect()
