"""Set-up, entities and unload against a real Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .helpers import CHLORINATOR, setup_pool


async def test_setup_creates_entities(hass: HomeAssistant) -> None:
    entry = await setup_pool(hass)
    assert entry.state is ConfigEntryState.LOADED

    target = hass.states.get("sensor.pool_daily_filtration_target")
    assert target is not None
    assert int(target.state) > 0
    assert target.attributes["base_minutes"] == 281
    assert hass.states.get("select.pool_operation_mode").state == "off"
    assert hass.states.get("switch.pool_maintenance_lock").state == "off"
    assert hass.states.get("binary_sensor.pool_daily_target_reached").state == "off"
    # Salt pool: the chlorinator entities exist, the solar ones do not.
    assert hass.states.get("switch.pool_salt_chlorinator") is not None
    assert hass.states.get("number.pool_solar_surplus_threshold") is None
    # Off is the default: nothing is switched after installing.
    assert hass.states.get("input_boolean.pump").state == "off"


async def test_optional_entities_follow_config(hass: HomeAssistant) -> None:
    await setup_pool(hass, chlorination_type="tablets", chlorinator_switch=CHLORINATOR)
    assert hass.states.get("switch.pool_salt_chlorinator") is None
    assert hass.states.get("sensor.pool_salinity") is None


async def test_unload(hass: HomeAssistant) -> None:
    entry = await setup_pool(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not hass.services.has_service("homepool", "start_cycle")
