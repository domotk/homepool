"""What the entities and the card read in one piece.

A mixin of ``PoolCoordinator``; see coordinator.py.
"""

from __future__ import annotations

from typing import Any

from ..const import (
    CONF_AIR_TEMPERATURE_SENSOR,
    CONF_CHLORINATOR_SWITCH,
    CONF_COVER_ENTITY,
    CONF_EQUIPMENT_ROOM_HUMIDITY_SENSOR,
    CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR,
    CONF_FILTER_PRESSURE_SENSOR,
    CONF_ORP_SENSOR,
    CONF_PH_SENSOR,
    CONF_PUMP_POWER_SENSOR,
    CONF_PUMP_SWITCH,
    CONF_SALINITY_SENSOR,
    CONF_WATER_TEMPERATURE_SENSOR,
)


class CardMixin:
    """What the entities and the card read in one piece."""

    def own_entities(self) -> dict[str, str]:
        """HomePool's own entities for this pool, by key: the card's index."""
        from homeassistant.helpers import entity_registry as er

        prefix = f"{self.entry.entry_id}_"
        return {
            entry.unique_id[len(prefix):]: entry.entity_id
            for entry in er.async_entries_for_config_entry(er.async_get(self.hass), self.entry.entry_id)
            if entry.unique_id.startswith(prefix)
        }

    def card_attributes(self) -> dict[str, Any]:
        """What the companion card needs beyond the entity states."""
        conf = self.conf
        return {
            "pool_entities": self.own_entities(),
            "shape": conf.get("shape"),
            "dimensions": {
                k: conf.get(k)
                for k in (
                    "side", "length", "width", "diameter",
                    "length_1", "width_1", "length_2", "width_2",
                    "depth_min", "depth_max",
                )
                if conf.get(k) is not None
            },
            "layout_variant": conf.get("layout_variant"),
            "layout_orientation": conf.get("layout_orientation"),
            "liner_color": conf.get("liner_color"),
            "volume_m3": self.volume,
            "skimmers": conf.get("skimmers_count"),
            "returns": conf.get("returns_count"),
            "has_autofill_skimmer": conf.get("has_autofill_skimmer"),
            "lights": conf.get("light_entities") or [],
            "entities": {
                key: conf.get(key)
                for key in (
                    CONF_PUMP_SWITCH,
                    CONF_CHLORINATOR_SWITCH,
                    CONF_PH_SENSOR,
                    CONF_WATER_TEMPERATURE_SENSOR,
                    CONF_AIR_TEMPERATURE_SENSOR,
                    CONF_ORP_SENSOR,
                    CONF_SALINITY_SENSOR,
                    CONF_FILTER_PRESSURE_SENSOR,
                    CONF_PUMP_POWER_SENSOR,
                    CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR,
                    CONF_EQUIPMENT_ROOM_HUMIDITY_SENSOR,
                    CONF_COVER_ENTITY,
                )
                if conf.get(key)
            },
        }
