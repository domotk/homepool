"""Chemistry readings taken by hand: validated, ranged, and no longer trusted once stale."""

from __future__ import annotations

from datetime import datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

from custom_components.homepool.pool.readings import (
    DEFAULT_STALE_DAYS,
    KINDS,
    default_range,
    reading_status,
    validate,
)

from .helpers import PUMP, SwitchRouter, setup_pool
from .test_control import local, madrid, set_mode, state, tick  # noqa: F401
from .test_season import entity, next_day


async def _record(hass: HomeAssistant, kind: str, value: float) -> None:
    await hass.services.async_call(
        "homepool", "record_reading",
        {"entity_id": "sensor.pool_status", "kind": kind, "value": value}, blocking=True,
    )
    await hass.async_block_till_done()


# ── pure ──


def test_validate_rejects_impossible_values() -> None:
    with pytest.raises(ValueError):
        validate("ph", 15)
    with pytest.raises(ValueError):
        validate("salt", -1)
    with pytest.raises(ValueError):
        validate("lead", 1)
    validate("ph", 14)
    validate("total_alkalinity", 0)


def test_stale_reading_is_not_out_of_range() -> None:
    now = datetime(2026, 7, 31)
    low, high = default_range("total_alkalinity", True)
    stale = reading_status(
        "total_alkalinity", 60, now - timedelta(days=31), now, low, high, 30
    )
    assert stale.stale and not stale.out_of_range
    fresh = reading_status("total_alkalinity", 60, now - timedelta(days=29), now, low, high, 30)
    assert not fresh.stale and fresh.out_of_range


def test_ranges_and_stale_ages_follow_the_spec() -> None:
    assert default_range("cyanuric_acid", True) == (30, 50)
    assert default_range("cyanuric_acid", False) == (30, 80)
    assert default_range("combined_chlorine", True) == (None, 0.6)
    assert default_range("calcium_hardness", False) == (200, 400)
    assert DEFAULT_STALE_DAYS == {
        "ph": 7, "free_chlorine": 7, "salt": 30, "total_alkalinity": 30,
        "calcium_hardness": 90, "cyanuric_acid": 90, "combined_chlorine": 14,
    }
    assert set(DEFAULT_STALE_DAYS) == set(KINDS)


def test_a_one_sided_range_only_judges_that_side() -> None:
    now = datetime(2026, 7, 31)
    assert not reading_status("combined_chlorine", 0.2, now, now, None, 0.6, 14).out_of_range
    assert reading_status("combined_chlorine", 0.8, now, now, None, 0.6, 14).out_of_range


# ── service, sensors and alerts ──


