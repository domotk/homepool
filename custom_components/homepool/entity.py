"""Shared base entity: every entity belongs to the pool device."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PUMP_MODEL, CONF_PUMP_SWITCH, DOMAIN
from .coordinator import PoolCoordinator


# Newer Home Assistant links devices by registry id and deprecates the
# (domain, identifier) form, removed in 2027.8; older versions only know the
# tuple. Use whichever this one understands.
VIA_DEVICE_ID = "via_device_id" in getattr(DeviceInfo, "__annotations__", {})


def _via_device(coordinator: PoolCoordinator) -> dict[str, object]:
    """The link to the device that owns the pump relay, as this HA wants it.

    Linking the pool to the relay's device puts the Shelly (or whatever drives
    the pump) one click away, and makes the relationship visible.
    """
    entity_id = coordinator.conf.get(CONF_PUMP_SWITCH)
    if not entity_id:
        return {}
    entity = er.async_get(coordinator.hass).async_get(entity_id)
    if entity is None or entity.device_id is None:
        return {}
    device = dr.async_get(coordinator.hass).async_get(entity.device_id)
    if device is None:
        return {}
    if VIA_DEVICE_ID:
        return {"via_device_id": device.id}
    if not device.identifiers:
        return {}
    return {"via_device": sorted(device.identifiers)[0]}


class PoolEntity(CoordinatorEntity[PoolCoordinator]):
    """Base for every HomePool entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PoolCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.pool_name,
            manufacturer="HomePool",
            model=coordinator.conf.get(CONF_PUMP_MODEL) or "Pool",
            **_via_device(coordinator),
        )
