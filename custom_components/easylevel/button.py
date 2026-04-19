"""EasyLevel button — manual refresh trigger."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EasyLevelCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EasyLevelCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EasyLevelRefreshButton(coordinator, entry)])


class EasyLevelRefreshButton(CoordinatorEntity[EasyLevelCoordinator], ButtonEntity):
    """Button that triggers an immediate BLE poll regardless of interval."""

    _attr_has_entity_name = True
    _attr_name = "Refresh now"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: EasyLevelCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_refresh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="CaraTech AB",
            model="EasyLevel Sensor",
        )

    async def async_press(self) -> None:
        """Connect immediately and update all sensor entities."""
        _LOGGER.debug("EasyLevel: manual refresh triggered")
        await self.coordinator.async_refresh_now()
