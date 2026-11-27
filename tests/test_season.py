"""The season state: proposed by the calendar, confirmed by the owner.

HomePool never changes the state on its own. ``winter_passive`` keeps the pump
off whatever asks for it, except hands-off, which is above it.
"""

from __future__ import annotations

from datetime import date, timedelta
from itertools import product

from freezegun.api import FrozenDateTimeFactory
import pytest
import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.homepool.const import DOMAIN
from custom_components.homepool.pool.season import (
    WINTER_STATES,
    SeasonState,
    default_swimming_months,
    initial_state,
    season_proposal,
)

from .helpers import BASE, CHLORINATOR, HANDS_OFF, PUMP, SwitchRouter, setup_helpers, setup_pool
from .test_control import local, madrid, set_mode, state, tick  # noqa: F401
from .test_winter import NOTIFY, _notified

SUMMER = [6, 7, 8, 9]


def entity(entry, key: str) -> str:
    """The real entity id of one of the pool's own entities."""
    return entry.runtime_data.own_entities()[key]


async def next_day(hass: HomeAssistant, freezer: FrozenDateTimeFactory, days: int = 1) -> None:
    """Jump whole days at once: a minute-by-minute week is too slow."""
    for _ in range(days):
        freezer.tick(timedelta(days=1))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()


async def set_season(hass: HomeAssistant, entry, value: str) -> None:
    await hass.services.async_call(
        DOMAIN, "set_season_state",
        {"entity_id": entity(entry, "season_state"), "state": value}, blocking=True,
    )
    await hass.async_block_till_done()


# ── pure ──


def test_proposal_dates() -> None:
    assert season_proposal(date(2026, 9, 30), SUMMER, "swimming") == "winter"
    assert season_proposal(date(2026, 9, 29), SUMMER, "swimming") is None
    assert season_proposal(date(2027, 5, 18), SUMMER, "winter_active") == "opening"
    assert season_proposal(date(2027, 5, 17), SUMMER, "winter_active") is None


def test_proposal_edges() -> None:
    # Out of season and still swimming: winter is proposed.
    assert season_proposal(date(2026, 10, 15), SUMMER, "swimming") == "winter"
    # Opened early, in the fortnight before the season: not sent back to winter.
    assert season_proposal(date(2027, 5, 25), SUMMER, "swimming") is None
    assert season_proposal(date(2027, 5, 17), SUMMER, "swimming") == "winter"
    # Already wintering: nothing to propose until the opening window.
    assert season_proposal(date(2026, 10, 15), SUMMER, "winter_passive") is None
    assert season_proposal(date(2027, 5, 31), SUMMER, "winter_passive") == "opening"
    # Still wintering once the season has started: opening is still proposed,
    # until the run ends.
    assert season_proposal(date(2027, 6, 1), SUMMER, "winter_active") == "opening"
    assert season_proposal(date(2027, 9, 30), SUMMER, "winter_active") == "opening"
    assert season_proposal(date(2027, 10, 1), SUMMER, "winter_active") is None
    # Opening, in the season: swimming is proposed (see test_checklists for more).
    assert season_proposal(date(2026, 9, 30), SUMMER, "opening") == "swimming"
    # A run across the new year, south of the equator.
    south = [12, 1, 2, 3]
    assert season_proposal(date(2027, 3, 31), south, "swimming") == "winter"
    assert season_proposal(date(2026, 12, 31), south, "swimming") is None
    assert season_proposal(date(2026, 11, 17), south, "winter_active") == "opening"
    assert season_proposal(date(2026, 11, 16), south, "winter_active") is None
    # Two runs: each ends and each opens.
    split = [1, 2, 7, 8]
    assert season_proposal(date(2026, 2, 28), split, "swimming") == "winter"
    assert season_proposal(date(2026, 6, 20), split, "winter_active") == "opening"
    # The whole year, or no months at all: no change to propose.
    for months in (list(range(1, 13)), []):
        for day in (date(2026, 12, 31), date(2026, 6, 1)):
            for st in SeasonState:
                assert season_proposal(day, months, st) is None


