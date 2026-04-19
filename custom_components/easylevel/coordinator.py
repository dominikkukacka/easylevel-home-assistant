"""EasyLevel BLE coordinator — manages active GATT connection and data updates."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothDataUpdateCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, HomeAssistant, callback

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


class EasyLevelCoordinator(ActiveBluetoothDataUpdateCoordinator[None]):
    """
    Coordinator for the EasyLevel BLE sensor.

    Strategy:
    - Passive: listens for BLE advertisements to detect when device is nearby.
    - Active poll: when an advertisement arrives (and poll is needed), connects
      via GATT, subscribes to NOTIFY on CHAR_ACCEL, collects ~2s of readings,
      then disconnects.  HA sensors are updated on each notify callback.

    Polling can be disabled entirely (sensor becomes read-only / shows last known
    value) and the interval is configurable via the integration's options flow.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        ble_device: BLEDevice,
        entry: ConfigEntry,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass=hass,
            logger=logger,
            address=ble_device.address,
            needs_poll_method=self._needs_poll,
            poll_method=self._async_poll,
            mode=bluetooth.BluetoothScanningMode.ACTIVE,
            connectable=True,
        )
        self._entry = entry
        self.parser = EasyLevelParser(smoothing_window=5)
        self._last_poll_ok = False
        self.firmware_info: str | None = None

    # ── Options helpers ───────────────────────────────────────────────────────

    @property
    def polling_enabled(self) -> bool:
        """Return whether active polling is enabled (from options)."""
        return self._entry.options.get(CONF_POLLING_ENABLED, DEFAULT_POLLING_ENABLED)

    @property
    def poll_interval(self) -> int:
        """Return poll interval in seconds (from options)."""
        return int(self._entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))

    # ── Poll scheduling ───────────────────────────────────────────────────────

    @callback
    def _needs_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        seconds_since_last_poll: float | None,
    ) -> bool:
        """Return True when we want to make an active connection."""
        if not self.polling_enabled:
            _LOGGER.debug("EasyLevel: polling disabled, skipping")
            return False
        if self.hass.state != CoreState.running:
            return False
        if not bluetooth.async_ble_device_from_address(
            self.hass, service_info.device.address, connectable=True
        ):
            return False
        # Poll immediately on first contact, then every poll_interval seconds
        if seconds_since_last_poll is None:
            return True
        return seconds_since_last_poll >= self.poll_interval

    # ── Active poll — GATT connect + notify ───────────────────────────────────

    async def _async_poll(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        """Connect to device, subscribe to notifications, collect data, disconnect."""

        # Prefer a connectable device handle from the BT stack
        device = bluetooth.async_ble_device_from_address(
            self.hass, service_info.device.address, connectable=True
        ) or service_info.device

        _LOGGER.debug(
            "EasyLevel: connecting to %s (interval=%ds)",
            device.address,
            self.poll_interval,
        )

        try:
            async with BleakClient(device) as client:
                # One-time device info read
                if self.firmware_info is None:
                    try:
                        raw_info = await client.read_gatt_char(CHAR_DEVICE_INFO)
                        self.firmware_info = raw_info.hex("-")
                        _LOGGER.debug(
                            "EasyLevel: device info bytes: %s", self.firmware_info
                        )
                    except BleakError as err:
                        _LOGGER.debug("EasyLevel: could not read device info: %s", err)

                packets_received = 0

                def _handle_notify(sender, data: bytearray) -> None:
                    nonlocal packets_received
                    packets_received += 1
                    parsed = self.parser.update(bytes(data))
                    if parsed is not None:
                        _LOGGER.debug(
                            "EasyLevel: pitch=%.2f°  roll=%.2f°  |g|=%.0f",
                            self.parser.pitch,
                            self.parser.roll,
                            parsed.gravity_magnitude,
                        )
                        self.async_set_updated_data(None)

                await client.start_notify(CHAR_ACCEL, _handle_notify)
                _LOGGER.debug("EasyLevel: subscribed, collecting data...")

                # Collect for 2 seconds to fill the smoothing window
                await asyncio.sleep(2.0)

                await client.stop_notify(CHAR_ACCEL)
                self._last_poll_ok = True
                _LOGGER.debug(
                    "EasyLevel: poll done — %d packets, pitch=%.2f°, roll=%.2f°",
                    packets_received,
                    self.parser.pitch or 0,
                    self.parser.roll or 0,
                )

        except BleakError as err:
            self._last_poll_ok = False
            _LOGGER.warning("EasyLevel: BLE connection error: %s", err)
        except asyncio.TimeoutError:
            self._last_poll_ok = False
            _LOGGER.warning("EasyLevel: connection timed out")

    # ── Advertisement handler ─────────────────────────────────────────────────

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle incoming BLE advertisement (data comes from active poll)."""

    @callback
    def _async_handle_unavailable(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        """Device went out of range."""
        _LOGGER.debug("EasyLevel: device unavailable (%s)", service_info.address)
