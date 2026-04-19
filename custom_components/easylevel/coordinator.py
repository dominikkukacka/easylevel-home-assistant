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

    The ActiveBluetoothDataUpdateCoordinator drives polling from incoming BLE
    advertisements.  We also schedule an immediate forced poll on startup so
    entities get data right away instead of waiting for the first advertisement.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        ble_device: BLEDevice,
        entry: ConfigEntry,
    ) -> None:
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
        self._ble_device = ble_device
        self.parser = EasyLevelParser(smoothing_window=5)
        self._last_poll_ok = False
        self.firmware_info: str | None = None

        # Live state — written by Switch/Number entities, persisted via async_save_options
        self.polling_enabled: bool = entry.options.get(
            CONF_POLLING_ENABLED, DEFAULT_POLLING_ENABLED
        )
        self.poll_interval: int = int(
            entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        )

    # ── Persist current live state to entry.options ───────────────────────────

    async def async_save_options(self) -> None:
        """Persist polling state so it survives HA restart."""
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={
                CONF_POLLING_ENABLED: self.polling_enabled,
                CONF_POLL_INTERVAL: self.poll_interval,
            },
        )

    # ── Immediate startup poll (doesn't wait for advertisement) ──────────────

    async def async_poll_now(self) -> None:
        """Force an immediate GATT poll using the device address we already have."""
        _LOGGER.debug("EasyLevel: startup poll — connecting to %s", self._ble_device.address)

        # Refresh the device handle from the BT stack (may have updated since init)
        device = bluetooth.async_ble_device_from_address(
            self.hass, self._ble_device.address, connectable=True
        ) or self._ble_device

        await self._connect_and_read(device)

    # ── Poll scheduling (advertisement-driven) ────────────────────────────────

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

    async def _async_poll(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        device = bluetooth.async_ble_device_from_address(
            self.hass, service_info.device.address, connectable=True
        ) or service_info.device
        await self._connect_and_read(device)

    # ── Shared GATT connect + notify logic ───────────────────────────────────

    async def _connect_and_read(self, device) -> None:
        """Connect via GATT, collect 2s of notifications, update entities."""
        _LOGGER.debug("EasyLevel: connecting to %s", device.address)
        try:
            async with BleakClient(device, timeout=15.0) as client:
                # One-time firmware read
                if self.firmware_info is None:
                    try:
                        raw = await client.read_gatt_char(CHAR_DEVICE_INFO)
                        self.firmware_info = raw.hex("-")
                        _LOGGER.debug("EasyLevel: firmware info: %s", self.firmware_info)
                    except BleakError as err:
                        _LOGGER.debug("EasyLevel: device info unavailable: %s", err)

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
                self._last_poll_ok = True

                _LOGGER.debug(
                    "EasyLevel: poll done — %d packets, pitch=%.2f°, roll=%.2f°",
                    packets,
                    self.parser.pitch or 0.0,
                    self.parser.roll or 0.0,
                )

                # Notify all subscribed entities — MUST be called from event loop
                self.async_set_updated_data(None)

        except BleakError as err:
            self._last_poll_ok = False
            _LOGGER.warning("EasyLevel: BLE connection failed: %s", err)
        except asyncio.TimeoutError:
            self._last_poll_ok = False
            _LOGGER.warning("EasyLevel: connection timed out after 15s")
        except Exception as err:
            self._last_poll_ok = False
            _LOGGER.error("EasyLevel: unexpected error during poll: %s", err)

    # ── Advertisement / unavailable callbacks ─────────────────────────────────

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Passive advertisement — data arrives via active poll above."""

    @callback
    def _async_handle_unavailable(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        _LOGGER.debug("EasyLevel: device out of range (%s)", service_info.address)
