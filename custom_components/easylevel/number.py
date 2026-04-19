"""EasyLevel number — poll interval."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAX_POLL_INTERVAL, MIN_POLL_INTERVAL
from .coordinator import EasyLevelCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EasyLevelCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EasyLevelPollIntervalNumber(coordinator, entry)])


class EasyLevelPollIntervalNumber(CoordinatorEntity[EasyLevelCoordinator], NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Poll interval"
    _attr_icon = "mdi:timer-outline"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_native_min_value = MIN_POLL_INTERVAL
    _attr_native_max_value = MAX_POLL_INTERVAL
    _attr_native_step = 5
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: EasyLevelCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_poll_interval"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title, manufacturer="CaraTech AB", model="EasyLevel Sensor",
        )

    @property
    def native_value(self) -> float:
        return float(self.coordinator.poll_interval)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.poll_interval = int(value)
        await self.coordinator.async_save_options()
        self.async_write_ha_state()
