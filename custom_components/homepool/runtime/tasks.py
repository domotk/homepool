"""Manual maintenance tasks: their state, and recording them done.

A mixin of ``PoolCoordinator``; see coordinator.py.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time
from typing import Any

from homeassistant.util import dt as dt_util

from ..const import (
    CONF_FILTER_TYPE,
    CONF_WINTER_PRODUCT_DOSE_PER_M3,
    CONF_WINTER_PRODUCT_TYPE,
    DEFAULT_WINTER_PRODUCT_DOSE_PER_M3,
    FilterType,
    ManualAction,
)
from ..pool.dosing import winter_product_dose
from ..pool.tasks import (
    FILTER_TASKS,
    LEGACY_TASKS,
    TASKS,
    TASKS_BY_ACTION,
    TASKS_BY_KEY,
    TaskDef,
    configured_days,
    task_applies,
    task_state,
)
from .common import ACTIONS_KEPT, _iso, _parse_dt


def _parse_date(value: Any) -> date | None:
    return dt_util.parse_date(value) if isinstance(value, str) else None


class TasksMixin:
    """Manual maintenance tasks: their state, and recording them done."""

    def days_since(self, task: str) -> int | None:
        when = _parse_dt(self.tasks.get(task))
        if when is None:
            return None
        return (dt_util.now().date() - dt_util.as_local(when).date()).days

    @property
    def uses_backwash(self) -> bool:
        return self.conf.get(CONF_FILTER_TYPE, FilterType.SAND) in (
            FilterType.SAND,
            FilterType.GLASS,
            FilterType.DIATOMACEOUS_EARTH,
        )

    @property
    def task_overrides(self) -> dict[str, dict[str, Any]]:
        """What the owner changed per task, from the options: ``days``,
        ``pump_hours`` and, for optional tasks, ``enabled``."""
        return self.conf.get("tasks") or {}

    def _task_exists(self, defn: TaskDef) -> bool:
        if defn.optional and not self.task_overrides.get(defn.key, {}).get(
            "enabled", defn.enabled_by_default
        ):
            return False
        return task_applies(defn.key, self.conf)

    def has_task(self, key: str) -> bool:
        return self._task_exists(TASKS_BY_KEY[key])

    def _task_days(self, defn: TaskDef) -> int | None:
        override = self.task_overrides.get(defn.key, {}).get("days")
        if override is not None:
            return int(override)
        return configured_days(defn, self.conf, self.season_state)

    def _seed_legacy_first_seen(self) -> None:
        """On the first load of 0.2, the rows 0.1.4 already had count from
        ``tasks_since``, as they did. One that only appears later (a pH probe
        of the owner's own turned on) counts from when it appears."""
        if self.tasks_since is None:
            return
        for key in LEGACY_TASKS:
            if key not in self.task_first_seen and self._task_exists(TASKS_BY_KEY[key]):
                self.task_first_seen[key] = self.tasks_since.isoformat()

    def _seed_task_dates(self) -> None:
        """Take the "last done" dates given in the setup wizard, once.

        The wizard has no pool to write them into yet, so it leaves them in
        the options; a task that already has a date keeps it.
        """
        for key, cfg in self.task_overrides.items():
            defn = TASKS_BY_KEY.get(key)
            when = _parse_date(cfg.get("last_done"))
            if defn is not None and when is not None and defn.action not in self.tasks:
                self.tasks[defn.action] = self._noon(when).isoformat()

    @staticmethod
    def _noon(day: date) -> datetime:
        """Noon of a day in the pool's time zone, as UTC: a date given by hand
        has no time, and noon keeps it on that day in either direction."""
        local_noon = datetime.combine(day, time(12), tzinfo=dt_util.get_default_time_zone())
        return dt_util.as_utc(local_noon)

    def _task_pump_hours(self, defn: TaskDef) -> float | None:
        override = self.task_overrides.get(defn.key, {}).get("pump_hours")
        return float(override) if override is not None else defn.pump_hours

    def task_status(self) -> list[dict[str, Any]]:
        """Every recurring task with when it was done and when it falls due."""
        return [self._task(defn) for defn in TASKS if self._task_exists(defn)]

    def _task(self, defn: TaskDef) -> dict[str, Any]:
        done = _parse_dt(self.tasks.get(defn.action))
        # Never marked as done: count from when HomePool started keeping
        # tasks, so a task without a date still falls due one day.
        counted_from = self.tasks_since if done is None else None
        if done is None:
            first_seen = _parse_dt(self.task_first_seen.get(defn.key))
            if first_seen is None:
                first_seen = dt_util.utcnow()
                self.task_first_seen[defn.key] = first_seen.isoformat()
            counted_from = max(counted_from, first_seen) if counted_from else first_seen
        days = self._task_days(defn)
        task_days = days
        # The date it was really done stays in the row; the due date may count
        # from somewhere else.
        counts_done = done
        if defn.key == "winter_product" and self.winter_entered is not None:
            if done is None or done < (self.winter_top_up_from or self.winter_entered):
                # Not done since going into winter: it is due that very day.
                counts_done, counted_from, days = None, self.winter_entered, 0
        state = task_state(
            defn,
            last_done=dt_util.as_local(counts_done) if counts_done else None,
            counted_from=dt_util.as_local(counted_from) if counted_from else None,
            today=dt_util.now().date(),
            season_state=self.season_state,
            pump_seconds_since=self.task_pump_s.get(defn.key, 0.0),
            days=days,
            pump_hours=self._task_pump_hours(defn),
            force=(self.pressure_high or self.backwash_after_treatment)
            and defn.key in FILTER_TASKS,
        )
        return {
            "task": defn.key,
            "last_done": _iso(done),
            "interval_days": None if state.interval_days is None else task_days,
            "interval_pump_hours": state.interval_pump_hours,
            "pump_hours_since": state.pump_hours_since,
            "counted_from": _iso(counted_from),
            "due": state.due.isoformat() if state.due else None,
            "overdue": state.overdue,
            "paused": state.paused,
        }

    @property
    def winter_product(self) -> dict[str, Any] | None:
        """What the winter product is and how much of it the pool takes."""
        product = self.opt(CONF_WINTER_PRODUCT_TYPE, "none")
        if product in (None, "", "none") or self.volume <= 0:
            return None
        per_m3 = float(
            self.opt(CONF_WINTER_PRODUCT_DOSE_PER_M3, DEFAULT_WINTER_PRODUCT_DOSE_PER_M3)
        )
        return {"type": product, "dose": asdict(winter_product_dose(product, per_m3, self.volume))}

    @property
    def backwash_needed(self) -> bool:
        for task in self.task_status():
            if task["task"] in FILTER_TASKS:
                return task["overdue"]
        return False

    @property
    def manual_action_pending(self) -> bool:
        return any(t["overdue"] for t in self.task_status())

    @property
    def next_manual_task(self) -> str:
        tasks = self.task_status()
        overdue = [t for t in tasks if t["overdue"]]
        if overdue:
            return overdue[0]["task"]
        dated = sorted((t for t in tasks if t["due"]), key=lambda t: t["due"])
        return dated[0]["task"] if dated else "none"

    async def async_complete_task(self, task: str, when: date | None = None) -> None:
        """Mark a task done today, or on a past day given by hand."""
        await self.async_record_action(TASKS_BY_KEY[task].action, at=self._done_at(when))

    def _done_at(self, when: date | None) -> datetime | None:
        """When a job done on ``when`` counts from: noon that day, but never later than now."""
        if when is None:
            return None
        return min(self._noon(when), dt_util.utcnow())

    async def async_record_action(
        self,
        action: str,
        value: float | None = None,
        notes: str | None = None,
        at: datetime | None = None,
    ) -> None:
        now = at or dt_util.utcnow()
        self.actions = [
            *self.actions,
            {"type": action, "at": now.isoformat(), "value": value, "notes": notes},
        ][-ACTIONS_KEPT:]
        completed = TASKS_BY_ACTION.get(action)
        if completed is not None or action == ManualAction.SALT_ADDED:
            self.tasks[action] = now.isoformat()
        if completed is not None:
            self.task_pump_s.pop(completed.key, None)
            self.due_notified.pop(completed.key, None)
            if completed.key in FILTER_TASKS:
                self._pressure_high_since = None
                self.pressure_high = False
                self.backwash_after_treatment = False
        self._save()
        await self.async_refresh()
