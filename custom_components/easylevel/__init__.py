"""EasyLevel Home Assistant integration."""

from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import EasyLevelCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start coordinator *after* platforms have subscribed
    entry.async_on_unload(coordinator.async_start())

    # Re-read options whenever the user changes them (no restart needed)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — coordinator reads options live, nothing to reload."""
    coordinator: EasyLevelCoordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug(
        "EasyLevel: options updated — polling_enabled=%s  interval=%ds",
        coordinator.polling_enabled,
        coordinator.poll_interval,
    )
    # The coordinator properties read from entry.options directly,
    # so changes take effect on the very next poll cycle automatically.


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
