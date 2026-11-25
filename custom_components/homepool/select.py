"""HomePool select: the operation mode."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PoolCoordinator
from .entity import PoolEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([OperationModeSelect(entry.runtime_data)])


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
