"""EasyLevel sensor platform — pitch, roll, diagnostic sensors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import DEGREE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import EasyLevelCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class EasyLevelSensorDescription(SensorEntityDescription):
    value_fn: Callable[[EasyLevelCoordinator], float | None]


SENSOR_DESCRIPTIONS: tuple[EasyLevelSensorDescription, ...] = (
    EasyLevelSensorDescription(
        key="pitch",
        name="Pitch",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:angle-acute",
        suggested_display_precision=1,
        value_fn=lambda c: c.parser.pitch,
    ),
    EasyLevelSensorDescription(
        key="roll",
        name="Roll",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:rotate-3d-variant",
        suggested_display_precision=1,
        value_fn=lambda c: c.parser.roll,
    ),
    EasyLevelSensorDescription(
        key="pitch_raw",
        name="Pitch (unsmoothed)",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:angle-acute",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.parser.last_raw.pitch if c.parser.last_raw else None,
    ),
    EasyLevelSensorDescription(
        key="roll_raw",
        name="Roll (unsmoothed)",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:rotate-3d-variant",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.parser.last_raw.roll if c.parser.last_raw else None,
    ),
    EasyLevelSensorDescription(
        key="gravity_magnitude",
        name="Gravity magnitude",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:earth",
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.parser.last_raw.gravity_magnitude if c.parser.last_raw else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EasyLevelCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        EasyLevelSensorEntity(coordinator, entry, desc)
        for desc in SENSOR_DESCRIPTIONS
    ])


class EasyLevelSensorEntity(RestoreEntity, SensorEntity):
    """
    Sensor entity that subscribes directly to coordinator.async_update_listeners().

    Does NOT inherit CoordinatorEntity because ActiveBluetoothDataUpdateCoordinator
    does not have last_update_success (which CoordinatorEntity.available requires).
    """

    entity_description: EasyLevelSensorDescription
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: EasyLevelCoordinator,
        entry: ConfigEntry,
        description: EasyLevelSensorDescription,
    ) -> None:
        self._coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="CaraTech AB",
            model="EasyLevel Sensor",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates when added to HA."""
        await super().async_added_to_hass()
        # Subscribe to coordinator listener list
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        """Called by coordinator.async_update_listeners() after each poll."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self._coordinator)

    @property
    def available(self) -> bool:
        """Available once we have received at least one reading."""
        return self._coordinator.parser.pitch is not None