def test_default_swimming_months() -> None:
    assert default_swimming_months([5, 6, 7], True, 40.0) == [5, 6, 7]
    assert default_swimming_months([5, 6, 7], False, 40.0) == [6, 7, 8, 9]
    assert default_swimming_months(None, True, 40.0) == [6, 7, 8, 9]
    assert default_swimming_months([], True, -33.0) == [12, 1, 2, 3]


def test_initial_state() -> None:
    assert initial_state(True, True, True) == SeasonState.SWIMMING
    assert initial_state(True, True, False) == SeasonState.WINTER_ACTIVE
    assert initial_state(False, False, False) == SeasonState.WINTER_ACTIVE
    # In season without salt: the chlorinator switch does not matter.
    assert initial_state(True, False, False) == SeasonState.SWIMMING
    for combo in product((True, False), repeat=3):
        assert initial_state(*combo) != SeasonState.WINTER_PASSIVE
    assert set(WINTER_STATES) == {SeasonState.WINTER_ACTIVE, SeasonState.WINTER_PASSIVE}


# ── upgrading from 0.1.4 ──


async def test_upgrade_from_014_store_in_season_with_cell_off(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory, hass_storage
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    hass_storage[f"{DOMAIN}.upg"] = {
        "version": 1, "key": f"{DOMAIN}.upg",
        "data": {
            "day": "2026-07-15",
            "tasks_since": local(2026, 7, 1, 10, 0).isoformat(),
            "settings": {"chlorinator_enabled": False, "mode": "smart"},
        },
    }
    SwitchRouter(hass)
    calls = await _notified(hass)
    await setup_helpers(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Pool", data={**BASE, **NOTIFY}, version=1, entry_id="upg"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert state(hass, entity(entry, "season_state")) == "winter_active"
    assert entry.runtime_data.settings["season_state"] == "winter_active"
    assert state(hass, PUMP) == "on"
    assert state(hass, "sensor.pool_pump_control") == "mode"
    told = [c for c in calls if "season state" in c.data["message"]]
    assert len(told) == 1
    assert "winter" in told[0].data["message"]

    # Once only: a reload does not say it again.
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await tick(hass, freezer, 2)
    assert len([c for c in calls if "season state" in c.data["message"]]) == 1


async def test_the_upgrade_reminder_waits_for_home_assistant_to_run(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory, hass_storage
) -> None:
    from homeassistant.core import CoreState

    freezer.move_to(local(2026, 7, 15, 12, 0))
    hass_storage[f"{DOMAIN}.upg"] = {
        "version": 1, "key": f"{DOMAIN}.upg",
        "data": {"day": "2026-07-15", "settings": {"chlorinator_enabled": False}},
    }
    SwitchRouter(hass)
    calls = await _notified(hass)
    await setup_helpers(hass)
    hass.set_state(CoreState.starting)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Pool", data={**BASE, **NOTIFY}, version=1, entry_id="upg"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # Loaded and evaluated while starting: queued, not sent.
    assert not [c for c in calls if "season state" in c.data["message"]]
    assert any(
        "season state" in r["message"] for r in entry.runtime_data.pending_reminders
    )
    hass.set_state(CoreState.running)
    await tick(hass, freezer, 1)  # the first evaluation with it running
    assert len([c for c in calls if "season state" in c.data["message"]]) == 1
    assert not entry.runtime_data.pending_reminders


async def test_a_new_install_is_not_told_about_the_season_state(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    calls = await _notified(hass)
    entry = await setup_pool(hass, **NOTIFY)
    assert state(hass, entity(entry, "season_state")) == "swimming"
    assert not [c for c in calls if "season state" in c.data["message"]]


# ── proposals ──


async def test_end_of_season_proposes_and_waits(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 9, 30, 21, 0))
    SwitchRouter(hass)
    calls = await _notified(hass)
    events = []
    hass.bus.async_listen("homepool_season_proposal", events.append)
    season_end = []
    hass.bus.async_listen("homepool_chlorinator_season_end", season_end.append)
    entry = await setup_pool(hass, **NOTIFY)
    coordinator = entry.runtime_data
    assert coordinator.season_state == "swimming"

    await tick(hass, freezer, 4 * 60)  # past midnight
    assert [e.data["to"] for e in events] == ["winter"]
    assert events[0].data["entry_id"] == entry.entry_id
    assert coordinator.season_state == "swimming"
    assert coordinator.season_proposal["to"] == "winter"
    assert hass.states.get(entity(entry, "season_state")).attributes["proposal"] == "winter"
    # The old event is still part of the contract.
    assert len(season_end) == 1
    # The reminder waits for the quiet hours to end.
    assert not any("winter" in c.data["message"].lower() for c in calls)
    await tick(hass, freezer, 8 * 60)  # 09:00
    assert any("winter" in c.data["message"].lower() for c in calls)

    await next_day(hass, freezer, 5)
    assert len(events) == 1
    await next_day(hass, freezer, 2)  # a week since the first
    assert len(events) == 2
    assert coordinator.season_state == "swimming"

    await hass.services.async_call(
        DOMAIN, "dismiss_season_proposal",
        {"entity_id": entity(entry, "season_state")}, blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity(entry, "season_state")).attributes["proposal"] is None
    await next_day(hass, freezer, 15)
    assert len(events) == 2
    assert coordinator.season_state == "swimming"


async def test_opening_is_proposed_before_the_season(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2027, 5, 17, 12, 0))
    SwitchRouter(hass)
    events = []
    hass.bus.async_listen("homepool_season_proposal", events.append)
    entry = await setup_pool(hass)
    assert entry.runtime_data.season_state == "winter_active"
    await next_day(hass, freezer)
    assert [e.data["to"] for e in events] == ["opening"]
    # Confirming clears the proposal, and does not touch the cell.
    enabled = entry.runtime_data.chlorinator_enabled
    await set_season(hass, entry, "opening")
    assert entry.runtime_data.season_proposal is None
    assert entry.runtime_data.chlorinator_enabled == enabled


async def test_an_unconfirmed_opening_keeps_reminding_into_the_season(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2027, 5, 31, 12, 0))
    SwitchRouter(hass)
    events = []
    hass.bus.async_listen("homepool_season_proposal", events.append)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    assert coordinator.season_state == "winter_active"
    await next_day(hass, freezer)  # the season's first day
    assert [e.data["to"] for e in events] == ["opening"]
    assert coordinator.season_proposal_shown == "opening"
    await next_day(hass, freezer, 6)
    assert len(events) == 1
    await next_day(hass, freezer)  # a week later
    assert [e.data["to"] for e in events] == ["opening", "opening"]
    assert coordinator.season_state == "winter_active"


