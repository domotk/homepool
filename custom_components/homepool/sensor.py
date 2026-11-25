"""HomePool sensor platform.

TODO: Implement entity definitions for sensor.
See design document section 9 for the complete list of entities.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HomePool sensor entities."""
    # TODO: Create entities based on config and connected sensors
    pass
