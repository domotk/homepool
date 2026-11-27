"""Water treatments: shock, clarifier and flocculant, on the pump's own clock."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from custom_components.homepool.pool.treatment import (
    DEFAULT_HOURS,
    PHASES,
    PUMP,
    Phase,
    TreatmentType,
    counts_pump_time,
    next_phase,
    phase_done,
)

from .helpers import CHLORINATOR, PUMP as PUMP_SWITCH, SwitchRouter, setup_pool
from .test_control import local, madrid, set_mode, state, tick  # noqa: F401
from .test_season import entity, set_season


async def advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, minutes: float, step: float = 15
) -> None:
    """Move the clock in jumps of ``step`` minutes, letting the loop run after each.

    The counters are charged by elapsed time, so a jump counts the same as
    the minutes in it; a day minute by minute is only slower.
    """
    left = minutes
    while left > 0:
        jump = min(step, left)
        freezer.tick(timedelta(minutes=jump))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        left -= jump


async def start(hass: HomeAssistant, entry, kind: str, **fields) -> None:
    await hass.services.async_call(
        "homepool", "start_treatment",
        {"entity_id": entity(entry, "overall_status"), "type": kind, **fields}, blocking=True,
    )
    await hass.async_block_till_done()


async def press(hass: HomeAssistant, entry, key: str) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": entity(entry, key)}, blocking=True
    )
    await hass.async_block_till_done()


def control(hass: HomeAssistant, entry) -> tuple[str, str]:
    st = hass.states.get(entity(entry, "pump_control"))
    return st.state, st.attributes["reason_key"]


def reason_keys(hass: HomeAssistant, entry) -> list[str]:
    """Every reason key the control sensor shows from now on, in order."""
    seen: list[str] = []
    entity_id = entity(entry, "pump_control")

    @callback
    def _changed(event) -> None:
        new = event.data["new_state"]
        key = new.attributes.get("reason_key") if new else None
        if key and (not seen or seen[-1] != key):
            seen.append(key)

    async_track_state_change_event(hass, [entity_id], _changed)
    return seen


def treatment_state(hass: HomeAssistant, entry):
    return hass.states.get(entity(entry, "water_treatment"))


def not_advised(hass: HomeAssistant, entry):
    return hass.states.get(entity(entry, "swimming_not_advised"))


def backwash_overdue(entry) -> bool:
    return next(t for t in entry.runtime_data.task_status() if t["task"] == "backwash")["overdue"]


# ── pure ──


def test_phases_and_their_pump() -> None:
    assert PHASES[TreatmentType.SHOCK] == (Phase.FILTERING,)
    assert PHASES[TreatmentType.FLOCCULANT] == (Phase.MIXING, Phase.SETTLING, Phase.VACUUMING)
    assert DEFAULT_HOURS[(TreatmentType.CLARIFIER, Phase.FILTERING)] == 48
    assert (TreatmentType.FLOCCULANT, Phase.VACUUMING) not in DEFAULT_HOURS
    assert PUMP == {
        Phase.FILTERING: True, Phase.MIXING: True, Phase.SETTLING: False, Phase.VACUUMING: None,
    }
    assert counts_pump_time(Phase.MIXING) and not counts_pump_time(Phase.SETTLING)
    assert next_phase(TreatmentType.FLOCCULANT, Phase.SETTLING) == Phase.VACUUMING
    assert next_phase(TreatmentType.FLOCCULANT, Phase.VACUUMING) is None
    assert next_phase(TreatmentType.SHOCK, Phase.FILTERING) is None
    assert phase_done(Phase.FILTERING, 24, 24 * 3600)
    assert not phase_done(Phase.FILTERING, 24, 24 * 3600 - 1)
    # Vacuuming has no clock: it waits for the owner.
    assert not phase_done(Phase.VACUUMING, None, 10**9)


# ── shock ──


async def test_shock_runs_24h_of_pump_time_across_midnight(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 20, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_mode(hass, "off")
    fired: list[str] = []
    for name in ("started", "phase", "ended"):
        hass.bus.async_listen(
            f"homepool_treatment_{name}", lambda e, name=name: fired.append(name)
        )
    await start(hass, entry, "shock")

    assert state(hass, PUMP_SWITCH) == "on"
    assert control(hass, entry) == ("treatment", "treatment_filtering")
    sensor = treatment_state(hass, entry)
    assert sensor.state == "shock"
    assert sensor.attributes["phase"] == "filtering"
    assert sensor.attributes["severity"] == "green"
    assert sensor.attributes["dose"]["unit"] == "g"
    assert sensor.attributes["dose"]["amount"] == 690  # 30 m³ × 15 mg/L at 65 %
    assert not_advised(hass, entry).attributes["reason"] == "treatment"
    assert "treatment" in entry.runtime_data.checklists

    await advance(hass, freezer, 24 * 60 - 1)  # 2026-07-16 19:59
    assert state(hass, PUMP_SWITCH) == "on"
    assert treatment_state(hass, entry).state == "shock"

    keys = reason_keys(hass, entry)
    await advance(hass, freezer, 2, step=1)  # 20:01
    assert treatment_state(hass, entry).state == "none"
    assert state(hass, PUMP_SWITCH) == "off"
    # The treatment started it, so the treatment's end let it go.
    assert keys[0] == "released_treatment"
    assert backwash_overdue(entry)
    assert fired == ["started", "ended"]
    advised = not_advised(hass, entry)
    assert advised.state == "on"
    assert advised.attributes["reason"] == "after_shock"
    # The step list stays for the steps that come after.
    assert "treatment" in entry.runtime_data.checklists

    await entry.runtime_data.async_record_reading("free_chlorine", 2.0)
    await hass.async_block_till_done()
    assert not_advised(hass, entry).state == "off"

    # A backwash clears what the treatment left due.
    await entry.runtime_data.async_complete_step("treatment.backwash")
    assert not backwash_overdue(entry)


async def test_a_lock_pauses_the_shock_clock(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 20, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await start(hass, entry, "shock")
    await advance(hass, freezer, 60)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": entity(entry, "maintenance_lock")}, blocking=True
    )
    await hass.async_block_till_done()
    assert state(hass, PUMP_SWITCH) == "off"
    await advance(hass, freezer, 60)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity(entry, "maintenance_lock")}, blocking=True
    )
    await hass.async_block_till_done()
    assert state(hass, PUMP_SWITCH) == "on"
    assert control(hass, entry) == ("treatment", "treatment_filtering")

    await advance(hass, freezer, 23 * 60 - 2)  # 2026-07-16 20:58
    assert treatment_state(hass, entry).state == "shock"
    assert state(hass, PUMP_SWITCH) == "on"
    await advance(hass, freezer, 3, step=1)  # 21:01
    assert treatment_state(hass, entry).state == "none"


async def test_hours_change_the_main_phase(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await start(hass, entry, "clarifier", hours=2)
    until = dt_util.parse_datetime(treatment_state(hass, entry).attributes["phase_until"])
    assert abs((until - dt_util.utcnow()).total_seconds() - 2 * 3600) < 60
    await advance(hass, freezer, 121, step=1)
    assert treatment_state(hass, entry).state == "none"


async def test_the_shock_runs_the_cell_regardless_of_todays_production(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    hass.states.async_set("input_number.production", "70")
    entry = await setup_pool(
        hass,
        chlorinator_switch=CHLORINATOR,
        chlorinator_controllable=True,
        chlorinator_production_entity="input_number.production",
    )
    coordinator = entry.runtime_data
    pushed: list[float] = []

    async def _set_value(call) -> None:
        pushed.append(call.data["value"])

    hass.services.async_register("input_number", "set_value", _set_value)
    coordinator.chlorine_s = 10 * 3600  # today's production is long done
    await start(hass, entry, "shock")
    assert pushed == [100]
    await advance(hass, freezer, 5, step=1)
    assert state(hass, CHLORINATOR) == "on"
    await press(hass, entry, "end_treatment")
    assert pushed == [100, 70]
    assert state(hass, CHLORINATOR) == "off"


# ── flocculant ──


async def _to_settling(hass, freezer, entry) -> None:
    await start(hass, entry, "flocculant")
    assert state(hass, PUMP_SWITCH) == "on"
    assert control(hass, entry) == ("treatment", "treatment_mixing")
    await advance(hass, freezer, 119)
    assert state(hass, PUMP_SWITCH) == "on"
    await advance(hass, freezer, 2)
    assert state(hass, PUMP_SWITCH) == "off"
    assert control(hass, entry) == ("treatment", "treatment_settling")
    assert treatment_state(hass, entry).attributes["phase"] == "settling"


async def test_flocculant_phases(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, chlorinator_switch=CHLORINATOR)
    await set_mode(hass, "off")
    phases: list[str] = []
    hass.bus.async_listen("homepool_treatment_phase", lambda e: phases.append(e.data["phase"]))
    await _to_settling(hass, freezer, entry)

    await advance(hass, freezer, 12 * 60 - 2)  # 23:59
    assert state(hass, PUMP_SWITCH) == "off"
    assert treatment_state(hass, entry).attributes["phase"] == "settling"
    await advance(hass, freezer, 3, step=1)  # 00:02
    assert treatment_state(hass, entry).attributes["phase"] == "vacuuming"
    assert treatment_state(hass, entry).attributes["phase_until"] is None
    assert control(hass, entry) == ("treatment", "treatment_vacuuming")
    assert phases == ["settling", "vacuuming"]

    # The owner runs the pump to vacuum: not an override, and not undone.
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": PUMP_SWITCH}, blocking=True, context=Context()
    )
    await advance(hass, freezer, 10, step=1)
    coordinator = entry.runtime_data
    assert coordinator.override is None
    assert state(hass, PUMP_SWITCH) == "on"
    assert control(hass, entry) == ("treatment", "treatment_vacuuming")
    # The valve is on waste: no water goes through the cell.
    assert state(hass, CHLORINATOR) == "off"
    # Switched off by hand as well.
    await hass.services.async_call(
        "input_boolean", "turn_off", {"entity_id": PUMP_SWITCH}, blocking=True, context=Context()
    )
    await advance(hass, freezer, 2, step=1)
    assert coordinator.override is None
    assert state(hass, PUMP_SWITCH) == "off"

    await press(hass, entry, "advance_treatment")  # vacuuming done
    assert treatment_state(hass, entry).state == "none"
    assert backwash_overdue(entry)
    # Only a shock leaves the water too strong to swim.
    assert not_advised(hass, entry).state == "off"


async def test_restart_mid_settling(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_mode(hass, "smart")
    await _to_settling(hass, freezer, entry)  # 12:01, the smart block is on
    await advance(hass, freezer, 6 * 60)  # 18:01

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert treatment_state(hass, entry).attributes["phase"] == "settling"
    await tick(hass, freezer, 2)
    assert state(hass, PUMP_SWITCH) == "off"
    assert control(hass, entry) == ("treatment", "treatment_settling")

    await advance(hass, freezer, 6 * 60 - 3)  # 23:59
    assert treatment_state(hass, entry).attributes["phase"] == "settling"
    await advance(hass, freezer, 3, step=1)
    assert treatment_state(hass, entry).attributes["phase"] == "vacuuming"


async def test_frost_during_settling(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.water", "20")
    entry = await setup_pool(hass, water_temperature_sensor="sensor.water")
    coordinator = entry.runtime_data
    await _to_settling(hass, freezer, entry)
    await advance(hass, freezer, 3 * 60)
    before = coordinator.treatment["counted_s"]
    assert abs(before - 3 * 3600) < 60

    hass.states.async_set("sensor.water", "1")
    await hass.async_block_till_done()
    assert state(hass, PUMP_SWITCH) == "on"
    assert control(hass, entry)[0] == "freeze_protection"
    assert "treatment_frost" in coordinator.alerts
    assert coordinator.treatment["frost_interrupted"] is True
    await advance(hass, freezer, 60)

    hass.states.async_set("sensor.water", "5")
    await hass.async_block_till_done()
    assert state(hass, PUMP_SWITCH) == "off"
    assert control(hass, entry) == ("treatment", "treatment_settling")
    assert "treatment_frost" not in coordinator.alerts
    await advance(hass, freezer, 60)
    # Two hours of wall time, one of them with the pump running for the frost.
    assert abs(coordinator.treatment["counted_s"] - before - 3600) < 60


# ── when it may run ──


async def test_no_treatment_in_winter_passive(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 11, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_season(hass, entry, "winter_passive")
    with pytest.raises(HomeAssistantError):
        await start(hass, entry, "shock")
    assert entry.runtime_data.treatment is None
    assert state(hass, PUMP_SWITCH) == "off"


async def test_only_one_treatment_at_a_time(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await press(hass, entry, "start_clarifier")
    assert treatment_state(hass, entry).state == "clarifier"
    with pytest.raises(HomeAssistantError):
        await start(hass, entry, "shock")
    assert treatment_state(hass, entry).state == "clarifier"


async def test_passive_wintering_ends_a_running_treatment(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 10, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_season(hass, entry, "swimming")
    await set_season(hass, entry, "winter_active")
    await press(hass, entry, "start_shock")
    assert "closing" in entry.runtime_data.checklists
    assert "treatment" in entry.runtime_data.checklists
    await set_season(hass, entry, "winter_passive")
    assert treatment_state(hass, entry).state == "none"
    # Its own step list goes with it.
    assert "treatment" not in entry.runtime_data.checklists
    assert state(hass, PUMP_SWITCH) == "off"
    # The shock did not get to run: its closing step is not ticked.
    closing = entry.runtime_data.checklists["closing"]["steps"]
    assert next(s for s in closing if s["id"] == "closing.shock")["done"] is None


async def test_ending_a_shock_ticks_the_closing_step(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 10, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_season(hass, entry, "swimming")
    await set_season(hass, entry, "winter_active")
    await press(hass, entry, "start_shock")
    await press(hass, entry, "end_treatment")
    closing = entry.runtime_data.checklists["closing"]["steps"]
    assert next(s for s in closing if s["id"] == "closing.shock")["done"] is not None


async def test_a_treatment_survives_a_reload(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await start(hass, entry, "shock", severity="dark")
    await advance(hass, freezer, 60)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    sensor = treatment_state(hass, entry)
    assert sensor.state == "shock"
    assert sensor.attributes["severity"] == "dark"
    assert sensor.attributes["dose"]["amount"] == 920  # 30 m³ × 20 mg/L at 65 %
    assert sensor.attributes["phase"] == "filtering"
    assert abs(entry.runtime_data.treatment["counted_s"] - 3600) < 60
    assert state(hass, PUMP_SWITCH) == "on"


async def test_high_free_chlorine_is_not_for_swimming(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    assert not_advised(hass, entry).state == "off"
    await entry.runtime_data.async_record_reading("free_chlorine", 6.0)
    await hass.async_block_till_done()
    advised = not_advised(hass, entry)
    assert advised.state == "on"
    assert advised.attributes["reason"] == "free_chlorine_high"


async def test_the_options_set_the_doses(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    from homeassistant.data_entry_flow import FlowResultType

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

    # The concentration left as shown for calcium hypochlorite (65) follows
    # the product: a liquid's 150 g/L, not 65 g/L.
    await water_step({"shock_product": "sodium_hypochlorite", "shock_concentration": 65})
    await start(hass, entry, "shock")
    dose = treatment_state(hass, entry).attributes["dose"]
    assert (dose["amount"], dose["unit"], dose["concentration"]) == (3.0, "L", 150)
    await press(hass, entry, "end_treatment")

    await water_step({"flocculant_dose_per_10m3": 50, "flocculant_dose_unit": "g"})
    await start(hass, entry, "flocculant")
    dose = treatment_state(hass, entry).attributes["dose"]
    assert (dose["amount"], dose["unit"], dose["follow_label"]) == (150, "g", True)
    # The dose also goes with the step that asks for it.
    steps = entry.runtime_data.checklist_view()["treatment"]
    assert next(s for s in steps if s["id"] == "treatment.dose")["dose"] == dose
    await press(hass, entry, "end_treatment")

    await start(hass, entry, "clarifier")
    dose = treatment_state(hass, entry).attributes["dose"]
    assert dose["amount"] is None and dose["follow_label"]


# ── review round 1 ──


async def _to_vacuuming(hass, freezer, entry) -> None:
    await _to_settling(hass, freezer, entry)
    await press(hass, entry, "advance_treatment")
    assert treatment_state(hass, entry).attributes["phase"] == "vacuuming"


async def test_homepool_pump_controls_are_refused_while_vacuuming(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_mode(hass, "off")
    await _to_vacuuming(hass, freezer, entry)
    coordinator = entry.runtime_data

    for service in ("turn_on", "turn_off"):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "switch", service, {"entity_id": entity(entry, "pump")}, blocking=True
            )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "homepool", "start_cycle", {"entity_id": entity(entry, "overall_status")},
            blocking=True,
        )
    assert coordinator.cycle_until is None and coordinator.override is None

    # The owner runs it at its own switch, then says the vacuuming is done.
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": PUMP_SWITCH}, blocking=True, context=Context()
    )
    await hass.async_block_till_done()
    await press(hass, entry, "advance_treatment")
    await advance(hass, freezer, 5, step=1)
    assert treatment_state(hass, entry).state == "none"
    # Left as the owner left it: not stopped, not taken over.
    assert state(hass, PUMP_SWITCH) == "on"
    assert coordinator.cycle_until is None and coordinator.override is None


async def test_the_end_drops_a_cycle_asked_for_during_the_treatment(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_mode(hass, "off")
    await _to_settling(hass, freezer, entry)
    # Left from before the treatment (asking for one now is refused).
    entry.runtime_data.cycle_until = dt_util.utcnow() + timedelta(minutes=600)
    await advance(hass, freezer, 1, step=1)
    assert state(hass, PUMP_SWITCH) == "off"  # below the treatment: waits
    await press(hass, entry, "end_treatment")
    await advance(hass, freezer, 2, step=1)
    assert entry.runtime_data.cycle_until is None
    assert state(hass, PUMP_SWITCH) == "off"


async def test_frost_in_vacuuming_is_released_when_it_passes(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.water", "20")
    entry = await setup_pool(hass, water_temperature_sensor="sensor.water")
    await set_mode(hass, "off")
    await _to_vacuuming(hass, freezer, entry)

    hass.states.async_set("sensor.water", "1")
    await hass.async_block_till_done()
    assert state(hass, PUMP_SWITCH) == "on"
    assert control(hass, entry)[0] == "freeze_protection"

    await advance(hass, freezer, 30)
    keys = reason_keys(hass, entry)
    hass.states.async_set("sensor.water", "5")
    # The refresh the sensor asks for waits out the coordinator's cooldown.
    await advance(hass, freezer, 1, step=1)
    assert state(hass, PUMP_SWITCH) == "off"
    assert keys[0] == "released_freeze_protection"
    await advance(hass, freezer, 2, step=1)
    assert control(hass, entry) == ("treatment", "treatment_vacuuming")
    assert state(hass, PUMP_SWITCH) == "off"


async def test_a_pump_already_on_is_let_go_when_the_shock_ends(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 20, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_mode(hass, "off")
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": PUMP_SWITCH}, blocking=True, context=Context()
    )
    await hass.async_block_till_done()
    assert control(hass, entry)[0] == "manual_override"

    await start(hass, entry, "shock")
    assert control(hass, entry) == ("treatment", "treatment_filtering")
    await advance(hass, freezer, 24 * 60 - 1)
    assert state(hass, PUMP_SWITCH) == "on"
    keys = reason_keys(hass, entry)
    await advance(hass, freezer, 2, step=1)
    assert treatment_state(hass, entry).state == "none"
    assert state(hass, PUMP_SWITCH) == "off"
    assert keys[0] == "released_treatment"


async def test_a_backwash_done_during_the_treatment_is_not_due_again(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_mode(hass, "off")
    coordinator = entry.runtime_data
    await _to_vacuuming(hass, freezer, entry)
    await coordinator.async_complete_step("treatment.backwash")
    await press(hass, entry, "advance_treatment")  # vacuuming done
    assert treatment_state(hass, entry).state == "none"
    assert not coordinator.backwash_after_treatment
    assert not backwash_overdue(entry)


async def test_a_backwash_from_before_the_treatment_does_not_count(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_mode(hass, "off")
    coordinator = entry.runtime_data
    await coordinator.async_complete_task("backwash")
    await advance(hass, freezer, 5, step=1)
    await _to_vacuuming(hass, freezer, entry)
    await press(hass, entry, "advance_treatment")
    assert coordinator.backwash_after_treatment
    assert backwash_overdue(entry)


async def test_vacuuming_reminds_after_3_hours_then_daily_and_never_ends_alone(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    from .test_winter import NOTIFY, _notified

    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    calls = await _notified(hass)
    entry = await setup_pool(hass, **{**NOTIFY, "notification_quiet_hours_start": None,
                                      "notification_quiet_hours_end": None})
    await set_mode(hass, "off")
    await _to_vacuuming(hass, freezer, entry)

    def reminders() -> int:
        return len([c for c in calls if "vacuum" in c.data["message"].lower()])

    await advance(hass, freezer, 3 * 60 - 5)
    assert reminders() == 0
    await advance(hass, freezer, 10, step=1)
    assert reminders() == 1
    # Not again after a reload.
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await advance(hass, freezer, 23 * 60)
    assert reminders() == 1
    await advance(hass, freezer, 60)
    assert reminders() == 2
    assert treatment_state(hass, entry).attributes["phase"] == "vacuuming"


async def test_a_day_spent_settling_or_vacuuming_misses_no_target(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    missed: list = []
    hass.bus.async_listen(
        "homepool_alert",
        lambda e: missed.append(e.data["context"]) if e.data["type"] == "target_missed" else None,
    )
    entry = await setup_pool(hass)
    await set_mode(hass, "smart")
    await _to_settling(hass, freezer, entry)
    await advance(hass, freezer, 12 * 60 + 5)  # past midnight, now vacuuming
    assert treatment_state(hass, entry).attributes["phase"] == "vacuuming"
    assert entry.runtime_data.history[-1]["day"] == "2026-07-15"
    assert entry.runtime_data.history[-1]["elapsed"] < entry.runtime_data.history[-1]["target"]
    await advance(hass, freezer, 24 * 60)  # a whole day vacuuming
    assert entry.runtime_data.history[-1]["day"] == "2026-07-16"
    assert missed == []

    # The treatment over, a short day is a missed target again.
    coordinator = entry.runtime_data
    await press(hass, entry, "end_treatment")
    await coordinator.async_set_setting("maintenance_lock", True)
    await advance(hass, freezer, 24 * 60)
    # 17 July still began in vacuuming; 18 July is an ordinary day.
    assert coordinator.history[-1]["day"] == "2026-07-17"
    assert missed == []
    await advance(hass, freezer, 24 * 60)
    assert coordinator.history[-1]["day"] == "2026-07-18"
    assert len(missed) == 1


@pytest.mark.parametrize("kind", ["shock", "flocculant"])
async def test_homepool_pump_controls_are_refused_in_every_treatment_phase(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory, kind: str
) -> None:
    """M6: the treatment decides the pump in all its phases, not only vacuuming."""
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_mode(hass, "off")
    coordinator = entry.runtime_data

    async def refused(phase: str) -> None:
        assert treatment_state(hass, entry).attributes["phase"] == phase
        for domain, service, data in (
            ("switch", "turn_on", {"entity_id": entity(entry, "pump")}),
            ("switch", "turn_off", {"entity_id": entity(entry, "pump")}),
            ("homepool", "start_cycle", {"entity_id": entity(entry, "overall_status")}),
            ("homepool", "stop_cycle", {"entity_id": entity(entry, "overall_status")}),
        ):
            with pytest.raises(HomeAssistantError) as err:
                await hass.services.async_call(domain, service, data, blocking=True)
            assert err.value.translation_key == "pump_in_treatment"
        assert coordinator.cycle_until is None and coordinator.override is None

    await start(hass, entry, kind)
    if kind == "shock":
        await refused("filtering")
    else:
        await refused("mixing")
        await advance(hass, freezer, 121)
        await refused("settling")
    # Over, they work again.
    await press(hass, entry, "end_treatment")
    await hass.services.async_call(
        "homepool", "start_cycle", {"entity_id": entity(entry, "overall_status")}, blocking=True
    )
    assert coordinator.cycle_until is not None


async def test_high_free_chlorine_is_no_alert_during_or_after_a_shock(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """M7: a shock raises the chlorine on purpose; only the low side is judged."""
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await start(hass, entry, "shock")
    await coordinator.async_record_reading("free_chlorine", 10.0)
    assert "free_chlorine_out_of_range" not in coordinator.alerts
    await coordinator.async_record_reading("free_chlorine", 0.2)
    assert "free_chlorine_out_of_range" in coordinator.alerts  # too low still counts
    await press(hass, entry, "end_treatment")
    await coordinator.async_record_reading("free_chlorine", 8.0)
    assert coordinator.after_shock_since is not None
    assert "free_chlorine_out_of_range" not in coordinator.alerts
    # Back in range, the after-shock period is over: high is an alert again.
    await coordinator.async_record_reading("free_chlorine", 1.0)
    assert coordinator.after_shock_since is None
    await coordinator.async_record_reading("free_chlorine", 8.0)
    assert "free_chlorine_out_of_range" in coordinator.alerts