async def test_no_proposals_without_auto_toggle(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 9, 30, 21, 0))
    SwitchRouter(hass)
    events = []
    hass.bus.async_listen("homepool_season_proposal", events.append)
    entry = await setup_pool(hass, chlorinator_auto_toggle=False)
    coordinator = entry.runtime_data
    assert coordinator.chlorinator_enabled
    await tick(hass, freezer, 4 * 60)
    await next_day(hass, freezer, 8)
    assert events == []
    assert coordinator.season_proposal is None
    # It no longer switches the cell with the calendar either.
    assert coordinator.chlorinator_enabled


async def test_a_dismissed_proposal_comes_back_with_the_next_season(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 9, 30, 21, 0))
    SwitchRouter(hass)
    events = []
    hass.bus.async_listen("homepool_season_proposal", events.append)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await tick(hass, freezer, 4 * 60)
    assert len(events) == 1
    await coordinator.async_dismiss_season_proposal()
    assert coordinator.season_proposal["dismissed_for"] == "winter"
    # Still swimming next summer: the calendar has nothing to propose, which
    # re-arms it; at the end of that season it proposes winter again.
    await coordinator._async_season_proposal(local(2027, 7, 15, 0, 1))
    assert coordinator.season_proposal is None
    await coordinator._async_season_proposal(local(2027, 9, 30, 0, 1))
    await hass.async_block_till_done()
    assert len(events) == 2
    assert coordinator.season_proposal_shown == "winter"


