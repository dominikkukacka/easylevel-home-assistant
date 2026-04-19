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

    polling_enabled and poll_interval are live attributes — entities (Switch,
    Number) write to them directly and the next _needs_poll() call picks them
    up.  They are also persisted to entry.options so they survive restarts.
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
        self.parser = EasyLevelParser(smoothing_window=5)
        self._last_poll_ok = False
        self.firmware_info: str | None = None

        # Live state — initialised from persisted options
        self.polling_enabled: bool = entry.options.get(
            CONF_POLLING_ENABLED, DEFAULT_POLLING_ENABLED
        )
        self.poll_interval: int = int(
            entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        )

    # ── Persist current live state back to entry.options ──────────────────────

    async def async_save_options(self) -> None:
        """Write current live state to config entry options (survives restart)."""
        self.hass.config_entries.async_update_entry(
            self._entry,
            options={
                CONF_POLLING_ENABLED: self.polling_enabled,
                CONF_POLL_INTERVAL: self.poll_interval,
            },
        )

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

    # ── Active poll ───────────────────────────────────────────────────────────

    async def _async_poll(
        self, service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        device = bluetooth.async_ble_device_from_address(
            self.hass, service_info.device.address, connectable=True
        ) or service_info.device

        _LOGGER.debug(
            "EasyLevel: connecting to %s (interval=%ds, enabled=%s)",
            device.address, self.poll_interval, self.polling_enabled,
        )

        try:
            async with BleakClient(device) as client:
                if self.firmware_info is None:
                    try:
                        raw_info = await client.read_gatt_char(CHAR_DEVICE_INFO)
                        self.firmware_info = raw_info.hex("-")
                    except BleakError as err:
                        _LOGGER.debug("EasyLevel: device info error: %s", err)

                packet_queue: asyncio.Queue[bytes] = asyncio.Queue()

                def _handle_notify(_sender, data: bytearray) -> None:
                    try:
                        packet_queue.put_nowait(bytes(data))
                    except asyncio.QueueFull:
                        pass

                await client.start_notify(CHAR_ACCEL, _handle_notify)
                deadline = asyncio.get_event_loop().time() + 2.0
                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        raw = await asyncio.wait_for(packet_queue.get(), timeout=remaining)
                        self.parser.update(raw)
                    except asyncio.TimeoutError:
                        break

                await client.stop_notify(CHAR_ACCEL)
                self._last_poll_ok = True
                _LOGGER.debug(
                    "EasyLevel: poll done — pitch=%.2f°  roll=%.2f°",
                    self.parser.pitch or 0.0, self.parser.roll or 0.0,
                )
                self.async_set_updated_data(None)

        except BleakError as err:
            self._last_poll_ok = False
            _LOGGER.warning("EasyLevel: BLE error: %s", err)
        except asyncio.TimeoutError:
            self._last_poll_ok = False
            _LOGGER.warning("EasyLevel: connection timed out")

    @callback
    def _async_handle_bluetooth_event(self, service_info, change) -> None:
        pass

    @callback
    def _async_handle_unavailable(self, service_info) -> None:
        _LOGGER.debug("EasyLevel: device unavailable (%s)", service_info.address)
