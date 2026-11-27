"""The task table: intervals in days and in pump hours, paused states."""

from __future__ import annotations

from datetime import date, datetime

from freezegun.api import FrozenDateTimeFactory

from homeassistant.core import HomeAssistant

from custom_components.homepool.pool.tasks import TASKS, TASKS_BY_KEY, default_days, task_state

from .helpers import PUMP, SwitchRouter, setup_pool
from .test_control import local, madrid, state, tick  # noqa: F401


def _state(key, *, season_state="swimming", today=date(2026, 7, 1), last_done=None,
           counted_from=None, pump_seconds_since=0.0):
    defn = TASKS_BY_KEY[key]
    return task_state(
        defn,
        last_done=last_done,
        counted_from=counted_from,
        today=today,
        season_state=season_state,
        pump_seconds_since=pump_seconds_since,
        days=default_days(defn, season_state),
        pump_hours=defn.pump_hours,
    )


def test_backwash_counts_days_in_swimming() -> None:
    done = datetime(2026, 7, 1, 10, 0)
    on_14th = _state("backwash", last_done=done, today=date(2026, 7, 14))
    assert on_14th.due == date(2026, 7, 15)
    assert not on_14th.overdue
    assert _state("backwash", last_done=done, today=date(2026, 7, 15)).overdue


def test_backwash_counts_pump_hours_in_winter_active() -> None:
    done = datetime(2026, 1, 1, 10, 0)
    kw = {"season_state": "winter_active", "last_done": done, "today": date(2026, 1, 30)}
    below = _state("backwash", pump_seconds_since=111 * 3600, **kw)
    assert not below.overdue
    assert below.due is None
    assert below.interval_pump_hours == 112
    assert below.pump_hours_since == 111
    assert _state("backwash", pump_seconds_since=112 * 3600, **kw).overdue


def test_tasks_pause_in_winter_passive() -> None:
    for defn in TASKS:
        s = _state(
            defn.key,
            season_state="winter_passive",
            last_done=datetime(2020, 1, 1),
            pump_seconds_since=10_000 * 3600,
        )
        if defn.key == "winter_product":
            assert not s.paused
            assert s.overdue
        else:
            assert s.paused, defn.key
            assert not s.overdue, defn.key
            assert s.due is None


def test_never_done_counts_from_counted_from() -> None:
    since = datetime(2026, 6, 20, 9, 0)
    s = _state("backwash", counted_from=since, today=date(2026, 7, 3))
    assert s.last_done is None
    assert s.counted_from == since
    assert s.due == date(2026, 7, 4)
    assert not s.overdue
    assert _state("backwash", counted_from=since, today=date(2026, 7, 4)).overdue


def test_water_test_is_every_14_days_in_winter_active() -> None:
    done = datetime(2026, 1, 1)
    s = _state("water_test", season_state="winter_active", last_done=done, today=date(2026, 1, 8))
    assert s.due == date(2026, 1, 15)
    assert not s.overdue


async def test_existing_ph_calibration_interval_is_kept(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(
        hass, ph_sensor="sensor.ph", ph_calibration_interval_days=60
    )
    rows = {t["task"]: t for t in entry.runtime_data.task_status()}
    assert rows["ph_calibration"]["interval_days"] == 60


async def test_a_new_install_calibrates_every_180_days(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, ph_sensor="sensor.ph")
    rows = {t["task"]: t for t in entry.runtime_data.task_status()}
    assert rows["ph_calibration"]["interval_days"] == 180


async def test_tasks_exist_by_equipment(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    keys = [t["task"] for t in coordinator.task_status()]
    assert keys == [
        "backwash", "water_test", "skimmer_baskets", "cell_cleaning", "filter_media_check",
    ]
    coordinator.task_overrides = {"skimmer_baskets": {"enabled": False}}
    assert "skimmer_baskets" not in [t["task"] for t in coordinator.task_status()]
    hass.config_entries.async_update_entry(
        coordinator.entry, data={**coordinator.entry.data, "has_ph_probe_outside": True}
    )
    assert "ph_calibration" in [t["task"] for t in coordinator.task_status()]


async def test_pump_seconds_reset_on_completion(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 1, 10, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    coordinator.settings["season_state"] = "winter_active"
    await coordinator.async_start_cycle(240)
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "on"
    await tick(hass, freezer, 120)
    assert coordinator.task_pump_s["backwash"] >= 2 * 3600 - 120
    row = next(t for t in coordinator.task_status() if t["task"] == "backwash")
    assert row["pump_hours_since"] >= 1.9
    await coordinator.async_record_action("backwash")
    assert coordinator.task_pump_s.get("backwash", 0) == 0
    assert coordinator.task_pump_s.get("filter_cleaning", 0) > 0


async def test_rows_new_in_0_2_are_not_overdue_on_upgrade(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory, hass_storage
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.homepool.const import DOMAIN

    from .helpers import BASE, setup_helpers

    freezer.move_to(local(2026, 7, 15, 10, 0))
    since = local(2026, 6, 15, 10, 0).isoformat()
    hass_storage[f"{DOMAIN}.upg"] = {
        "version": 1, "key": f"{DOMAIN}.upg",
        "data": {"day": "2026-07-15", "tasks_since": since},
    }
    SwitchRouter(hass)
    await setup_helpers(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Pool", data=BASE, version=1, entry_id="upg"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    rows = {t["task"]: t for t in entry.runtime_data.task_status()}
    assert rows["backwash"]["overdue"]
    assert not rows["water_test"]["overdue"]
    assert not rows["skimmer_baskets"]["overdue"]
    assert rows["water_test"]["due"] == "2026-07-22"
    assert "task_first_seen" in entry.runtime_data._to_store()
