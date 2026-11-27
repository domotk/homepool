"""HomePool switches: the pump through HomePool, the maintenance lock, the cell."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PoolCoordinator
from .entity import PoolEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolCoordinator = entry.runtime_data
    entities: list[SwitchEntity] = [PumpSwitch(coordinator), MaintenanceLockSwitch(coordinator)]
    if coordinator.is_salt:
        entities.append(ChlorinatorEnabledSwitch(coordinator))
    async_add_entities(entities)


class PumpSwitch(PoolEntity, SwitchEntity):
    """The pump, switched through HomePool.

    Turning it on starts a manual cycle for what is left of today's target;
    turning it off stops the pump and holds it off for the override time. Both
    still give way to the maintenance lock and the safety shutoff, which is
    the difference from switching the relay directly.
    """

    def __init__(self, coordinator: PoolCoordinator) -> None:
        super().__init__(coordinator, "pump")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.pump_is_on if self.coordinator.pump_available else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_pump(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_pump(False)


class MaintenanceLockSwitch(PoolEntity, SwitchEntity):
    """While on, the pump stays off whatever the mode says."""

    _attr_icon = "mdi:lock"

    def __init__(self, coordinator: PoolCoordinator) -> None:
        super().__init__(coordinator, "maintenance_lock")

    @property
    def is_on(self) -> bool:
        return self.coordinator.maintenance_lock

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_setting("maintenance_lock", True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_setting("maintenance_lock", False)


class ChlorinatorEnabledSwitch(PoolEntity, SwitchEntity):
    """Master switch for the salt chlorinator. Follows the season state, and can
    still be changed by hand: the last change wins."""

    _attr_icon = "mdi:shaker-outline"

    def __init__(self, coordinator: PoolCoordinator) -> None:
        super().__init__(coordinator, "salt_chlorinator_enabled")

    @property
    def is_on(self) -> bool:
        return self.coordinator.chlorinator_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_setting("chlorinator_enabled", True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_setting("chlorinator_enabled", False)
