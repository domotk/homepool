"""HomePool selects: the operation mode and the season state."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PoolCoordinator
from .entity import PoolEntity
from .pool.season import SeasonState


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolCoordinator = entry.runtime_data
    async_add_entities([OperationModeSelect(coordinator), SeasonStateSelect(coordinator)])


class OperationModeSelect(PoolEntity, SelectEntity):
    """off, timer, smart — and the two solar modes when there is a surplus sensor."""

    _attr_icon = "mdi:pool"

    def __init__(self, coordinator: PoolCoordinator) -> None:
        super().__init__(coordinator, "operation_mode")
        self._attr_options = coordinator.available_modes()

    @property
    def current_option(self) -> str:
        mode = self.coordinator.mode
        return mode if mode in self._attr_options else "off"

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_setting("mode", option)


class SeasonStateSelect(PoolEntity, SelectEntity):
    """Swimming, active or passive wintering, or opening: the owner's to choose.

    The calendar only proposes a change; ``proposal`` says which.
    """

    _attr_icon = "mdi:calendar-sync"
    _attr_options = [s.value for s in SeasonState]

    def __init__(self, coordinator: PoolCoordinator) -> None:
        super().__init__(coordinator, "season_state")

    @property
    def current_option(self) -> str:
        return self.coordinator.season_state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"proposal": self.coordinator.season_proposal_shown}

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_season_state(option)
