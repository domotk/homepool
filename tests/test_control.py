"""The control loop against a real Home Assistant and a controlled clock."""

from __future__ import annotations

from datetime import datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.core import Context, HomeAssistant
from homeassistant.util import dt as dt_util

from .helpers import CHLORINATOR, HANDS_OFF, PUMP, SwitchRouter, setup_pool

TZ = "Europe/Madrid"


@pytest.fixture
async def madrid(hass: HomeAssistant):
    await hass.config.async_set_time_zone(TZ)
    yield


def local(*args) -> datetime:
    return datetime(*args, tzinfo=dt_util.get_time_zone(TZ))


async def tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, minutes: float = 1) -> None:
    """Advance the clock a minute at a time, letting the loop run each minute."""
    steps = max(1, int(minutes))
    for _ in range(steps):
        freezer.tick(timedelta(minutes=minutes / steps))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        router = hass.data.get("_test_router")
        if router is not None and router.deferred:
            await router.flush()
            await hass.async_block_till_done()


async def set_mode(hass: HomeAssistant, mode: str) -> None:
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.pool_operation_mode", "option": mode},
        blocking=True,
    )
    await hass.async_block_till_done()


def state(hass: HomeAssistant, entity_id: str) -> str:
    return hass.states.get(entity_id).state


async def test_smart_mode_runs_the_target_and_stops(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    router = SwitchRouter(hass)
    await setup_pool(hass)
    target = int(state(hass, "sensor.pool_daily_filtration_target"))
    assert target > 300  # July, no sensors: base × seasonal

    await set_mode(hass, "smart")
    assert state(hass, PUMP) == "on"
    assert state(hass, "sensor.pool_pump_control") == "mode"

    await tick(hass, freezer, 60)
    assert 59 <= int(state(hass, "sensor.pool_filtration_today")) <= 60

    await tick(hass, freezer, target - 60 + 2)
    assert state(hass, PUMP) == "off"
    assert state(hass, "binary_sensor.pool_daily_target_reached") == "on"
    # Exactly one start and one stop: no cycling.
    assert router.count("turn_on", PUMP) == 1
    assert router.count("turn_off", PUMP) == 1


async def test_hand_switching_is_respected(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 6, 0))
    SwitchRouter(hass)
    await setup_pool(hass, manual_override_minutes=60)
    await set_mode(hass, "smart")
    assert state(hass, PUMP) == "off"  # too early for the noon block

    # Someone switches it on by hand, with a context that is not HomePool's.
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": PUMP}, blocking=True, context=Context()
    )
    await tick(hass, freezer, 30)
    assert state(hass, PUMP) == "on"
    assert state(hass, "sensor.pool_pump_control") == "manual_override"

    # Once the override expires, the mode takes over again.
    await tick(hass, freezer, 35)
    assert state(hass, PUMP) == "off"
    assert state(hass, "sensor.pool_pump_control") == "mode"


