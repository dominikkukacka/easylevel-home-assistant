"""EasyLevel Home Assistant integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import EasyLevelCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EasyLevel from a config entry."""
    address: str = entry.data[CONF_ADDRESS]

    ble_device = bluetooth.async_ble_device_from_address(
        hass, address.upper(), connectable=True
    )
    if not ble_device:
        raise ConfigEntryNotReady(
            f"EasyLevel device {address} not found. "
            "Make sure it is powered on and within Bluetooth range."
        )

    coordinator = EasyLevelCoordinator(
        hass=hass,
        logger=_LOGGER,
        ble_device=ble_device,
        entry=entry,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Set up all platforms first so entities can subscribe before data arrives
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start the advertisement-driven coordinator
    entry.async_on_unload(coordinator.async_start())

    # Schedule an immediate poll so sensors show data right away
    # (doesn't wait for the first BLE advertisement to arrive)
    async def _initial_poll(_now=None) -> None:
        await coordinator.async_poll_now()

    hass.async_create_task(_initial_poll())

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
