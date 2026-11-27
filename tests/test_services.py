"""Services, manual records, diagnostics, and the entity ids the README promises."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.homepool.diagnostics import async_get_config_entry_diagnostics

from .helpers import CHLORINATOR, SwitchRouter, setup_pool

FULL = {
    "chlorinator_switch": CHLORINATOR,
    "ph_sensor": "sensor.ph",
    "has_ph_dosing": True,
    "pump_power_sensor": "sensor.pump_power",
    "pump_energy_sensor": "sensor.pump_energy",
    "energy_price": 0.15,
    "water_temperature_sensor": "sensor.water",
    "flood_sensor": "binary_sensor.flood",
    "equipment_room_temperature_sensor": "sensor.room",
    "solar_excess_sensor": "sensor.grid",
}


async def test_readme_entity_ids_exist(hass: HomeAssistant) -> None:
    SwitchRouter(hass)
    entry = await setup_pool(hass, **FULL)
    ids = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    for expected in (
        "sensor.pool_daily_filtration_target",
        "sensor.pool_filtration_today",
        "sensor.pool_filtration_left_today",
        "sensor.pool_pump_control",
        "sensor.pool_status",
        "sensor.pool_next_manual_task",
        "sensor.pool_recommended_chlorinator_production",
        "sensor.pool_chlorine_production_today",
        "sensor.pool_chlorine_production_left_today",
        "sensor.pool_salinity",
        "sensor.pool_free_chlorine",
        "sensor.pool_ph_trend",
        "sensor.pool_pump_energy_today",
        "sensor.pool_pump_cost_today",
        "binary_sensor.pool_daily_target_reached",
        "binary_sensor.pool_pump_running",
        "binary_sensor.pool_safety_shutoff",
        "binary_sensor.pool_freeze_protection",
        "binary_sensor.pool_pump_power_anomaly",
        "binary_sensor.pool_ph_out_of_range",
        "binary_sensor.pool_ph_correction",
        "binary_sensor.pool_filter_needs_cleaning",
        "binary_sensor.pool_manual_task_due",
        "select.pool_operation_mode",
        "switch.pool_pump",
        "switch.pool_maintenance_lock",
        "switch.pool_chlorinator_in_use",
        "number.pool_filtration_multiplier",
        "number.pool_solar_surplus_threshold",
        "number.pool_ph_target",
        "number.pool_chlorinator_production",
        "button.pool_start_cycle",
        "button.pool_stop_cycle",
        "button.pool_backwash_done",
        "button.pool_filter_cleaned",
        "button.pool_salt_added",
        "button.pool_ph_probe_calibrated",
        "button.pool_recalculate_target",
    ):
        assert expected in ids, expected
    # With a surplus sensor, the solar modes are offered.
    assert "smart_solar" in hass.states.get("select.pool_operation_mode").attributes["options"]


async def test_manual_records_feed_the_sensors(hass: HomeAssistant, freezer) -> None:
    # In the chlorinator's season: out of it, low salt is not an alert.
    freezer.move_to("2026-07-15 10:00:00+00:00")
    SwitchRouter(hass)
    await setup_pool(hass)
    await hass.services.async_call(
        "homepool", "record_salt_level", {"entity_id": "sensor.pool_status", "value": 2.6},
        blocking=True,
    )
    await hass.async_block_till_done()
    salinity = hass.states.get("sensor.pool_salinity")
    assert float(salinity.state) == 2.6
    assert salinity.attributes["source"] == "manual_record"
    # Salt below the range is an alert.
    assert "salt_low" in hass.states.get("sensor.pool_status").attributes["alerts"]

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.pool_backwash_done"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.pool_days_since_the_filter_was_cleaned").state == "0"
    assert hass.states.get("binary_sensor.pool_filter_needs_cleaning").state == "off"


async def test_raising_the_multiplier_raises_the_target(hass: HomeAssistant) -> None:
    SwitchRouter(hass)
    await setup_pool(hass)
    before = int(hass.states.get("sensor.pool_daily_filtration_target").state)
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.pool_filtration_multiplier", "value": 1.5},
        blocking=True,
    )
    await hass.async_block_till_done()
    after = int(hass.states.get("sensor.pool_daily_filtration_target").state)
    assert after > before


async def test_diagnostics_redact_the_location(hass: HomeAssistant) -> None:
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["data"]["latitude"] == "**REDACTED**"
    assert diag["controller"]["target"]["target_minutes"] > 0
    assert "store" in diag["controller"]


async def test_a_service_aimed_at_nothing_is_refused(hass: HomeAssistant) -> None:
    import pytest
    from homeassistant.exceptions import ServiceValidationError

    SwitchRouter(hass)
    await setup_pool(hass)
    hass.states.async_set("sensor.unrelated", "1")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "homepool", "start_cycle", {"entity_id": "sensor.unrelated"}, blocking=True
        )


async def test_the_card_can_find_every_entity(hass: HomeAssistant) -> None:
    SwitchRouter(hass)
    entry = await setup_pool(hass, **FULL)
    # The index fills in once every platform has registered its entities.
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    attrs = hass.states.get("sensor.pool_daily_filtration_target").attributes
    assert attrs["pool_entities"]["pump_control"] == "sensor.pool_pump_control"
    assert attrs["pool_entities"]["operation_mode"] == "select.pool_operation_mode"
    assert attrs["entities"]["ph_sensor"] == "sensor.ph"
    assert attrs["shape"] == "rectangular"


# ── who may call the services ──


async def _user(hass: HomeAssistant, group: str | None):
    """A user of a group; never the first, which Home Assistant makes the owner."""
    if not any(not u.system_generated for u in await hass.auth.async_get_users()):
        await hass.auth.async_create_user("Owner")
    groups = [group] if group else []
    user = await hass.auth.async_create_user("Someone", group_ids=groups)
    assert not user.is_owner
    return user


async def test_a_read_only_user_cannot_drive_the_pool(hass: HomeAssistant) -> None:
    """A user whose policy only reads entities is refused, as an entity service
    would refuse them; nothing changes."""
    import pytest
    from homeassistant.core import Context
    from homeassistant.exceptions import Unauthorized

    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    own = coordinator.own_entities()
    user = await _user(hass, "system-read-only")
    context = Context(user_id=user.id)

    # The control: the pool's own select refuses them.
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "select", "select_option",
            {"entity_id": own["season_state"], "option": "winter_passive"},
            blocking=True, context=context,
        )
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "homepool", "set_season_state",
            {"entity_id": own["season_state"], "state": "winter_passive"},
            blocking=True, context=context,
        )
    assert coordinator.season_state != "winter_passive"
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "homepool", "start_cycle", {"entity_id": own["season_state"]},
            blocking=True, context=context,
        )
    assert coordinator.cycle_until is None
    # Targeted by device, too.
    device_id = er.async_get(hass).async_get(own["season_state"]).device_id
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "homepool", "start_cycle", {"device_id": device_id},
            blocking=True, context=context,
        )
    assert coordinator.cycle_until is None


async def test_admins_users_and_automations_may_call_the_services(hass: HomeAssistant) -> None:
    from homeassistant.core import Context

    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    target = {"entity_id": coordinator.own_entities()["season_state"]}
    for context in (
        Context(user_id=(await _user(hass, "system-admin")).id),
        Context(user_id=(await _user(hass, "system-users")).id),
        Context(),  # an automation: no user
        None,
    ):
        coordinator.cycle_until = None
        await hass.services.async_call(
            "homepool", "start_cycle", target, blocking=True, context=context
        )
        assert coordinator.cycle_until is not None


async def test_an_unknown_user_is_refused(hass: HomeAssistant) -> None:
    import pytest
    from homeassistant.core import Context
    from homeassistant.exceptions import UnknownUser

    SwitchRouter(hass)
    entry = await setup_pool(hass)
    with pytest.raises(UnknownUser):
        await hass.services.async_call(
            "homepool", "start_cycle",
            {"entity_id": entry.runtime_data.own_entities()["season_state"]},
            blocking=True, context=Context(user_id="no-such-user"),
        )


async def test_a_manual_action_needs_a_finite_value_and_short_notes(hass: HomeAssistant) -> None:
    import pytest
    import voluptuous as vol

    SwitchRouter(hass)
    entry = await setup_pool(hass)
    target = {"entity_id": entry.runtime_data.own_entities()["season_state"]}
    for bad in ({"value": float("nan")}, {"value": "inf"}, {"notes": "x" * 501}):
        with pytest.raises(vol.Invalid):
            await hass.services.async_call(
                "homepool", "record_manual_action",
                {**target, "action_type": "backwash", **bad}, blocking=True,
            )
    await hass.services.async_call(
        "homepool", "record_manual_action",
        {**target, "action_type": "backwash", "value": 2, "notes": "x" * 500}, blocking=True,
    )
    assert entry.runtime_data.actions[-1]["notes"] == "x" * 500


async def test_bulky_attributes_are_not_recorded(hass: HomeAssistant) -> None:
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    own = entry.runtime_data.own_entities()
    tasks = hass.data["sensor"].get_entity(own["next_manual_task"])
    assert {"tasks", "checklists", "recent_actions", "winter_product"} <= tasks._unrecorded_attributes
    treatment = hass.data["sensor"].get_entity(own["water_treatment"])
    assert "phase_until" in treatment._unrecorded_attributes
