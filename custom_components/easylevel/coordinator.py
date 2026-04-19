"""EasyLevel BLE coordinator."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

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

    Inherits from ActiveBluetoothDataUpdateCoordinator which does NOT have
    last_update_success or async_set_updated_data — it uses async_update_listeners().
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
        self.firmware_info: str | None = None

        # Live state — written directly by Switch/Number entities
        self.polling_enabled: bool = entry.options.get(
            CONF_POLLING_ENABLED, DEFAULT_POLLING_ENABLED
        )
        self.poll_interval: int = int(
            entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        )

    async def async_save_options(self) -> None:
        """Persist polling state to config entry options."""
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={
                CONF_POLLING_ENABLED: self.polling_enabled,
                CONF_POLL_INTERVAL: self.poll_interval,
            },
        )

    async def async_poll_now(self) -> None:
        """Force an immediate poll (called on startup)."""
        device = bluetooth.async_ble_device_from_address(
            self.hass, self._ble_device.address, connectable=True
        ) or self._ble_device
        await self._connect_and_read(device)

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

    async def _connect_and_read(self, device) -> None:
        """Connect via GATT, collect 2s of notifications, notify listeners."""
        _LOGGER.debug("EasyLevel: connecting to %s", device.address)
        try:
            client = await establish_connection(
                BleakClient,
                device,
                device.address,
                max_attempts=3,
            )
            try:
                if self.firmware_info is None:
                    try:
                        raw = await client.read_gatt_char(CHAR_DEVICE_INFO)
                        self.firmware_info = raw.hex("-")
                        _LOGGER.debug("EasyLevel: firmware: %s", self.firmware_info)
                    except BleakError as err:
                        _LOGGER.debug("EasyLevel: firmware read error: %s", err)

                queue: asyncio.Queue[bytes] = asyncio.Queue()

                def _on_notify(_sender, data: bytearray) -> None:
                    try:
                        queue.put_nowait(bytes(data))
                    except asyncio.QueueFull:
                        pass

                await client.start_notify(CHAR_ACCEL, _on_notify)
                _LOGGER.debug("EasyLevel: collecting for 2s…")

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

                # Correct method for ActiveBluetoothDataUpdateCoordinator
                self.async_update_listeners()

            finally:
                await client.disconnect()

        except BleakError as err:
            _LOGGER.warning("EasyLevel: BLE error: %s", err)
        except asyncio.TimeoutError:
            _LOGGER.warning("EasyLevel: connection timed out")
        except Exception as err:
            _LOGGER.error("EasyLevel: unexpected error: %s", err)

    @callback
    def _async_handle_bluetooth_event(self, service_info, change) -> None:
        pass

    @callback
    def _async_handle_unavailable(self, service_info) -> None:
        _LOGGER.debug("EasyLevel: device out of range (%s)", service_info.address)
