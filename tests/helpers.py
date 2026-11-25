"""Shared setup for the integration tests."""

from __future__ import annotations

from typing import Any

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.homepool.const import DOMAIN

PUMP = "input_boolean.pump"
CHLORINATOR = "input_boolean.chlorinator"
HANDS_OFF = "input_boolean.hands_off"

BASE: dict[str, Any] = {
    "name": "Pool",
    "latitude": 39.6,
    "longitude": -0.5,
    "shape": "rectangular",
    "length": 6.5,
    "width": 2.5,
    "depth_min": 1.2,
    "depth_max": 2.2,
    "layout_variant": "plain",
    "volume": 30.0,
    "construction_type": "built_in",
    "has_cover": "none",
    "is_covered_by_roof": False,
    "pump_nominal_flow_rate": 12.8,
    "pump_nominal_power": 880,
    "filter_type": "sand",
    "chlorination_type": "salt",
    "chlorinator_nominal_production": 35,
    "chlorinator_production_default": 70,
    "chlorinator_self_regulating": False,
    "chlorinator_active_months": [6, 7, 8, 9],
    "chlorinator_auto_toggle": True,
    "pump_switch": PUMP,
}


async def setup_helpers(hass: HomeAssistant) -> None:
    await async_setup_component(
        hass,
        "input_boolean",
        {"input_boolean": {"pump": {}, "chlorinator": {}, "hands_off": {}}},
    )


async def setup_pool(hass: HomeAssistant, **overrides: Any) -> MockConfigEntry:
    await setup_helpers(hass)
    entry = MockConfigEntry(domain=DOMAIN, title="Pool", data={**BASE, **overrides}, version=1)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
