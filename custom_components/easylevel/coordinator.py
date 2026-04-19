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
      then disconnects. HA sensors are updated after the poll completes.

    Polling can be disabled entirely and the interval is configurable via options.
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
        return self._entry.options.get(CONF_POLLING_ENABLED, DEFAULT_POLLING_ENABLED)

    @property
    def poll_interval(self) -> int:
        return int(self._entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))

    # ── Poll scheduling ───────────────────────────────────────────────────────

    @callback
    def _needs_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        seconds_since_last_poll: float | None,
    ) -> bool:
        if not self.polling_enabled:
            return False
        if self.hass.state != CoreState.running:
            return False
        if not bluetooth.async_ble_device_from_address(
            self.hass, service_info.device.address, connectable=True
        ):
            return False
        if seconds_since_last_poll is None:
            return True
        return seconds_since_last_poll >= self.poll_interval

    # ── Active poll — GATT connect + notify ───────────────────────────────────

    async def _async_poll(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        """Connect, subscribe to notifications for 2s, parse, disconnect, then update."""

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
                        _LOGGER.debug("EasyLevel: device info: %s", self.firmware_info)
                    except BleakError as err:
                        _LOGGER.debug("EasyLevel: could not read device info: %s", err)

                # Collect packets via asyncio queue — avoids calling HA APIs
                # from the Bleak callback thread
                packet_queue: asyncio.Queue[bytes] = asyncio.Queue()

                def _handle_notify(_sender, data: bytearray) -> None:
                    # This callback runs in the Bleak thread — only put to queue
                    try:
                        packet_queue.put_nowait(bytes(data))
                    except asyncio.QueueFull:
                        pass

                await client.start_notify(CHAR_ACCEL, _handle_notify)
                _LOGGER.debug("EasyLevel: subscribed, collecting for 2s…")

                # Drain the queue for 2 seconds in the HA event loop
                deadline = asyncio.get_event_loop().time() + 2.0
                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        raw = await asyncio.wait_for(
                            packet_queue.get(), timeout=remaining
                        )
                        self.parser.update(raw)
                    except asyncio.TimeoutError:
                        break

                await client.stop_notify(CHAR_ACCEL)
                self._last_poll_ok = True

                _LOGGER.debug(
                    "EasyLevel: poll done — pitch=%.2f°  roll=%.2f°",
                    self.parser.pitch or 0.0,
                    self.parser.roll or 0.0,
                )

                # Notify HA entities — called from the event loop, safe here
                self.async_set_updated_data(None)

        except BleakError as err:
            self._last_poll_ok = False
            _LOGGER.warning("EasyLevel: BLE connection error: %s", err)
        except asyncio.TimeoutError:
            self._last_poll_ok = False
            _LOGGER.warning("EasyLevel: connection timed out")

    # ── Advertisement / unavailable handlers ──────────────────────────────────

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Passive advertisement received — data comes from active poll above."""

    @callback
    def _async_handle_unavailable(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        """Device went out of range."""
        _LOGGER.debug("EasyLevel: device unavailable (%s)", service_info.address)
