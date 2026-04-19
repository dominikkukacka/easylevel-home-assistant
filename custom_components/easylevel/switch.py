"""EasyLevel switch platform — polling enable/disable."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
    async_add_entities([EasyLevelPollingSwitch(coordinator, entry)])


class EasyLevelPollingSwitch(CoordinatorEntity[EasyLevelCoordinator], SwitchEntity):
    """Switch that enables/disables BLE polling from the dashboard."""

    _attr_has_entity_name = True
    _attr_name = "Polling"
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, coordinator: EasyLevelCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_polling_enabled"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="CaraTech AB",
            model="EasyLevel Sensor",
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.polling_enabled

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.polling_enabled = True
        await self.coordinator.async_save_options()
        self.async_write_ha_state()
        _LOGGER.debug("EasyLevel: polling enabled")

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.polling_enabled = False
        await self.coordinator.async_save_options()
        self.async_write_ha_state()
        _LOGGER.debug("EasyLevel: polling disabled")

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
