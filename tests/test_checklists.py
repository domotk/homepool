"""The closing and opening checklists, and the passive-wintering rules around them."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.homepool.const import DOMAIN
from custom_components.homepool.pool.checklists import (
    CLOSING_STEPS,
    OPENING_STEPS,
    TREATMENT_CLARIFIER,
    TREATMENT_FLOCCULANT,
    TREATMENT_SHOCK,
    build,
)

from .helpers import PUMP, SwitchRouter, setup_pool
from .test_control import local, madrid, set_mode, state, tick  # noqa: F401
from .test_season import entity, next_day, set_season

SALT = {"salt"}
EVERYTHING = {"salt", "winter_product", "ph_probe"}


def ids(steps) -> list[str]:
    return [s.id for s in steps]


def step_ids(coordinator, list_id: str) -> list[str]:
    return [s["id"] for s in coordinator.checklists[list_id]["steps"]]


async def closing_proposed(hass, freezer, **options):
    """A pool whose season has just ended, with the closing list open."""
    freezer.move_to(local(2026, 9, 30, 21, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, **options)
    await tick(hass, freezer, 4 * 60)  # past midnight: winter is proposed
    return entry, entry.runtime_data


# ── pure ──


def test_lists_have_the_specified_steps() -> None:
    assert ids(CLOSING_STEPS) == [
        "closing.shock", "closing.cell", "closing.backwash",
        "closing.lower_level", "closing.plugs", "closing.winter_product",
    ]
    assert ids(OPENING_STEPS) == [
        "opening.remove_winter_product", "opening.backwash", "opening.measure",
        "opening.salt", "opening.reconnect_cell", "opening.calibrate_ph", "opening.shock",
    ]
    assert ids(TREATMENT_SHOCK) == [
        "treatment.brush", "treatment.ph", "treatment.dose",
        "treatment.algaecide", "treatment.measure", "treatment.backwash",
    ]
    assert ids(TREATMENT_CLARIFIER) == ["treatment.ph", "treatment.dose", "treatment.backwash"]
    assert ids(TREATMENT_FLOCCULANT) == [
        "treatment.ph", "treatment.dose", "treatment.vacuum",
        "treatment.backwash", "treatment.refill",
    ]


def test_build_filters_by_equipment() -> None:
    assert ids(build("closing", set())) == [
        "closing.shock", "closing.backwash", "closing.lower_level", "closing.plugs",
    ]
    assert "closing.cell" in ids(build("closing", SALT))
    assert "closing.winter_product" not in ids(build("closing", SALT))
    assert "closing.winter_product" in ids(build("closing", EVERYTHING))
    opening = ids(build("opening", set()))
    assert not {"opening.salt", "opening.reconnect_cell", "opening.calibrate_ph"} & set(opening)
    assert "opening.calibrate_ph" in ids(build("opening", {"ph_probe"}))
    assert ids(build("treatment", set(), "clarifier")) == ids(TREATMENT_CLARIFIER)


def test_pump_steps_come_before_passive_steps() -> None:
    steps = build("closing", EVERYTHING)
    last_pump = max(i for i, s in enumerate(steps) if s.needs_pump)
    first_passive = min(i for i, s in enumerate(steps) if s.only_passive)
    assert last_pump < first_passive


# ── closing ──


async def test_closing_is_created_with_the_proposal(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    entry, coordinator = await closing_proposed(hass, freezer)
    assert coordinator.season_proposal["to"] == "winter"
    # A salt pool without a winter product.
    assert step_ids(coordinator, "closing") == [
        "closing.shock", "closing.cell", "closing.backwash",
        "closing.lower_level", "closing.plugs",
    ]
    assert all(s["done"] is None for s in coordinator.checklists["closing"]["steps"])
    attrs = hass.states.get(entity(entry, "next_manual_task")).attributes
    shown = attrs["checklists"]["closing"]
    assert shown[0] == {
        "id": "closing.shock", "text": "Shock the water with the pH at 7.2–7.4.",
        "done": False, "done_at": None, "starts_treatment": "shock", "needs_pump": True,
    }
    # Every item says whether it offers a treatment and whether it needs the pump.
    cell = next(i for i in shown if i["id"] == "closing.cell")
    assert cell["starts_treatment"] is None and cell["needs_pump"] is False
    backwash = next(i for i in shown if i["id"] == "closing.backwash")
    assert backwash["starts_treatment"] is None and backwash["needs_pump"] is True
    # The list is kept across a reload.
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert step_ids(entry.runtime_data, "closing")[0] == "closing.shock"


async def test_closing_has_the_winter_product_step_when_there_is_one(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    _, coordinator = await closing_proposed(hass, freezer, winter_product_type="floater")
    assert step_ids(coordinator, "closing")[-1] == "closing.winter_product"


async def test_an_open_list_keeps_its_progress_when_proposed_again(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    _, coordinator = await closing_proposed(hass, freezer)
    await coordinator.async_complete_step("closing.shock")
    coordinator._open_season_checklist("winter")
    assert coordinator.checklists["closing"]["steps"][0]["done"] is not None


async def test_winter_active_prunes_passive_steps(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    entry, coordinator = await closing_proposed(hass, freezer)
    await set_season(hass, entry, "winter_active")
    assert step_ids(coordinator, "closing") == [
        "closing.shock", "closing.cell", "closing.backwash",
    ]


async def test_passive_with_pump_steps_open_warns(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    entry, coordinator = await closing_proposed(hass, freezer)
    await coordinator.async_complete_step("closing.shock")
    await set_season(hass, entry, "winter_passive")
    assert coordinator.season_state == "winter_passive"
    alert = coordinator.alerts["closing_needs_pump"]
    assert alert["severity"] == "warning"
    assert "no longer start" in alert["message"]
    # Doing the last pump step clears it.
    await coordinator.async_complete_step("closing.backwash")
    assert "closing_needs_pump" not in coordinator.alerts


async def test_closing_needs_pump_is_notified_once_across_reloads(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """Ruling 26: the alert stays while it holds, but it reaches the phone once."""
    from .test_winter import NOTIFY, _notified

    calls = await _notified(hass)
    entry, coordinator = await closing_proposed(
        hass, freezer, **{**NOTIFY, "notification_quiet_hours_start": None,
                          "notification_quiet_hours_end": None},
    )

    def sent() -> int:
        return len([c for c in calls if "no longer start" in c.data["message"]])

    await set_season(hass, entry, "winter_passive")
    assert "closing_needs_pump" in coordinator.alerts
    assert sent() == 1
    for _ in range(2):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        await tick(hass, freezer, 2)
        assert "closing_needs_pump" in entry.runtime_data.alerts
        assert sent() == 1
    # Once it no longer holds, the flag goes: a new occasion is notified again.
    coordinator = entry.runtime_data
    await coordinator.async_complete_step("closing.shock")
    await coordinator.async_complete_step("closing.backwash")
    assert "closing_needs_pump" not in coordinator.alerts
    assert not coordinator.closing_needs_pump_notified


async def test_passive_with_the_pump_steps_done_does_not_warn(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    entry, coordinator = await closing_proposed(hass, freezer)
    await coordinator.async_complete_step("closing.shock")
    await coordinator.async_complete_step("closing.backwash")
    await set_season(hass, entry, "winter_passive")
    assert "closing_needs_pump" not in coordinator.alerts


async def test_passive_clears_a_running_cycle_and_refuses_a_new_one(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await coordinator.async_start_cycle(60)
    assert coordinator.cycle_until is not None
    coordinator.override = {"state": True, "until": "2099-01-01T00:00:00+00:00"}

    await set_season(hass, entry, "winter_passive")
    assert coordinator.cycle_until is None
    assert coordinator.override is None

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "start_cycle", {"entity_id": entity(entry, "season_state")}, blocking=True
        )
    assert err.value.translation_key == "cycle_in_winter_passive"
    with pytest.raises(ServiceValidationError):
        await coordinator.async_start_cycle(10)
    assert coordinator.cycle_until is None

    # Out of passive wintering it works again.
    await set_season(hass, entry, "winter_active")
    await coordinator.async_start_cycle(10)
    assert coordinator.cycle_until is not None


# ── steps ──


async def test_step_completes_its_task(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    _, coordinator = await closing_proposed(hass, freezer)
    assert "backwash" not in coordinator.tasks
    await coordinator.async_complete_step("closing.backwash")
    assert coordinator.tasks["backwash"] == dt_util.utcnow().isoformat()
    assert coordinator.checklists["closing"]["steps"][2]["done"] is not None
    # Ticking it twice changes nothing.
    first = coordinator.checklists["closing"]["steps"][2]["done"]
    await coordinator.async_complete_step("closing.backwash")
    assert coordinator.checklists["closing"]["steps"][2]["done"] == first


async def test_an_unknown_step_is_refused(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    entry, coordinator = await closing_proposed(hass, freezer)
    target = {"entity_id": entity(entry, "season_state")}
    for step in ("closing.winter_product", "opening.backwash", "nonsense"):
        with pytest.raises(ServiceValidationError) as err:
            await hass.services.async_call(
                DOMAIN, "complete_step", {**target, "step": step}, blocking=True
            )
        assert err.value.translation_key == "step_not_open"


async def test_the_services_tick_and_dismiss(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    entry, coordinator = await closing_proposed(hass, freezer)
    target = {"entity_id": entity(entry, "season_state")}
    await hass.services.async_call(
        DOMAIN, "complete_step", {**target, "step": "closing.shock"}, blocking=True
    )
    shown = hass.states.get(entity(entry, "next_manual_task")).attributes["checklists"]
    assert shown["closing"][0]["done"] is True
    await hass.services.async_call(
        DOMAIN, "dismiss_checklist", {**target, "checklist": "closing"}, blocking=True
    )
    assert "closing" not in coordinator.checklists
    assert hass.states.get(entity(entry, "next_manual_task")).attributes["checklists"] == {}


async def test_a_finished_closing_list_is_no_longer_shown(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    entry, coordinator = await closing_proposed(hass, freezer)
    await set_season(hass, entry, "winter_active")
    for step in ("closing.shock", "closing.cell", "closing.backwash"):
        await coordinator.async_complete_step(step)
    # Kept, finished, until the next change of season.
    assert coordinator.checklists["closing"]["completed"]
    assert "closing" not in coordinator.checklist_view()


# ── opening ──


async def test_opening_done_proposes_swimming(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2027, 5, 20, 12, 0))
    SwitchRouter(hass)
    events = []
    hass.bus.async_listen("homepool_season_proposal", events.append)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await set_season(hass, entry, "winter_active")
    assert not coordinator.chlorinator_enabled
    await set_season(hass, entry, "opening")
    assert step_ids(coordinator, "opening") == [
        "opening.backwash", "opening.measure", "opening.salt",
        "opening.reconnect_cell", "opening.shock",
    ]
    steps = step_ids(coordinator, "opening")
    for step in steps[:3]:
        await coordinator.async_complete_step(step)
    assert not coordinator.chlorinator_enabled
    assert coordinator.season_proposal is None
    await coordinator.async_complete_step("opening.reconnect_cell")
    assert coordinator.chlorinator_enabled
    await coordinator.async_complete_step("opening.shock")

    assert "opening" not in coordinator.checklist_view()
    assert coordinator.season_proposal["to"] == "swimming"
    assert coordinator.season_proposal_shown == "swimming"
    assert hass.states.get(entity(entry, "season_state")).attributes["proposal"] == "swimming"
    assert coordinator.season_state == "opening"
    await hass.async_block_till_done()
    assert [e.data["to"] for e in events] == ["swimming"]

    # The calendar proposes nothing in this state, and must leave this alone.
    await next_day(hass, freezer, 3)
    assert coordinator.season_proposal["to"] == "swimming"

    await set_season(hass, entry, "swimming")
    assert coordinator.season_proposal is None


async def test_a_swimming_proposal_survives_a_midnight_with_no_calendar_proposal(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    # Before the season: the calendar has nothing to propose from opening.
    freezer.move_to(local(2027, 5, 20, 23, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await set_season(hass, entry, "opening")
    for step in step_ids(coordinator, "opening"):
        await coordinator.async_complete_step(step)
    assert coordinator.season_proposal["to"] == "swimming"
    await tick(hass, freezer, 2 * 60)  # past midnight
    assert coordinator.day.isoformat() == "2027-05-21"
    assert coordinator.season_proposal["to"] == "swimming"
    # Dismissed, it is not shown, and the next midnight drops it.
    await coordinator.async_dismiss_season_proposal()
    assert coordinator.season_proposal_shown is None
    await next_day(hass, freezer, 8)
    assert coordinator.season_proposal is None
    assert coordinator.season_proposal_shown is None


async def test_a_withdrawn_calendar_proposal_is_saved(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory, hass_storage
) -> None:
    _, coordinator = await closing_proposed(hass, freezer)
    assert coordinator.season_proposal["to"] == "winter"
    # The calendar has nothing to propose any more: the proposal goes, and is saved.
    saved: list[bool] = []
    original = coordinator._save
    coordinator._save = lambda: (saved.append(True), original())[1]
    await coordinator._async_season_proposal(local(2027, 7, 15, 0, 1))
    assert coordinator.season_proposal is None
    assert saved


async def test_an_unconfirmed_swimming_proposal_is_reminded_every_7_days(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2027, 7, 15, 12, 0))
    SwitchRouter(hass)
    events = []
    hass.bus.async_listen("homepool_season_proposal", events.append)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await set_season(hass, entry, "opening")
    for step in step_ids(coordinator, "opening"):
        await coordinator.async_complete_step(step)
    await hass.async_block_till_done()
    assert [e.data["to"] for e in events] == ["swimming"]
    await next_day(hass, freezer, 6)
    assert len(events) == 1
    await next_day(hass, freezer, 1)
    assert [e.data["to"] for e in events] == ["swimming", "swimming"]
    assert coordinator.season_proposal["to"] == "swimming"
    # Dismissed, it is not brought up again.
    await coordinator.async_dismiss_season_proposal()
    await next_day(hass, freezer, 8)
    assert len(events) == 2


async def test_entering_opening_drops_an_open_closing_list(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    entry, coordinator = await closing_proposed(hass, freezer)
    assert "closing" in coordinator.checklists
    await set_season(hass, entry, "winter_active")
    assert "closing" in coordinator.checklists
    await set_season(hass, entry, "opening")
    assert "closing" not in coordinator.checklists
    assert "opening" in coordinator.checklists


async def test_entering_winter_drops_an_open_opening_list(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2027, 7, 15, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await set_season(hass, entry, "opening")
    assert "opening" in coordinator.checklists
    await set_season(hass, entry, "winter_passive")
    assert "opening" not in coordinator.checklists
    assert "closing" in coordinator.checklists


async def test_finishing_the_opening_list_while_swimming_proposes_nothing(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """Swimming is proposed only from the opening state; a list ticked after
    the owner confirmed swimming must not block the end of the season."""
    freezer.move_to(local(2026, 5, 20, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, chlorination_type="tablets")
    coordinator = entry.runtime_data
    await set_season(hass, entry, "winter_active")
    await set_season(hass, entry, "opening")
    await set_season(hass, entry, "swimming")
    for step in step_ids(coordinator, "opening"):
        await coordinator.async_complete_step(step)
    assert "opening" not in coordinator.checklist_view()
    assert coordinator.season_proposal is None

    freezer.move_to(local(2026, 9, 30, 21, 0))
    await tick(hass, freezer, 4 * 60)  # past midnight: the season is over
    assert coordinator.season_proposal["to"] == "winter"
    assert coordinator.season_proposal_shown == "winter"
    assert "closing" in coordinator.checklists


async def test_finishing_the_opening_list_while_wintering_keeps_the_opening_proposal(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2027, 5, 17, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    assert coordinator.season_state == "winter_active"
    await next_day(hass, freezer)
    assert coordinator.season_proposal["to"] == "opening"
    for step in step_ids(coordinator, "opening"):
        await coordinator.async_complete_step(step)
    assert coordinator.season_proposal["to"] == "opening"
    assert coordinator.season_proposal_shown == "opening"


@pytest.mark.parametrize("dismissed", [True, False])
async def test_a_stale_swimming_proposal_does_not_block_the_calendar(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory, dismissed: bool
) -> None:
    """A swimming proposal left from before (dismissed, or for the state the
    pool is already in) is dropped and the calendar has its say."""
    freezer.move_to(local(2026, 9, 30, 21, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    assert coordinator.season_state == "swimming"
    coordinator.season_proposal = {
        "to": "swimming",
        "since": local(2026, 6, 1, 12, 0).isoformat(),
        "reminded": local(2026, 6, 1, 12, 0).isoformat(),
        "dismissed_for": "swimming" if dismissed else None,
    }
    await tick(hass, freezer, 4 * 60)
    assert coordinator.season_proposal["to"] == "winter"
    assert coordinator.season_proposal_shown == "winter"
    assert "closing" in coordinator.checklists


async def test_dismissing_the_winter_proposal_drops_the_closing_list(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    _, coordinator = await closing_proposed(hass, freezer)
    assert "closing" in coordinator.checklists
    await coordinator.async_dismiss_season_proposal()
    assert "closing" not in coordinator.checklists


async def test_dismissing_the_opening_proposal_drops_the_opening_list(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2027, 5, 17, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await next_day(hass, freezer)
    assert coordinator.season_proposal["to"] == "opening"
    assert "opening" in coordinator.checklists
    await hass.services.async_call(
        DOMAIN, "dismiss_season_proposal",
        {"entity_id": entity(entry, "season_state")}, blocking=True,
    )
    assert "opening" not in coordinator.checklists


# ── review round 2: a list's lifetime ──


def shown(hass, entry) -> dict:
    return hass.states.get(entity(entry, "next_manual_task")).attributes["checklists"]


async def test_a_closing_list_withdrawn_by_the_calendar_goes_with_its_proposal(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """Never confirmed nor dismissed: the calendar withdraws the winter
    proposal in the spring, and the list goes with it, so next autumn starts
    a new one rather than last year's ticks."""
    _, coordinator = await closing_proposed(hass, freezer)
    await coordinator.async_complete_step("closing.shock")
    await coordinator._async_season_proposal(local(2027, 5, 18, 0, 1))
    assert coordinator.season_proposal is None
    assert "closing" not in coordinator.checklists
    await coordinator._async_season_proposal(local(2027, 9, 30, 0, 1))
    assert coordinator.season_proposal["to"] == "winter"
    assert all(s["done"] is None for s in coordinator.checklists["closing"]["steps"])