async def test_hands_off_never_switches(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    router = SwitchRouter(hass)
    await setup_pool(hass, hands_off_entity=HANDS_OFF)
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": HANDS_OFF}, blocking=True)
    await set_mode(hass, "smart")
    await tick(hass, freezer, 10)
    assert state(hass, PUMP) == "off"
    assert router.count("turn_on", PUMP) == 0
    assert state(hass, "sensor.pool_pump_control") == "hands_off"


async def test_maintenance_lock_stops_at_once(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    await setup_pool(hass)
    await set_mode(hass, "smart")
    assert state(hass, PUMP) == "on"
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.pool_maintenance_lock"}, blocking=True
    )
    await hass.async_block_till_done()
    # No minimum run time for the lock.
    assert state(hass, PUMP) == "off"
    await tick(hass, freezer, 30)
    assert state(hass, PUMP) == "off"


async def test_chlorinator_follows_the_flow(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    router = SwitchRouter(hass)
    await setup_pool(hass, chlorinator_switch=CHLORINATOR)
    await set_mode(hass, "smart")
    assert state(hass, PUMP) == "on"
    # The cell waits for the flow to settle.
    assert state(hass, CHLORINATOR) == "off"
    await tick(hass, freezer, 3)
    assert state(hass, CHLORINATOR) == "on"

    # Stopping: the cell goes off first, then the pump.
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.pool_maintenance_lock"}, blocking=True
    )
    await hass.async_block_till_done()
    await tick(hass, freezer, 1)
    assert state(hass, CHLORINATOR) == "off"
    assert state(hass, PUMP) == "off"
    order = [c for c in router.calls if c[0] == "turn_off"]
    assert order[0] == ("turn_off", CHLORINATOR)


async def test_cell_on_without_flow_is_switched_off_at_start(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    from .helpers import setup_helpers

    await setup_helpers(hass)
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": CHLORINATOR}, blocking=True)
    await setup_pool(hass, chlorinator_switch=CHLORINATOR)
    assert state(hass, CHLORINATOR) == "off"


async def test_a_rejected_command_is_retried(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    router = SwitchRouter(hass)
    router.ignore[PUMP] = 1  # the first command is lost, like a relay saying 401
    await setup_pool(hass)
    await set_mode(hass, "smart")
    assert state(hass, PUMP) == "off"
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "on"
    assert router.count("turn_on", PUMP) == 2


async def test_a_dead_relay_raises_an_alert(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    router = SwitchRouter(hass)
    router.ignore[PUMP] = 99
    events = []
    hass.bus.async_listen("homepool_alert", events.append)
    await setup_pool(hass)
    await set_mode(hass, "smart")
    await tick(hass, freezer, 5)
    assert router.count("turn_on", PUMP) == 3  # gives up after three
    assert state(hass, "sensor.pool_status") == "action_required"
    assert [e.data["type"] for e in events] == ["pump_not_responding"]


async def test_midnight_splits_the_running_time(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 23, 30))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await hass.services.async_call(
        "homepool", "start_cycle", {"entity_id": "select.pool_operation_mode", "duration": 60},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert state(hass, PUMP) == "on"
    await tick(hass, freezer, 45)
    coordinator = entry.runtime_data
    assert coordinator.day.isoformat() == "2026-07-16"
    assert coordinator.history[-1]["day"] == "2026-07-15"
    assert 29 <= coordinator.history[-1]["elapsed"] <= 30
    assert 14 <= coordinator.elapsed_minutes <= 15


async def test_counters_survive_a_restart(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_mode(hass, "smart")
    await tick(hass, freezer, 40)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert int(state(hass, "sensor.pool_filtration_today")) >= 39
    assert state(hass, "select.pool_operation_mode") == "smart"


async def test_freeze_protection_runs_the_pump_in_off_mode(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 1, 15, 6, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.water", "1.0", {"unit_of_measurement": "°C"})
    await setup_pool(hass, water_temperature_sensor="sensor.water")
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "on"
    assert state(hass, "sensor.pool_pump_control") == "freeze_protection"
    hass.states.async_set("sensor.water", "6.0", {"unit_of_measurement": "°C"})
    await tick(hass, freezer, 2)
    # HomePool started it, so HomePool stops it once the reason has gone.
    assert state(hass, PUMP) == "off"
    assert state(hass, "sensor.pool_pump_control") == "mode"


async def test_flood_is_a_safety_shutoff(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    hass.states.async_set("binary_sensor.flood", "off")
    events = []
    hass.bus.async_listen("homepool_safety_shutoff", events.append)
    await setup_pool(hass, flood_sensor="binary_sensor.flood")
    await set_mode(hass, "smart")
    assert state(hass, PUMP) == "on"
    hass.states.async_set("binary_sensor.flood", "on")
    await hass.async_block_till_done()
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "off"
    assert state(hass, "binary_sensor.pool_safety_shutoff") == "on"
    assert len(events) == 1


async def test_solar_mode_follows_the_debounced_surplus(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 11, 16, 10, 0))
    router = SwitchRouter(hass)
    hass.states.async_set("sensor.grid", "2000", {"unit_of_measurement": "W"})
    await setup_pool(hass, solar_excess_sensor="sensor.grid", solar_excess_sign="export_positive")
    await set_mode(hass, "solar")
    assert state(hass, PUMP) == "off"
    await tick(hass, freezer, 6)
    assert state(hass, PUMP) == "on"
    # The meter now sees the pump: export drops by its draw, which is added
    # back, so it keeps running.
    hass.states.async_set("sensor.grid", str(2000 - 880), {"unit_of_measurement": "W"})
    await tick(hass, freezer, 15)
    assert state(hass, PUMP) == "on"
    # A short kettle: 300 W import for 5 minutes is tolerated.
    hass.states.async_set("sensor.grid", "-300", {"unit_of_measurement": "W"})
    await tick(hass, freezer, 5)
    hass.states.async_set("sensor.grid", "1000", {"unit_of_measurement": "W"})
    await tick(hass, freezer, 5)
    assert state(hass, PUMP) == "on"
    # Clouds for good: 800 W import with the pump on is gone after the delay.
    hass.states.async_set("sensor.grid", "-800", {"unit_of_measurement": "W"})
    await tick(hass, freezer, 12)
    assert state(hass, PUMP) == "off"
    assert router.count("turn_on", PUMP) == 1


async def test_ph_correction_runs_the_pump_within_its_daily_cap(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 6, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.ph", "7.9")
    await setup_pool(
        hass, ph_sensor="sensor.ph", has_ph_dosing=True,
        ph_correction_minutes=30, ph_correction_max_daily=60,
    )
    await set_mode(hass, "smart")
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "on"
    assert state(hass, "sensor.pool_pump_control") == "ph_correction"
    # The probe never recovers: the cap stops it after an hour.
    await tick(hass, freezer, 90)
    assert state(hass, PUMP) == "off"
    assert state(hass, "binary_sensor.pool_ph_correction") == "on"


async def test_a_late_confirmation_is_not_taken_for_a_hand(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 11, 16, 10, 0))
    router = SwitchRouter(hass)
    router.deferred = True
    hass.states.async_set("sensor.grid", "2000", {"unit_of_measurement": "W"})
    await setup_pool(hass, solar_excess_sensor="sensor.grid")
    await set_mode(hass, "solar")
    sources = set()
    for _ in range(8):
        await tick(hass, freezer, 1)
        sources.add(state(hass, "sensor.pool_pump_control"))
    assert state(hass, PUMP) == "on"
    hass.states.async_set("sensor.grid", "-900", {"unit_of_measurement": "W"})
    for _ in range(40):
        await tick(hass, freezer, 1)
        sources.add(state(hass, "sensor.pool_pump_control"))
    # Off when the surplus went, not held on for two hours as a "manual" choice.
    assert state(hass, PUMP) == "off"
    assert "manual_override" not in sources


async def test_a_stuck_cell_does_not_keep_the_pump_running(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    router = SwitchRouter(hass)
    hass.states.async_set("binary_sensor.flood", "off")
    events = []
    hass.bus.async_listen("homepool_alert", events.append)
    await setup_pool(hass, chlorinator_switch=CHLORINATOR, flood_sensor="binary_sensor.flood")
    await set_mode(hass, "smart")
    await tick(hass, freezer, 3)
    assert state(hass, CHLORINATOR) == "on"
    router.ignore[CHLORINATOR] = 99
    hass.states.async_set("binary_sensor.flood", "on")
    await hass.async_block_till_done()
    await tick(hass, freezer, 1)
    # The cell is asked to stop first, and the pump waits for it...
    assert state(hass, PUMP) == "on"
    # ...but only while the cell's retries last.
    await tick(hass, freezer, 4)
    assert state(hass, PUMP) == "off"
    assert "chlorinator_not_responding" in [e.data["type"] for e in events]


async def test_the_pools_own_air_sensor_beats_the_forecast(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    from homeassistant.core import SupportsResponse

    freezer.move_to(local(2026, 11, 25, 10, 0))
    hass.states.async_set("sensor.air", "14.1", {"unit_of_measurement": "°C"})
    hass.states.async_set("weather.home", "sunny")

    async def forecasts(call):
        return {"weather.home": {"forecast": [{"temperature": 17.7, "precipitation": 0}]}}

    hass.services.async_register(
        "weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY
    )
    SwitchRouter(hass)
    await setup_pool(
        hass, air_temperature_sensor="sensor.air", weather_entity="weather.home"
    )
    attrs = hass.states.get("sensor.pool_daily_filtration_target").attributes
    assert attrs["sources"]["temperature"] == "air_temperature_max"
    assert attrs["inputs"]["air_temperature"] == 14.1


async def test_the_reason_is_in_home_assistants_language(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 11, 25, 10, 0))
    SwitchRouter(hass)
    await setup_pool(hass)
    # Set after setup so the entity ids stay English; the reasons follow the
    # language at runtime.
    hass.config.language = "es"
    await tick(hass, freezer, 1)
    attrs = hass.states.get("sensor.pool_pump_control").attributes
    assert attrs["reason_key"] == "off_mode"
    assert attrs["reason"] == "Modo apagado: la bomba se maneja a mano"

    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": PUMP}, blocking=True,
        context=Context(user_id=(await hass.auth.async_create_user("Someone")).id),
    )
    await tick(hass, freezer, 1)
    attrs = hass.states.get("sensor.pool_pump_control").attributes
    assert attrs["reason_key"] == "manual_override_on"
    assert attrs["reason"] == "Encendida a mano; se respeta por ahora"


async def test_minutes_are_rounded_not_truncated(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 11, 25, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    # 90 s of running is 2 minutes, not the 1 that truncating gave; 89 s is 1.
    coordinator.elapsed_s = 90
    assert coordinator.elapsed_minutes == 2
    coordinator.elapsed_s = 89
    assert coordinator.elapsed_minutes == 1


async def test_a_sunny_air_sensor_is_held_near_the_forecast(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """A sensor reading 23 °C against a 17.7 °C forecast counts as 20.7 °C."""
    from homeassistant.core import SupportsResponse

    freezer.move_to(local(2026, 11, 25, 12, 0))
    hass.states.async_set("sensor.air", "23.0", {"unit_of_measurement": "°C"})
    hass.states.async_set("weather.home", "sunny")

    async def forecasts(call):
        return {"weather.home": {"forecast": [{"temperature": 17.7, "precipitation": 0}]}}

    hass.services.async_register(
        "weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY
    )
    SwitchRouter(hass)
    await setup_pool(
        hass, air_temperature_sensor="sensor.air", weather_entity="weather.home"
    )
    attrs = hass.states.get("sensor.pool_daily_filtration_target").attributes
    assert attrs["sources"]["temperature"] == "air_temperature_max_capped"
    assert attrs["inputs"]["air_temperature"] == 20.7
    # The floor is on the sensor, not only in the diagnostics.
    assert attrs["min_minutes"] is not None
    assert attrs["max_minutes"] >= attrs["min_minutes"]


async def _switch_on_under(hass: HomeAssistant, freezer, context: Context) -> dict:
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": PUMP}, blocking=True, context=context
    )
    await tick(hass, freezer, 1)
    return hass.states.get("sensor.pool_pump_control").attributes


async def test_an_automation_is_not_taken_for_a_hand(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 11, 25, 10, 0))
    SwitchRouter(hass)
    await setup_pool(hass)
    context = Context()
    hass.bus.async_fire(
        "automation_triggered",
        {"name": "Pump on with solar", "entity_id": "automation.pump_solar"},
        context=context,
    )
    # Recorded as the event fires, with nothing awaited: the automation's
    # service call may change the pump right after.
    assert context.id in hass.config_entries.async_entries("homepool")[0].runtime_data._runner_contexts
    attrs = await _switch_on_under(hass, freezer, context)
    assert state(hass, "sensor.pool_pump_control") == "manual_override"
    assert attrs["reason_key"] == "automation_override_on"
    assert attrs["reason"] == "Switched on by the automation «Pump on with solar»; respected for now"
    assert attrs["manual_override_by"] == "automation"


async def test_a_scripts_child_context_is_traced_to_it(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 11, 25, 10, 0))
    SwitchRouter(hass)
    await setup_pool(hass)
    run = Context()
    hass.bus.async_fire("script_started", {"name": "Morning", "entity_id": "script.morning"}, context=run)
    await hass.async_block_till_done()
    attrs = await _switch_on_under(hass, freezer, Context(parent_id=run.id))
    assert attrs["reason_key"] == "script_override_on"


async def test_a_change_with_no_person_or_automation_is_outside(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 11, 25, 10, 0))
    SwitchRouter(hass)
    await setup_pool(hass)
    attrs = await _switch_on_under(hass, freezer, Context())
    assert attrs["reason_key"] == "external_override_on"
    assert attrs["manual_override_by"] == "external"
