"""EasyLevel sensor platform."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorEntity, SensorEntityDescription, SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import DEGREE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EasyLevelCoordinator


@dataclass(frozen=True, kw_only=True)
class EasyLevelSensorDescription(SensorEntityDescription):
    value_fn: Callable[[EasyLevelCoordinator], float | None]


SENSORS: tuple[EasyLevelSensorDescription, ...] = (
    EasyLevelSensorDescription(
        key="pitch", name="Pitch",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:angle-acute",
        suggested_display_precision=1,
        value_fn=lambda c: c.parser.pitch,
    ),
    EasyLevelSensorDescription(
        key="roll", name="Roll",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:rotate-3d-variant",
        suggested_display_precision=1,
        value_fn=lambda c: c.parser.roll,
    ),
    EasyLevelSensorDescription(
        key="pitch_raw", name="Pitch (unsmoothed)",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:angle-acute",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.parser.last_raw.pitch if c.parser.last_raw else None,
    ),
    EasyLevelSensorDescription(
        key="roll_raw", name="Roll (unsmoothed)",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:rotate-3d-variant",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.parser.last_raw.roll if c.parser.last_raw else None,
    ),
    EasyLevelSensorDescription(
        key="gravity_magnitude", name="Gravity magnitude",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:earth",
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.parser.last_raw.gravity_magnitude if c.parser.last_raw else None,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: EasyLevelCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EasyLevelSensor(coordinator, entry, d) for d in SENSORS])


class EasyLevelSensor(CoordinatorEntity[EasyLevelCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: EasyLevelSensorDescription

    def __init__(self, coordinator: EasyLevelCoordinator, entry: ConfigEntry, description: EasyLevelSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title, manufacturer="CaraTech AB", model="EasyLevel Sensor",
        )

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator)
