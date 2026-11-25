"""HomePool — Swimming pool management integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

type HomePoolConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: HomePoolConfigEntry) -> bool:
    """Set up HomePool from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # TODO: Initialize the HomePoolCoordinator here
    # coordinator = HomePoolCoordinator(hass, entry)
    # await coordinator.async_config_entry_first_refresh()
    # hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("HomePool integration set up for '%s'", entry.title)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HomePoolConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.info("HomePool integration unloaded for '%s'", entry.title)

    return unload_ok