async def test_an_opening_list_withdrawn_by_the_calendar_goes_with_its_proposal(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2027, 5, 17, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await next_day(hass, freezer)
    assert coordinator.season_proposal["to"] == "opening"
    await coordinator.async_complete_step("opening.backwash")
    # Still wintering when the season is over: the proposal and its list go.
    await coordinator._async_season_proposal(local(2027, 10, 15, 0, 1))
    assert coordinator.season_proposal is None
    assert "opening" not in coordinator.checklists


async def test_leaving_winter_straight_for_swimming_drops_the_closing_list(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    entry, coordinator = await closing_proposed(hass, freezer)
    await set_season(hass, entry, "winter_active")
    await coordinator.async_complete_step("closing.shock")
    await set_season(hass, entry, "swimming")
    assert "closing" not in coordinator.checklists


async def test_a_closing_list_finished_before_winter_is_confirmed_stays_done(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """The natural order: every closing step done, then passive wintering
    confirmed. No blank list, no warning for work already done."""
    entry, coordinator = await closing_proposed(hass, freezer)
    began = coordinator.checklists["closing"]["created"]
    for step in step_ids(coordinator, "closing"):
        await coordinator.async_complete_step(step)
    assert "closing" not in shown(hass, entry)
    await set_season(hass, entry, "winter_passive")
    assert "closing_needs_pump" not in coordinator.alerts
    assert "closing" not in shown(hass, entry)
    assert all(s["done"] for s in coordinator.checklists["closing"]["steps"])
    assert coordinator.winter_top_up_from.isoformat() == began
    # A finished list is not open: its steps cannot be ticked again.
    assert not coordinator.has_open_step("closing.shock")
    # Gone at the next change of season.
    await set_season(hass, entry, "opening")
    assert "closing" not in coordinator.checklists


async def test_an_opening_list_finished_while_wintering_proposes_swimming_on_opening(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2027, 5, 17, 12, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await next_day(hass, freezer)
    assert coordinator.season_proposal["to"] == "opening"
    for step in step_ids(coordinator, "opening"):
        await coordinator.async_complete_step(step)
    await set_season(hass, entry, "opening")
    assert "opening" not in shown(hass, entry)
    assert coordinator.season_proposal["to"] == "swimming"
    assert coordinator.season_proposal_shown == "swimming"
    await set_season(hass, entry, "swimming")
    assert "opening" not in coordinator.checklists


async def test_confirming_the_state_the_pool_is_in_leaves_the_proposal(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    events = []
    hass.bus.async_listen("homepool_season_proposal", events.append)
    entry, coordinator = await closing_proposed(hass, freezer)
    await hass.async_block_till_done()
    assert len(events) == 1
    proposal = dict(coordinator.season_proposal)
    await set_season(hass, entry, "swimming")
    assert coordinator.season_proposal == proposal
    assert "closing" in coordinator.checklists
    await next_day(hass, freezer)
    await set_season(hass, entry, "swimming")
    await next_day(hass, freezer)
    assert len(events) == 1


# ── review round 2: out of the opening state ──


def test_the_calendar_proposes_a_way_out_of_opening() -> None:
    from datetime import date

    from custom_components.homepool.pool.season import season_proposal

    summer = [6, 7, 8, 9]
    # Before the season: nothing yet, the opening list proposes swimming.
    assert season_proposal(date(2027, 5, 20), summer, "opening") is None
    # The season has started: swimming.
    assert season_proposal(date(2027, 6, 1), summer, "opening") == "swimming"
    assert season_proposal(date(2027, 9, 30), summer, "opening") == "swimming"
    # Past it: winter, as from swimming.
    assert season_proposal(date(2027, 10, 6), summer, "opening") == "winter"
    # An opening begun early in spring takes weeks: it is left alone.
    assert season_proposal(date(2027, 3, 1), summer, "opening") is None


async def test_an_opening_left_unconfirmed_is_proposed_swimming_then_winter(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2027, 5, 20, 12, 0))
    SwitchRouter(hass)
    events = []
    hass.bus.async_listen("homepool_season_proposal", events.append)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    await set_season(hass, entry, "winter_active")
    await set_season(hass, entry, "opening")
    await coordinator.async_dismiss_checklist("opening")
    await next_day(hass, freezer, 12)  # June 1
    assert coordinator.season_proposal_shown == "swimming"
    await hass.async_block_till_done()
    assert [e.data["to"] for e in events] == ["swimming"]
    # Dismissed, it stays dismissed while the calendar says the same.
    await coordinator.async_dismiss_season_proposal()
    await next_day(hass, freezer, 10)
    assert coordinator.season_proposal_shown is None
    assert len(events) == 1
    # Past the season: winter.
    freezer.move_to(local(2027, 10, 5, 23, 0))
    await tick(hass, freezer, 2 * 60)
    assert coordinator.season_proposal_shown == "winter"
    assert "closing" in coordinator.checklists


async def test_a_backwash_step_cleans_a_cartridge(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    """A cartridge filter has no backwash task: the step is its cleaning."""
    entry, coordinator = await closing_proposed(hass, freezer, filter_type="cartridge")
    await coordinator.async_complete_step("closing.backwash")
    assert coordinator.tasks.get("filter_cleaned")
    assert "backwash" not in coordinator.tasks
    row = next(t for t in coordinator.task_status() if t["task"] == "filter_cleaning")
    assert row["last_done"] is not None and not row["overdue"]