async def test_the_calendar_no_longer_switches_the_cell(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 9, 30, 21, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await tick(hass, freezer, 4 * 60)
    assert entry.runtime_data.season_proposal["to"] == "winter"
    assert entry.runtime_data.chlorinator_enabled


# ── confirming ──


async def test_confirming_winter_active_turns_the_cell_off(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, chlorinator_switch=CHLORINATOR)
    coordinator = entry.runtime_data
    cell = entity(entry, "salt_chlorinator_enabled")
    await coordinator.async_record_reading("salt", 2.8)
    await tick(hass, freezer, 1)
    assert state(hass, cell) == "on"
    assert "salt_low" in coordinator.alerts

    changed = []
    hass.bus.async_listen("homepool_season_state_changed", changed.append)
    await set_season(hass, entry, "winter_active")
    await tick(hass, freezer, 1)
    assert state(hass, cell) == "off"
    assert "salt_low" not in coordinator.alerts
    assert len(changed) == 1
    assert changed[0].data == {
        "entry_id": entry.entry_id, "pool": "Pool", "old": "swimming", "new": "winter_active",
    }
    assert state(hass, entity(entry, "season_state")) == "winter_active"

    # Back to swimming turns it on again; the select does the same as the service.
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": entity(entry, "season_state"), "option": "swimming"}, blocking=True,
    )
    await hass.async_block_till_done()
    assert state(hass, cell) == "on"
    assert len(changed) == 2


