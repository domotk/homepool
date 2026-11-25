"""HomePool: run a pool's filtration and salt chlorinator from entities you already have."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_extract_entity_ids

from .const import (
    ATTR_ACTION_TYPE,
    ATTR_DURATION,
    ATTR_NOTES,
    ATTR_VALUE,
    CONFIG_VERSION,
    DOMAIN,
    PLATFORMS,
    SERVICE_FORCE_PH_WINDOW,
    SERVICE_RECALCULATE,
    SERVICE_RECORD_FREE_CHLORINE,
    SERVICE_RECORD_MANUAL_ACTION,
    SERVICE_RECORD_SALT_LEVEL,
    SERVICE_RESET_DAILY,
    SERVICE_START_CYCLE,
    SERVICE_STOP_CYCLE,
    ManualAction,
)
from .coordinator import PoolCoordinator

_LOGGER = logging.getLogger(__name__)

type HomePoolConfigEntry = ConfigEntry[PoolCoordinator]

# Entity service schemas accept entity_id, device_id, area_id and label_id, so
# the UI offers its usual target picker and "every pool" is expressible.
DURATION_SCHEMA = cv.make_entity_service_schema(
    {vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(float), vol.Range(min=1, max=1440))}
)
EMPTY_SCHEMA = cv.make_entity_service_schema({})
ACTION_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_ACTION_TYPE): vol.In([a.value for a in ManualAction]),
        vol.Optional(ATTR_VALUE): vol.Coerce(float),
        vol.Optional(ATTR_NOTES): cv.string,
    }
)
SALT_SCHEMA = cv.make_entity_service_schema(
    {vol.Required(ATTR_VALUE): vol.All(vol.Coerce(float), vol.Range(min=0, max=15))}
)
CHLORINE_SCHEMA = cv.make_entity_service_schema(
    {vol.Required(ATTR_VALUE): vol.All(vol.Coerce(float), vol.Range(min=0, max=20))}
)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Refuse entries from a newer version rather than misreading them."""
    return entry.version <= CONFIG_VERSION


async def async_setup_entry(hass: HomeAssistant, entry: HomePoolConfigEntry) -> bool:
    """Set up one pool."""
    coordinator = PoolCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_start()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HomePoolConfigEntry) -> bool:
    """Unload a pool, saving its counters on the way out."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    remaining = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED
    ]
    if not remaining:
        for service in (
            SERVICE_START_CYCLE,
            SERVICE_STOP_CYCLE,
            SERVICE_RECORD_MANUAL_ACTION,
            SERVICE_RECORD_SALT_LEVEL,
            SERVICE_RECORD_FREE_CHLORINE,
            SERVICE_RECALCULATE,
            SERVICE_FORCE_PH_WINDOW,
            SERVICE_RESET_DAILY,
        ):
            hass.services.async_remove(DOMAIN, service)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the stored counters and log with the pool."""
    from homeassistant.helpers.storage import Store

    from .const import STORAGE_VERSION

    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the configuration is edited."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register once, however many pools there are."""
    if hass.services.has_service(DOMAIN, SERVICE_START_CYCLE):
        return

    async def _pools(call: ServiceCall) -> list[PoolCoordinator]:
        """Every pool the call points at, each once, however it was targeted."""
        registry = er.async_get(hass)
        found: dict[str, PoolCoordinator] = {}
        for entity_id in await async_extract_entity_ids(hass, call):
            entity = registry.async_get(entity_id)
            if entity is None or entity.config_entry_id is None:
                continue
            entry = hass.config_entries.async_get_entry(entity.config_entry_id)
            if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
                continue
            found.setdefault(entry.entry_id, entry.runtime_data)
        if not found:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_pool_targeted"
            )
        return list(found.values())

    async def _start_cycle(call: ServiceCall) -> None:
        for pool in await _pools(call):
            await pool.async_start_cycle(call.data.get(ATTR_DURATION))

    async def _stop_cycle(call: ServiceCall) -> None:
        for pool in await _pools(call):
            await pool.async_stop_cycle()

    async def _record_action(call: ServiceCall) -> None:
        for pool in await _pools(call):
            await pool.async_record_action(
                call.data[ATTR_ACTION_TYPE], call.data.get(ATTR_VALUE), call.data.get(ATTR_NOTES)
            )

    async def _record_salt(call: ServiceCall) -> None:
        for pool in await _pools(call):
            await pool.async_record_reading("salt", call.data[ATTR_VALUE])

    async def _record_chlorine(call: ServiceCall) -> None:
        for pool in await _pools(call):
            await pool.async_record_reading("free_chlorine", call.data[ATTR_VALUE])

    async def _recalculate(call: ServiceCall) -> None:
        for pool in await _pools(call):
            await pool.async_recalculate()

    async def _ph_window(call: ServiceCall) -> None:
        for pool in await _pools(call):
            await pool.async_force_ph_window(call.data.get(ATTR_DURATION))

    async def _reset(call: ServiceCall) -> None:
        for pool in await _pools(call):
            await pool.async_reset_daily()

    handlers: dict[str, tuple[Any, vol.Schema]] = {
        SERVICE_START_CYCLE: (_start_cycle, DURATION_SCHEMA),
        SERVICE_STOP_CYCLE: (_stop_cycle, EMPTY_SCHEMA),
        SERVICE_RECORD_MANUAL_ACTION: (_record_action, ACTION_SCHEMA),
        SERVICE_RECORD_SALT_LEVEL: (_record_salt, SALT_SCHEMA),
        SERVICE_RECORD_FREE_CHLORINE: (_record_chlorine, CHLORINE_SCHEMA),
        SERVICE_RECALCULATE: (_recalculate, EMPTY_SCHEMA),
        SERVICE_FORCE_PH_WINDOW: (_ph_window, DURATION_SCHEMA),
        SERVICE_RESET_DAILY: (_reset, EMPTY_SCHEMA),
    }
    for name, (handler, schema) in handlers.items():
        hass.services.async_register(DOMAIN, name, handler, schema=schema)
