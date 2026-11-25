"""HomePool numbers: the calibration knob and the setpoints."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_PH_SENSOR, CONF_SOLAR_EXCESS_SENSOR
from .coordinator import PoolCoordinator
from .entity import PoolEntity


@dataclass(frozen=True, kw_only=True)
class PoolNumberDescription(NumberEntityDescription):
    setting: str
    value_fn: Callable[[PoolCoordinator], float]
    exists_fn: Callable[[PoolCoordinator], bool] = lambda c: True


NUMBERS: tuple[PoolNumberDescription, ...] = (
    PoolNumberDescription(
        key="user_multiplier",
        setting="user_multiplier",
        native_min_value=0.5,
        native_max_value=2.0,
        native_step=0.05,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda c: c.user_multiplier,
    ),
    PoolNumberDescription(
        key="ph_target",
        setting="ph_target",
        native_min_value=6.8,
        native_max_value=8.0,
        native_step=0.1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda c: c.has(CONF_PH_SENSOR),
        value_fn=lambda c: c.ph_target,
    ),
    PoolNumberDescription(
        key="chlorinator_production",
        setting="chlorinator_production",
        native_min_value=0,
        native_max_value=100,
        native_step=5,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda c: c.is_salt and not c.self_regulating,
        value_fn=lambda c: c.chlorinator_production,
    ),
    PoolNumberDescription(
        key="solar_excess_threshold",
        setting="solar_threshold",
        native_min_value=0,
        native_max_value=5000,
        native_step=50,
        native_unit_of_measurement=UnitOfPower.WATT,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda c: c.has(CONF_SOLAR_EXCESS_SENSOR),
        value_fn=lambda c: c.solar_threshold,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolCoordinator = entry.runtime_data
    async_add_entities(
        PoolNumber(coordinator, d) for d in NUMBERS if d.exists_fn(coordinator)
    )


class PoolNumber(PoolEntity, NumberEntity):
    """A setpoint kept in HomePool's own store, not in the config entry.

    Moving a slider must not reload the integration, and the store already
    survives restarts.
    """

    entity_description: PoolNumberDescription

    def __init__(self, coordinator: PoolCoordinator, description: PoolNumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        return self.entity_description.value_fn(self.coordinator)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_setting(self.entity_description.setting, value)