async def test_the_season_state_decides_the_cell_outside_its_months(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """Ruling 24: swimming on 3 October, past the chlorinator's months, the
    cell still runs with flow and counts in the target; in winter it is off."""
    freezer.move_to(local(2026, 10, 3, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, chlorinator_switch=CHLORINATOR)
    coordinator = entry.runtime_data
    await set_season(hass, entry, "swimming")
    assert coordinator.chlorinator_enabled
    await coordinator.async_start_cycle(120)
    await tick(hass, freezer, 3)  # past the flow delay
    assert state(hass, PUMP) == "on"
    assert state(hass, CHLORINATOR) == "on"
    assert (coordinator.target.get("target_chlorine_minutes") or 0) > 0
    assert "chlorinator_not_producing" not in coordinator.alerts
    assert coordinator.chlorination_mode == "salt"

    await set_season(hass, entry, "winter_active")
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "on"  # the cycle still runs
    assert state(hass, CHLORINATOR) == "off"
    assert not coordinator.target.get("target_chlorine_minutes")


async def test_in_winter_the_cell_stays_off_even_in_its_months_and_switched_on(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """Ruling 24, winter side: in July, a chlorinator month, with the cell
    switched back on by hand, active wintering still keeps it off."""
    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, chlorinator_switch=CHLORINATOR)
    coordinator = entry.runtime_data
    await set_season(hass, entry, "winter_active")
    await coordinator.async_set_setting("chlorinator_enabled", True)
    await coordinator.async_record_reading("salt", 2.8)
    await coordinator.async_start_cycle(120)
    await tick(hass, freezer, 3)
    assert coordinator.chlorinator_enabled
    assert state(hass, PUMP) == "on"
    assert state(hass, CHLORINATOR) == "off"
    assert not coordinator.target.get("target_chlorine_minutes")
    assert coordinator.chlorination_mode != "salt"
    assert "salt_low" not in coordinator.alerts


async def test_in_opening_the_cell_counts_once_it_is_in_use(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2027, 5, 20, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, chlorinator_switch=CHLORINATOR)
    coordinator = entry.runtime_data
    await set_season(hass, entry, "opening")
    await coordinator.async_record_reading("salt", 2.8)
    await coordinator.async_start_cycle(120)
    await tick(hass, freezer, 3)
    assert not coordinator.chlorinator_enabled
    assert state(hass, CHLORINATOR) == "off"
    assert "salt_low" not in coordinator.alerts

    await coordinator.async_complete_step("opening.reconnect_cell")
    await tick(hass, freezer, 1)
    assert state(hass, CHLORINATOR) == "on"
    assert (coordinator.target.get("target_chlorine_minutes") or 0) > 0
    assert "salt_low" in coordinator.alerts


async def test_confirming_the_same_state_again_keeps_the_cell_as_set_by_hand(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    assert coordinator.season_state == "swimming"
    await coordinator.async_set_setting("chlorinator_enabled", False)
    await set_season(hass, entry, "swimming")
    assert not coordinator.chlorinator_enabled
    await set_season(hass, entry, "winter_active")
    assert not coordinator.chlorinator_enabled
    await coordinator.async_set_setting("chlorinator_enabled", True)
    await set_season(hass, entry, "winter_active")
    assert coordinator.chlorinator_enabled
    # A real change still sets it.
    await set_season(hass, entry, "winter_passive")
    assert not coordinator.chlorinator_enabled
    await set_season(hass, entry, "swimming")
    assert coordinator.chlorinator_enabled


async def test_a_bad_season_state_is_refused(hass: HomeAssistant) -> None:
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    with pytest.raises(vol.Invalid):  # the schema refuses it
        await set_season(hass, entry, "autumn")


# ── passive wintering ──


async def test_winter_passive_keeps_the_pump_off(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, hands_off_entity=HANDS_OFF)
    await set_mode(hass, "smart")
    assert state(hass, PUMP) == "on"

    await set_season(hass, entry, "winter_passive")
    assert state(hass, PUMP) == "off"
    assert state(hass, "sensor.pool_pump_control") == "winter_passive"
    attrs = hass.states.get("sensor.pool_pump_control").attributes
    assert attrs["reason_key"] == "winter_passive"

    # Switched on by a person: off again within one evaluation.
    user = await hass.auth.async_create_user("Owner")
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": PUMP}, blocking=True,
        context=Context(user_id=user.id),
    )
    # Let the change ask for its evaluation before the clock moves, as it
    # would in a running Home Assistant.
    await hass.async_block_till_done()
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "off"

    # A manual cycle is refused, so it cannot run it either.
    with pytest.raises(ServiceValidationError):
        await entry.runtime_data.async_start_cycle(30)
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "off"

    # Hands-off is above it: the pump is left alone.
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": HANDS_OFF}, blocking=True
    )
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": PUMP}, blocking=True,
        context=Context(user_id=user.id),
    )
    await hass.async_block_till_done()
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "on"
    assert state(hass, "sensor.pool_pump_control") == "hands_off"


