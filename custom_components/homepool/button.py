"""HomePool buttons: start and stop a cycle, and log the manual jobs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_PH_SENSOR, ManualAction
from .coordinator import PoolCoordinator
from .entity import PoolEntity


@dataclass(frozen=True, kw_only=True)
class PoolButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[PoolCoordinator], Awaitable[None]]
    exists_fn: Callable[[PoolCoordinator], bool] = lambda c: True


BUTTONS: tuple[PoolButtonDescription, ...] = (
    PoolButtonDescription(
        key="start_cycle",
        icon="mdi:play",
        press_fn=lambda c: c.async_start_cycle(),
    ),
    PoolButtonDescription(
        key="stop_cycle",
        icon="mdi:stop",
        press_fn=lambda c: c.async_stop_cycle(),
    ),
    PoolButtonDescription(
        key="mark_backwash_done",
        icon="mdi:backup-restore",
        exists_fn=lambda c: c.uses_backwash,
        press_fn=lambda c: c.async_record_action(ManualAction.BACKWASH),
    ),
    PoolButtonDescription(
        key="mark_filter_cleaned",
        icon="mdi:air-filter",
        press_fn=lambda c: c.async_record_action(ManualAction.FILTER_CLEANED),
    ),
    PoolButtonDescription(
        key="mark_salt_added",
        icon="mdi:shaker",
        exists_fn=lambda c: c.is_salt,
        press_fn=lambda c: c.async_record_action(ManualAction.SALT_ADDED),
    ),
    PoolButtonDescription(
        key="mark_ph_calibrated",
        icon="mdi:test-tube",
        exists_fn=lambda c: c.has(CONF_PH_SENSOR),
        press_fn=lambda c: c.async_record_action(ManualAction.PH_CALIBRATED),
    ),
    PoolButtonDescription(
        key="recalculate_target",
        icon="mdi:calculator-variant",
        press_fn=lambda c: c.async_recalculate(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolCoordinator = entry.runtime_data
    async_add_entities(
        PoolButton(coordinator, d) for d in BUTTONS if d.exists_fn(coordinator)
    )


class PoolButton(PoolEntity, ButtonEntity):
    entity_description: PoolButtonDescription

    def __init__(self, coordinator: PoolCoordinator, description: PoolButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator)
