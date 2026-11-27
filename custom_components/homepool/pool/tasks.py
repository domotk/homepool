"""The recurring tasks of a pool, as a table, and when each one falls due.

Pure logic, no Home Assistant imports. A task counts days, or, in the states
where the pump barely runs, hours of pump (a filter is dirtied by the water that
goes through it, not by the calendar). It is paused in the states where it makes
no sense, and then it never falls due.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

from ..const import (
    CONF_BACKWASH_INTERVAL_DAYS,
    CONF_CHLORINATION_TYPE,
    CONF_FILTER_TYPE,
    CONF_HAS_PH_PROBE_OUTSIDE,
    CONF_PH_CALIBRATION_INTERVAL_DAYS,
    CONF_PH_SENSOR,
    DEFAULT_BACKWASH_INTERVAL_DAYS,
    DEFAULT_PH_CALIBRATION_INTERVAL_DAYS,
    FilterType,
)

SWIMMING = "swimming"
WINTER_ACTIVE = "winter_active"
WINTER_PASSIVE = "winter_passive"
OPENING = "opening"

_NOT_PASSIVE = (SWIMMING, WINTER_ACTIVE, OPENING)
_WINTER = (WINTER_ACTIVE, WINTER_PASSIVE)


@dataclass(frozen=True)
class TaskDef:
    key: str
    action: str  # the ManualAction value that completes it
    days: int | None
    pump_hours: float | None
    pump_hours_states: tuple[str, ...]  # states where pump_hours replaces days
    states: tuple[str, ...]  # season states where it counts
    optional: bool
    # Where the interval in days differs from ``days`` in some state.
    days_by_state: tuple[tuple[str, int], ...] = ()


TASKS: tuple[TaskDef, ...] = (
    TaskDef("backwash", "backwash", 14, 112.0, (WINTER_ACTIVE, OPENING), _NOT_PASSIVE, False),
    TaskDef(
        "filter_cleaning", "filter_cleaned", 14, 112.0, (WINTER_ACTIVE, OPENING), _NOT_PASSIVE, False
    ),
    TaskDef("ph_calibration", "ph_calibrated", 180, None, (), _NOT_PASSIVE, False),
    TaskDef("winter_product", "winter_product_added", 56, None, (), _WINTER, False),
    TaskDef(
        "water_test", "water_tested", 7, None, (), _NOT_PASSIVE, False,
        days_by_state=((WINTER_ACTIVE, 14),),
    ),
    TaskDef("skimmer_baskets", "skimmer_baskets_emptied", 7, None, (), (SWIMMING,), True),
    TaskDef("cell_cleaning", "cell_cleaned", 90, None, (), (SWIMMING,), False),
    TaskDef("filter_media_check", "filter_media_checked", 1825, None, (), _NOT_PASSIVE, True),
)

# The two filter jobs: one or the other exists, by filter type.
FILTER_TASKS = ("backwash", "filter_cleaning")
# Rows that already existed in 0.1.4: they count from ``tasks_since``.
LEGACY_TASKS = ("backwash", "filter_cleaning", "ph_calibration")
TASKS_BY_KEY = {t.key: t for t in TASKS}
TASKS_BY_ACTION = {t.action: t for t in TASKS}


def default_days(defn: TaskDef, season_state: str) -> int | None:
    """The interval in days for a state, before any option or override."""
    return dict(defn.days_by_state).get(season_state, defn.days)


def _set(conf: Mapping[str, Any], key: str, default: Any = None) -> Any:
    value = conf.get(key)
    return default if value in (None, "") else value


def task_applies(key: str, conf: Mapping[str, Any]) -> bool:
    """Whether the pool's equipment calls for a task, whatever the owner chose.

    ``conf`` is the pool's configuration (entry data over options).
    """
    filter_type = conf.get(CONF_FILTER_TYPE, FilterType.SAND)
    filter_bed = filter_type in (
        FilterType.SAND,
        FilterType.GLASS,
        FilterType.DIATOMACEOUS_EARTH,
    )
    return {
        "backwash": filter_bed,
        "filter_cleaning": not filter_bed,
        "ph_calibration": bool(conf.get(CONF_PH_SENSOR) or conf.get(CONF_HAS_PH_PROBE_OUTSIDE)),
        "winter_product": _set(conf, "winter_product_type", "none") != "none",
        "cell_cleaning": conf.get(CONF_CHLORINATION_TYPE) == "salt",
        "filter_media_check": filter_type in (FilterType.SAND, FilterType.GLASS),
    }.get(key, True)


def configured_days(defn: TaskDef, conf: Mapping[str, Any], season_state: str) -> int | None:
    """The interval in days before a per-task override: the pump and water
    steps' settings for the jobs that had one in 0.1, the table otherwise."""
    if defn.key in FILTER_TASKS:
        return int(_set(conf, CONF_BACKWASH_INTERVAL_DAYS, DEFAULT_BACKWASH_INTERVAL_DAYS))
    if defn.key == "ph_calibration":
        return int(
            _set(conf, CONF_PH_CALIBRATION_INTERVAL_DAYS, DEFAULT_PH_CALIBRATION_INTERVAL_DAYS)
        )
    return default_days(defn, season_state)


@dataclass
class TaskState:
    key: str
    last_done: datetime | None
    counted_from: datetime | None
    interval_days: int | None
    interval_pump_hours: float | None
    pump_hours_since: float | None
    due: date | None
    overdue: bool
    paused: bool


def task_state(
    defn: TaskDef,
    *,
    last_done: datetime | None,
    counted_from: datetime | None,
    today: date,
    season_state: str,
    pump_seconds_since: float,
    days: int | None,
    pump_hours: float | None,
    force: bool = False,
) -> TaskState:
    """Where one task stands.

    ``last_done`` and ``counted_from`` give the date it counts from (the first
    wins); the caller passes them in local time. ``force`` makes it overdue now
    (high filter pressure), unless the task is paused.
    """
    paused = season_state not in defn.states
    by_pump = season_state in defn.pump_hours_states and pump_hours is not None
    base = last_done or counted_from
    due: date | None = None
    if by_pump:
        overdue = pump_seconds_since >= pump_hours * 3600
    else:
        overdue = False
        if base is not None and days is not None:
            due = base.date() + timedelta(days=days)
            overdue = today >= due
    if paused:
        due = None
        overdue = False
    elif force:
        overdue = True
    return TaskState(
        key=defn.key,
        last_done=last_done,
        counted_from=counted_from if last_done is None else None,
        interval_days=None if by_pump else days,
        interval_pump_hours=pump_hours if by_pump else None,
        pump_hours_since=round(pump_seconds_since / 3600, 1) if by_pump else None,
        due=due,
        overdue=overdue,
        paused=paused,
    )
