"""EasyLevel sensor platform — pitch, roll, and diagnostic sensors."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import DEGREE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EasyLevelCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class EasyLevelSensorDescription(SensorEntityDescription):
    """Describes an EasyLevel sensor."""


SENSOR_DESCRIPTIONS: tuple[EasyLevelSensorDescription, ...] = (
    EasyLevelSensorDescription(
        key="pitch",
        name="Pitch",
        native_unit_of_measurement=DEGREE,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:angle-acute",
        suggested_display_precision=1,
    ),
    EasyLevelSensorDescription(
        key="roll",
        name="Roll",
        native_unit_of_measurement=DEGREE,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:rotate-3d-variant",
        suggested_display_precision=1,
    ),
    EasyLevelSensorDescription(
        key="pitch_raw",
        name="Pitch (unsmoothed)",
        native_unit_of_measurement=DEGREE,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:angle-acute",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,  # hidden by default
    ),
    EasyLevelSensorDescription(
        key="roll_raw",
        name="Roll (unsmoothed)",
        native_unit_of_measurement=DEGREE,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:rotate-3d-variant",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
    EasyLevelSensorDescription(
        key="gravity_magnitude",
        name="Gravity magnitude",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:earth",
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EasyLevel sensors from a config entry."""
    coordinator: EasyLevelCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        EasyLevelSensorEntity(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class EasyLevelSensorEntity(CoordinatorEntity[EasyLevelCoordinator], SensorEntity):
    """A single EasyLevel sensor entity."""

    entity_description: EasyLevelSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EasyLevelCoordinator,
        entry: ConfigEntry,
        description: EasyLevelSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="CaraTech AB",
            model="EasyLevel Sensor",
        )

    @property
    def native_value(self) -> float | None:
        """Return current sensor value."""
        parser = self.coordinator.parser
        key = self.entity_description.key

        if key == "pitch":
            return parser.pitch
        if key == "roll":
            return parser.roll
        if key == "pitch_raw":
            raw = parser.last_raw
            return raw.pitch if raw else None
        if key == "roll_raw":
            raw = parser.last_raw
            return raw.roll if raw else None
        if key == "gravity_magnitude":
            raw = parser.last_raw
            return raw.gravity_magnitude if raw else None
        return None

    @property
    def available(self) -> bool:
        """Return True if we have received at least one reading."""
        return self.coordinator.parser.pitch is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle data update from coordinator."""
        self.async_write_ha_state()