async def test_winter_passive_ignores_freeze_and_ph(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 1, 15, 4, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.water", "1")
    hass.states.async_set("sensor.ph", "7.9")
    entry = await setup_pool(
        hass, water_temperature_sensor="sensor.water", ph_sensor="sensor.ph", has_ph_dosing=True
    )
    coordinator = entry.runtime_data
    await set_mode(hass, "smart")
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "on"  # freeze protection, before passive
    assert "kept running" in coordinator.alerts["freeze_protection"]["message"]

    events = []
    hass.bus.async_listen("homepool_alert", events.append)
    await set_season(hass, entry, "winter_passive")
    await tick(hass, freezer, 30)
    assert state(hass, PUMP) == "off"
    assert state(hass, "sensor.pool_pump_control") == "winter_passive"
    assert "gizmos" in coordinator.alerts["freeze_protection"]["message"]
    assert not coordinator.ph_correction_active
    assert state(hass, "binary_sensor.pool_ph_correction") == "off"
    # Raised again with the new wording, once.
    assert [e.data["type"] for e in events].count("freeze_protection") == 1

    # A pH window asked for by hand does not run it either.
    await coordinator.async_force_ph_window(30)
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "off"


# ── services ──


async def test_completing_a_task_the_pool_does_not_have_is_refused(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)  # no pH probe: no calibration task
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "complete_task",
            {"entity_id": "sensor.pool_status", "task": "ph_calibration"}, blocking=True,
        )
    assert err.value.translation_key == "task_not_in_pool"
    assert "ph_calibrated" not in entry.runtime_data.tasks


async def test_chlorination_mode_in_winter_with_a_product(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, winter_product_type="floater")
    mode = entity(entry, "chlorination_mode")
    assert state(hass, mode) == "salt"
    await set_season(hass, entry, "winter_active")
    assert state(hass, mode) == "winter_product"


def test_an_early_opening_is_not_sent_back_to_winter() -> None:
    from custom_components.homepool.pool.season import season_proposal

    months = [6, 7, 8, 9]
    # Opened on 1 April for a June season: nothing, all spring.
    assert season_proposal(date(2027, 4, 1), months, "opening") is None
    assert season_proposal(date(2027, 2, 15), months, "opening") is None
    # Left in opening through the season: winter once it is over.
    assert season_proposal(date(2026, 10, 6), months, "opening") == "winter"
    assert season_proposal(date(2026, 12, 20), months, "opening") == "winter"
    # The southern hemisphere, across the new year.
    south = [12, 1, 2, 3]
    assert season_proposal(date(2026, 10, 1), south, "opening") is None
    assert season_proposal(date(2026, 5, 1), south, "opening") == "winter"


async def test_a_hand_switch_in_passive_wintering_is_not_acted_on_later(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """The third real install (0.2.0): switched on by hand in passive wintering,
    off again at once, and then on for two hours on leaving it."""
    freezer.move_to(local(2026, 11, 27, 19, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_mode(hass, "off")
    await set_season(hass, entry, "winter_active")
    assert state(hass, PUMP) == "off"

    await set_season(hass, entry, "winter_passive")
    user = await hass.auth.async_create_user("Owner")
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": PUMP}, blocking=True,
        context=Context(user_id=user.id),
    )
    await hass.async_block_till_done()
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "off"
    assert entry.runtime_data.override is None

    await set_season(hass, entry, "winter_active")
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "off"
    attrs = hass.states.get("sensor.pool_pump_control").attributes
    assert attrs["reason_key"] != "manual_override_on"


async def test_leaving_passive_wintering_drops_a_hold_left_from_before(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """However a hold got there, none outlives passive wintering."""
    freezer.move_to(local(2026, 11, 27, 19, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    await set_mode(hass, "off")
    await set_season(hass, entry, "winter_passive")
    coordinator = entry.runtime_data
    coordinator.override = {
        "state": True,
        "until": (dt_util.utcnow() + timedelta(hours=2)).isoformat(),
        "by": "user",
        "name": None,
    }
    await set_season(hass, entry, "winter_active")
    assert coordinator.override is None
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "off"


async def test_a_season_change_does_not_lower_the_days_target(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """During a day the target only goes up (246 fell to 232 on the third
    install); only recalculate_schedule takes it down."""
    freezer.move_to(local(2026, 11, 27, 18, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    held = coordinator.target_minutes + 60
    coordinator.target = {**coordinator.target, "target_minutes": held}

    await set_season(hass, entry, "winter_passive")
    assert coordinator.target_minutes == held
    assert coordinator.target["held_at_previous"] is True

    await coordinator.async_recalculate()
    assert coordinator.target_minutes < held