async def test_record_reading_service_and_alert(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    sensor = "sensor.pool_total_alkalinity"
    assert state(hass, sensor) == "unknown"
    await _record(hass, "total_alkalinity", 60)
    assert float(state(hass, sensor)) == 60
    attrs = hass.states.get(sensor).attributes
    assert attrs["recorded_at"] and attrs["stale"] is False
    assert "total_alkalinity_out_of_range" in entry.runtime_data.alerts
    assert entry.runtime_data.alerts["total_alkalinity_out_of_range"]["severity"] == "warning"
    await _record(hass, "total_alkalinity", 100)
    assert "total_alkalinity_out_of_range" not in entry.runtime_data.alerts


async def test_every_new_kind_has_a_sensor(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    for kind, value in (("combined_chlorine", 0.9), ("calcium_hardness", 250), ("cyanuric_acid", 40)):
        await _record(hass, kind, value)
        assert float(state(hass, f"sensor.pool_{kind}")) == value
    alerts = entry.runtime_data.alerts
    assert "combined_chlorine_out_of_range" in alerts
    assert "calcium_hardness_out_of_range" not in alerts
    assert "cyanuric_acid_out_of_range" not in alerts


async def test_cyanuric_acid_range_depends_on_the_chlorination(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, chlorination_type="liquid")
    await _record(hass, "cyanuric_acid", 70)
    assert "cyanuric_acid_out_of_range" not in entry.runtime_data.alerts


async def test_free_chlorine_range_is_used(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(
        hass, free_chlorine_range_min=1.0, free_chlorine_range_max=3.0
    )
    await _record(hass, "free_chlorine", 0.4)
    assert "free_chlorine_out_of_range" in entry.runtime_data.alerts
    await _record(hass, "free_chlorine", 2.0)
    assert "free_chlorine_out_of_range" not in entry.runtime_data.alerts


async def test_free_chlorine_probe_is_judged_against_the_range(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.fc", "0.3")
    entry = await setup_pool(hass, free_chlorine_sensor="sensor.fc")
    await tick(hass, freezer, 1)
    assert "free_chlorine_out_of_range" in entry.runtime_data.alerts


async def test_stale_salt_stops_feeding_the_target(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await _record(hass, "salt", 2.8)
    await tick(hass, freezer, 1)
    assert "salt_low" in coordinator.alerts
    assert coordinator.salinity == (2.8, "manual_record")
    assert "reading_stale" not in coordinator.alerts

    await next_day(hass, freezer, 31)
    await tick(hass, freezer, 1)
    assert "salt_low" not in coordinator.alerts
    assert coordinator.salinity == (None, None)
    assert "salt" in coordinator.alerts["reading_stale"]["message"]
    assert coordinator.alerts["reading_stale"]["severity"] == "info"
    assert not any(t["task"] == "reading_stale" for t in coordinator.task_status())
    assert "reading_stale_due" not in coordinator.alerts


async def test_the_salinity_and_free_chlorine_sensors_show_a_stale_reading(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """The 0.1 sensors keep the last number and say it is old, like the new
    kinds; only the calculations and the alerts ignore it."""
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await _record(hass, "salt", 2.8)
    await _record(hass, "free_chlorine", 0.4)
    await tick(hass, freezer, 1)
    for sensor in ("sensor.pool_salinity", "sensor.pool_free_chlorine"):
        assert hass.states.get(sensor).attributes["stale"] is False

    await next_day(hass, freezer, 31)
    await tick(hass, freezer, 1)
    assert coordinator.salinity == (None, None)
    assert coordinator.free_chlorine == (None, None)
    assert "salt_low" not in coordinator.alerts
    assert "free_chlorine_out_of_range" not in coordinator.alerts
    for sensor, value in (("sensor.pool_salinity", 2.8), ("sensor.pool_free_chlorine", 0.4)):
        st = hass.states.get(sensor)
        assert float(st.state) == value
        assert st.attributes["stale"] is True
        assert st.attributes["source"] == "manual_record"
        assert st.attributes["recorded_at"]


async def test_in_active_wintering_the_water_test_interval_keeps_ph_and_chlorine_fresh(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """The water test is every 14 days in active wintering: a pH or a free
    chlorine measured on that schedule is not stale after 7."""
    freezer.move_to(local(2026, 11, 2, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    assert coordinator.season_state == "winter_active"
    assert coordinator.reading_stale_days("ph") == 14
    assert coordinator.reading_stale_days("free_chlorine") == 14
    assert coordinator.reading_stale_days("salt") == 30  # not a water test kind
    await _record(hass, "ph", 7.4)
    await _record(hass, "free_chlorine", 1.0)
    await next_day(hass, freezer, 10)
    assert not coordinator.manual_status("ph").stale
    assert not coordinator.manual_status("free_chlorine").stale
    await next_day(hass, freezer, 5)
    assert coordinator.manual_status("ph").stale

    # A longer water test interval stretches it; a longer stale age wins over it.
    hass.config_entries.async_update_entry(
        entry, options={"tasks": {"water_test": {"days": 21}}, "ph_stale_days": 30}
    )
    assert coordinator.reading_stale_days("free_chlorine") == 21
    assert coordinator.reading_stale_days("ph") == 30
    # Swimming: the stale ages are their own again.
    hass.config_entries.async_update_entry(entry, options={})
    coordinator.settings["season_state"] = "swimming"
    assert coordinator.reading_stale_days("ph") == 7


async def test_a_stale_reading_keeps_no_range_alert_and_says_so(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 1, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await _record(hass, "total_alkalinity", 60)
    await _record(hass, "free_chlorine", 0.4)
    assert "total_alkalinity_out_of_range" in coordinator.alerts
    await next_day(hass, freezer, 8)
    await tick(hass, freezer, 1)
    # Free chlorine (7 days) is stale; alkalinity (30 days) is not.
    assert "free_chlorine_out_of_range" not in coordinator.alerts
    assert "total_alkalinity_out_of_range" in coordinator.alerts
    assert coordinator.alerts["reading_stale"]["message"].count("free_chlorine") == 1
    first = coordinator.alerts["reading_stale"]["message"]
    await next_day(hass, freezer, 25)
    await tick(hass, freezer, 1)
    assert "total_alkalinity_out_of_range" not in coordinator.alerts
    second = coordinator.alerts["reading_stale"]["message"]
    assert second != first and "total_alkalinity" in second
    # The sensor still shows the last number, and says it is old.
    attrs = hass.states.get("sensor.pool_total_alkalinity").attributes
    assert float(state(hass, "sensor.pool_total_alkalinity")) == 60
    assert attrs["stale"] is True


async def test_a_new_reading_clears_the_stale_alert(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 1, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await _record(hass, "salt", 3.5)
    await next_day(hass, freezer, 31)
    await tick(hass, freezer, 1)
    assert "reading_stale" in entry.runtime_data.alerts
    await _record(hass, "salt", 3.6)
    assert "reading_stale" not in entry.runtime_data.alerts


async def test_a_probe_in_use_never_makes_the_manual_reading_stale(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 1, 10, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.sal", "3.6")
    entry = await setup_pool(hass, salinity_sensor="sensor.sal")
    await _record(hass, "salt", 3.5)
    await next_day(hass, freezer, 31)
    hass.states.async_set("sensor.sal", "3.6")
    await tick(hass, freezer, 1)
    assert "reading_stale" not in entry.runtime_data.alerts


async def test_the_stale_age_is_an_option(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 1, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, salt_stale_days=10)
    await _record(hass, "salt", 3.5)
    await next_day(hass, freezer, 11)
    await tick(hass, freezer, 1)
    assert entry.runtime_data.salinity == (None, None)


# ── what a reading does ──


async def test_invalid_reading_errors(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    with pytest.raises(HomeAssistantError) as err:
        await _record(hass, "ph", 20)
    assert err.value.translation_key == "invalid_reading"
    with pytest.raises(HomeAssistantError):
        await _record(hass, "salt", -1)
    assert entry.runtime_data.manual_readings == {}


async def test_ph_or_free_chlorine_counts_as_the_water_test(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 1, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await next_day(hass, freezer, 8)
    await tick(hass, freezer, 1)
    assert "water_test_due" in coordinator.alerts
    coordinator.task_pump_s["water_test"] = 99.0
    await _record(hass, "total_alkalinity", 100)
    assert "water_test_due" in coordinator.alerts  # not a water test
    await _record(hass, "free_chlorine", 1.5)
    assert "water_test_due" not in coordinator.alerts
    assert "water_test" not in coordinator.due_notified
    assert "water_test" not in coordinator.task_pump_s
    assert coordinator.actions[-1]["type"] == "water_tested"

    coordinator.due_notified["water_test"] = "2026-07-09"
    await _record(hass, "ph", 7.4)
    assert "water_test" not in coordinator.due_notified


async def test_a_manual_ph_stands_in_for_a_missing_probe(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    assert coordinator.ph is None
    await _record(hass, "ph", 7.9)
    assert coordinator.ph == 7.9
    assert float(state(hass, "sensor.pool_manual_ph")) == 7.9
    assert coordinator.ph_out_of_range
    await tick(hass, freezer, 1)
    assert "ph_out_of_range" in coordinator.alerts
    await next_day(hass, freezer, 8)
    await tick(hass, freezer, 1)
    assert coordinator.ph is None
    assert not coordinator.ph_out_of_range
    assert "ph_out_of_range" not in coordinator.alerts


async def test_the_probe_wins_over_a_manual_ph_and_has_no_manual_sensor(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.ph", "7.3")
    entry = await setup_pool(hass, ph_sensor="sensor.ph")
    await _record(hass, "ph", 7.9)
    assert entry.runtime_data.ph == 7.3
    assert hass.states.get("sensor.pool_manual_ph") is None


async def test_a_manual_ph_never_runs_the_pump_for_the_correction(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 6, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, has_ph_dosing=True)
    await set_mode(hass, "smart")
    await _record(hass, "ph", 8.2)
    await tick(hass, freezer, 5)
    assert state(hass, PUMP) == "off"
    assert not entry.runtime_data.ph_correction_active
    assert entry.runtime_data.ph == 8.2


async def test_readings_survive_a_reload(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await _record(hass, "cyanuric_acid", 45)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert float(state(hass, "sensor.pool_cyanuric_acid")) == 45


# ── the water step ──


async def test_the_water_step_sets_ranges_and_stale_ages(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "water"}
    )
    assert result["step_id"] == "water"
    shown = {str(k) for k in result["data_schema"].schema}
    assert {"total_alkalinity_range_min", "cyanuric_acid_range_max", "salt_stale_days"} <= shown
    assert "combined_chlorine_range_min" not in shown
    bad = await hass.config_entries.options.async_configure(
        result["flow_id"], {"total_alkalinity_range_min": 130}
    )
    assert bad["errors"] == {"total_alkalinity_range_min": "range_order"}
    done = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"total_alkalinity_range_max": 100, "salt_stale_days": 10},
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    assert coordinator.reading_range("total_alkalinity") == (80, 100)
    assert coordinator.reading_stale_days("salt") == 10
    assert coordinator.reading_stale_days("ph") == 7


async def test_reading_stale_does_not_change_the_status(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 1, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await _record(hass, "total_alkalinity", 100)
    await next_day(hass, freezer, 31)
    await entry.runtime_data.async_complete_task("water_test")
    await entry.runtime_data.async_complete_task("backwash")
    await entry.runtime_data.async_complete_task("skimmer_baskets")
    await tick(hass, freezer, 1)
    assert "reading_stale" in entry.runtime_data.alerts
    assert set(entry.runtime_data.alerts) == {"reading_stale"}
    assert not entry.runtime_data.manual_action_pending
    assert entry.runtime_data.overall_status == "ok"


async def test_no_reading_stale_in_passive_wintering(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    from .test_season import set_season

    freezer.move_to(local(2026, 7, 1, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await _record(hass, "salt", 3.5)
    await set_season(hass, entry, "winter_passive")
    await next_day(hass, freezer, 31)
    await tick(hass, freezer, 1)
    assert "reading_stale" not in entry.runtime_data.alerts


def test_validate_rejects_nan_and_infinity() -> None:
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            validate("free_chlorine", value)


async def test_the_cyanuric_acid_range_follows_the_chlorination_unless_changed(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)

    async def water_step(values):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "water"}
        )
        done = await hass.config_entries.options.async_configure(result["flow_id"], values)
        assert done["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

    # Saved with the salt range shown, untouched: nothing is written.
    await water_step({})
    assert entry.options.get("cyanuric_acid_range_max") is None
    assert entry.runtime_data.reading_range("cyanuric_acid") == (30, 50)
    # Leaving salt, the range follows it.
    await water_step({"chlorination_type": "liquid"})
    assert entry.runtime_data.reading_range("cyanuric_acid") == (30, 80)
    # A range the owner changed is kept.
    await water_step({"cyanuric_acid_range_max": 70})
    assert entry.options["cyanuric_acid_range_max"] == 70
    assert entry.runtime_data.reading_range("cyanuric_acid") == (30, 70)


async def test_salt_is_not_stale_while_the_cell_is_not_in_use(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    from .test_season import set_season

    freezer.move_to(local(2026, 7, 1, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await _record(hass, "salt", 3.5)
    await _record(hass, "total_alkalinity", 100)
    await set_season(hass, entry, "winter_active")
    await next_day(hass, freezer, 31)
    await tick(hass, freezer, 1)
    stale = entry.runtime_data.alerts["reading_stale"]["message"]
    assert "total_alkalinity" in stale
    assert "salt" not in stale


async def test_a_nan_reading_counts_as_unavailable(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """A sensor that reports nan or inf is not a number to act on: freeze
    protection falls back to the air, as it does with the water unavailable."""
    freezer.move_to(local(2026, 1, 15, 6, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.water", "nan")
    hass.states.async_set("sensor.air", "-3")
    entry = await setup_pool(
        hass, water_temperature_sensor="sensor.water", air_temperature_sensor="sensor.air"
    )
    coordinator = entry.runtime_data
    await tick(hass, freezer, 1)
    assert coordinator.water_temperature is None
    assert coordinator.freeze_active
    hass.states.async_set("sensor.water", "inf")
    await tick(hass, freezer, 1)
    assert coordinator.water_temperature is None
    assert coordinator.freeze_active


async def test_probes_raise_no_range_alerts_in_passive_wintering(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """Drained pipes: an in-line probe reads air or a dry cup."""
    from .test_season import set_season

    freezer.move_to(local(2026, 12, 15, 10, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.ph", "5.0")
    hass.states.async_set("sensor.fc", "0")
    entry = await setup_pool(hass, ph_sensor="sensor.ph", free_chlorine_sensor="sensor.fc")
    coordinator = entry.runtime_data
    await tick(hass, freezer, 1)
    assert "ph_out_of_range" in coordinator.alerts
    assert "free_chlorine_out_of_range" in coordinator.alerts
    await set_season(hass, entry, "winter_passive")
    await tick(hass, freezer, 1)
    assert "ph_out_of_range" not in coordinator.alerts
    assert "free_chlorine_out_of_range" not in coordinator.alerts
    assert not coordinator.ph_out_of_range
    assert hass.states.get("binary_sensor.pool_ph_out_of_range").state == "off"


async def test_a_reading_measured_again_does_not_raise_reading_stale_anew(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    events = []
    hass.bus.async_listen(
        "homepool_alert",
        lambda e: events.append(e) if e.data["type"] == "reading_stale" else None,
    )
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await _record(hass, "ph", 7.4)
    await _record(hass, "free_chlorine", 1.0)
    await next_day(hass, freezer, 15)
    await tick(hass, freezer, 1)
    await hass.async_block_till_done()
    assert len(events) == 1
    assert "ph" in coordinator.alerts["reading_stale"]["message"]
    # One measured again: the list shrinks, and that is not news.
    await _record(hass, "ph", 7.4)
    await tick(hass, freezer, 1)
    await hass.async_block_till_done()
    message = coordinator.alerts["reading_stale"]["message"]
    assert "free_chlorine" in message and "ph," not in message
    assert len(events) == 1
    # Another going stale is.
    await next_day(hass, freezer, 15)
    await tick(hass, freezer, 1)
    await hass.async_block_till_done()
    assert len(events) == 2
    assert "ph" in coordinator.alerts["reading_stale"]["message"]
