"""HomePool binary sensors: is the day done, and is anything wrong."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CHLORINATOR_SWITCH,
    CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR,
    CONF_FLOOD_SENSOR,
    CONF_HAS_PH_DOSING,
    CONF_PH_DOSING_ENTITY,
    CONF_PH_SENSOR,
    CONF_PUMP_POWER_SENSOR,
    CONF_WATER_TEMPERATURE_SENSOR,
)
from .coordinator import PoolCoordinator
from .entity import PoolEntity


@dataclass(frozen=True, kw_only=True)
class PoolBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[PoolCoordinator], bool | None]
    exists_fn: Callable[[PoolCoordinator], bool] = lambda c: True
    attrs_fn: Callable[[PoolCoordinator], dict[str, Any]] | None = None


BINARY_SENSORS: tuple[PoolBinaryDescription, ...] = (
    PoolBinaryDescription(
        key="daily_target_reached",
        value_fn=lambda c: c.target_reached,
    ),
    PoolBinaryDescription(
        key="pump_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda c: c.pump_is_on if c.pump_available else None,
    ),
    PoolBinaryDescription(
        key="chlorine_target_reached",
        exists_fn=lambda c: c.is_salt and c.has(CONF_CHLORINATOR_SWITCH),
        value_fn=lambda c: c.chlorine_target_reached,
    ),
    PoolBinaryDescription(
        key="backwash_needed",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda c: c.backwash_needed,
        attrs_fn=lambda c: {"pressure_high": c.pressure_high},
    ),
    PoolBinaryDescription(
        key="ph_out_of_range",
        device_class=BinarySensorDeviceClass.PROBLEM,
        exists_fn=lambda c: c.has(CONF_PH_SENSOR),
        value_fn=lambda c: c.ph_out_of_range,
    ),
    PoolBinaryDescription(
        key="ph_correction_active",
        exists_fn=lambda c: c.has(CONF_PH_SENSOR)
        and (c.has(CONF_HAS_PH_DOSING) or c.has(CONF_PH_DOSING_ENTITY)),
        value_fn=lambda c: c.ph_correction_active,
        attrs_fn=lambda c: {
            "minutes_today": c.ph_correction_minutes,
            "window_until": c.ph_window_until.isoformat() if c.ph_window_until else None,
        },
    ),
    PoolBinaryDescription(
        key="critical_water_temperature",
        device_class=BinarySensorDeviceClass.PROBLEM,
        exists_fn=lambda c: c.has(CONF_WATER_TEMPERATURE_SENSOR),
        value_fn=lambda c: c.critical_water_temperature,
    ),
    PoolBinaryDescription(
        key="pump_anomaly",
        device_class=BinarySensorDeviceClass.PROBLEM,
        exists_fn=lambda c: c.has(CONF_PUMP_POWER_SENSOR),
        value_fn=lambda c: c.pump_anomaly,
    ),
    PoolBinaryDescription(
        key="equipment_room_flood",
        device_class=BinarySensorDeviceClass.MOISTURE,
        exists_fn=lambda c: c.has(CONF_FLOOD_SENSOR),
        value_fn=lambda c: c.flood,
    ),
    PoolBinaryDescription(
        key="equipment_room_overheat",
        device_class=BinarySensorDeviceClass.HEAT,
        exists_fn=lambda c: c.has(CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR),
        value_fn=lambda c: c.equipment_room_overheat,
    ),
    PoolBinaryDescription(
        key="manual_action_pending",
        value_fn=lambda c: c.manual_action_pending,
    ),
    PoolBinaryDescription(
        key="safety_shutoff_active",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=lambda c: c.safety_active,
        attrs_fn=lambda c: {"conditions": c.safety_reasons},
    ),
    PoolBinaryDescription(
        key="freeze_protection_active",
        device_class=BinarySensorDeviceClass.COLD,
        value_fn=lambda c: c.freeze_active,
    ),
    PoolBinaryDescription(
        key="swimming_not_advised",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=lambda c: c.swimming_not_advised is not None,
        attrs_fn=lambda c: {"reason": c.swimming_not_advised},
    ),
    PoolBinaryDescription(
        key="chlorinator_in_season",
        exists_fn=lambda c: c.is_salt,
        value_fn=lambda c: c.in_season,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolCoordinator = entry.runtime_data
    async_add_entities(
        PoolBinarySensor(coordinator, d) for d in BINARY_SENSORS if d.exists_fn(coordinator)
    )


class PoolBinarySensor(PoolEntity, BinarySensorEntity):
    entity_description: PoolBinaryDescription

    def __init__(self, coordinator: PoolCoordinator, description: PoolBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator)
