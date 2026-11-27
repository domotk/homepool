"""The pool controller: counts, decides and switches.

One instance per pool. It owns everything that changes while Home Assistant
runs — today's counters, the target, the settings people change from entities,
the log of manual tasks — keeps it in ``.storage`` so a restart does not lose a
day of filtration, and runs the control loop.

The loop runs every minute and on every state change of an entity it watches.
Each run:

1. rolls the day over if midnight has passed, splitting the running time at
   midnight so neither day gets the other's minutes;
2. adds the time the pump and the cell have been on since the last run;
3. recalculates the target when it is due;
4. evaluates safety, freeze, pH, manual actions and the mode, and lets
   ``pool.scheduler`` decide;
5. switches the pump and the cell, chlorinator first when stopping;
6. raises or clears alerts.

Nothing here decides *what* to do: that is the scheduler and the modes, which
have no Home Assistant in them and are tested on their own.
"""

from __future__ import annotations

from collections import deque
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import Context, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CHLORINATOR_AUTO_TOGGLE,
    CONF_CHLORINATOR_SWITCH,
    CONF_COVER_ENTITY,
    CONF_ENABLE_BUILTIN_NOTIFICATIONS,
    CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR,
    CONF_FILTER_PRESSURE_SENSOR,
    CONF_FLOOD_SENSOR,
    CONF_HANDS_OFF_ENTITY,
    CONF_MANUAL_OVERRIDE_MINUTES,
    CONF_NOTIFICATION_QUIET_HOURS_END,
    CONF_NOTIFICATION_QUIET_HOURS_START,
    CONF_NOTIFICATION_SERVICE,
    CONF_NOTIFICATION_SEVERITY_MIN,
    CONF_CRITICAL_IGNORE_QUIET_HOURS,
    CONF_PH_DOSING_ENTITY,
    CONF_PH_SENSOR,
    CONF_PUMP_POWER_SENSOR,
    CONF_PUMP_SWITCH,
    CONF_SOLAR_EXCESS_SENSOR,
    CONF_WATER_TEMPERATURE_SENSOR,
    DEFAULT_MANUAL_OVERRIDE_MINUTES,
    DOMAIN,
    EVALUATION_INTERVAL_S,
    HISTORY_DAYS,
    SOLAR_START_DELAY_MIN,
    SOLAR_STOP_DELAY_MIN,
    STORAGE_VERSION,
    Severity,
)
from .modes import MODE_REGISTRY
from .notify_dispatcher import NotifyDispatcher
from .pool.chlorine_calculator import is_chlorinator_in_season
from .pool.season import initial_state
from .pool.scheduler import SolarDebouncer
from .pool.treatment import Phase, counts_pump_time
from .pool.tasks import TASKS
from .runtime.actions import ActionsMixin
from .runtime.alerts import AlertsMixin
from .runtime.card import CardMixin
from .runtime.common import ACTIONS_KEPT, BAD_STATES, _iso, _parse_dt
from .runtime.config import ConfigMixin
from .runtime.control import ControlMixin
from .runtime.figures import FiguresMixin, parse_timer_slots
from .runtime.readings import ReadingsMixin
from .runtime.season import SeasonMixin
from .runtime.target import TargetMixin, _todays_forecast
from .runtime.tasks import TasksMixin
from .runtime.treatment import TreatmentMixin
from .texts import text

# Imported from here by config_flow.py and the tests.
__all__ = ["PoolCoordinator", "parse_timer_slots", "_todays_forecast"]

_LOGGER = logging.getLogger(__name__)

# How long after a command a matching state change still counts as its result.
OWN_CHANGE_WINDOW_S = 120

# The events automations and scripts fire as they start, named here rather
# than imported so HomePool does not load either integration.
EVENT_AUTOMATION_TRIGGERED = "automation_triggered"
EVENT_SCRIPT_STARTED = "script_started"

# Automation and script runs remembered to attribute pump changes.
RUNNER_CONTEXTS_KEPT = 300


class PoolCoordinator(
    ConfigMixin,
    ReadingsMixin,
    FiguresMixin,
    TasksMixin,
    SeasonMixin,
    TreatmentMixin,
    TargetMixin,
    ControlMixin,
    AlertsMixin,
    ActionsMixin,
    CardMixin,
    DataUpdateCoordinator[dict[str, Any]],
):
    """Runs one pool."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=EVALUATION_INTERVAL_S),
            config_entry=entry,
        )
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._unsubs: list[Any] = []
        self._own_contexts: deque[str] = deque(maxlen=20)
        # Contexts of automations and scripts that ran lately, with their
        # kind and name: a pump change under one of them was theirs, not a
        # person's.
        self._runner_contexts: dict[str, tuple[str, str]] = {}
        self._solar = SolarDebouncer(SOLAR_START_DELAY_MIN, SOLAR_STOP_DELAY_MIN)
        self._ph_samples: deque[tuple[datetime, float]] = deque(maxlen=60)
        self._anomaly_since: datetime | None = None
        self._pressure_high_since: datetime | None = None
        self._forecast: dict[str, Any] = {}
        # Every day the provider gave, so that today's entry is picked on each
        # calculation, not only when it was fetched.
        self._forecast_days: list[dict[str, Any]] = []
        self._forecast_at: datetime | None = None
        self._last_tick: datetime | None = None
        self._pump_was_on = False
        self._chlor_was_on = False
        self._pending: dict[str, dict[str, Any]] = {}
        self.notifier: NotifyDispatcher | None = None

        # Persisted state, filled by async_load.
        self.day: date = dt_util.now().date()
        self.elapsed_s = 0.0
        self.chlorine_s = 0.0
        self.ph_correction_s = 0.0
        self.target: dict[str, Any] = {}
        self.target_at: datetime | None = None
        self.settings: dict[str, Any] = {}
        self.tasks: dict[str, str] = {}
        self.tasks_since: datetime | None = None
        # Seconds the pump has run for each task since it was last done, and
        # the per-task changes made by the owner.
        self.task_pump_s: dict[str, float] = {}
        # When a task row first showed up without a date: rows added after 0.1.4
        # count from then, so an upgrade does not make them overdue at once.
        self.task_first_seen: dict[str, str] = {}
        # When the pool last went into wintering from another state: the winter
        # product falls due that day, whatever was done in an earlier winter.
        self.winter_entered: datetime | None = None
        # From when a winter product top-up counts for that winter: the
        # closing list's or the winter proposal's start, when earlier than
        # ``winter_entered``, so a top-up done while closing is not due again.
        self.winter_top_up_from: datetime | None = None
        self.manual_readings: dict[str, dict[str, Any]] = {}
        self.actions: list[dict[str, Any]] = []
        self.history: list[dict[str, Any]] = []
        self.energy_baseline: float | None = None
        self.air_max: dict[str, float | None] = {"today": None, "yesterday": None}
        self.in_season_last: bool | None = None
        self.cycle_until: datetime | None = None
        self.ph_window_until: datetime | None = None
        self.override: dict[str, Any] | None = None
        self.pump_changed_at: datetime | None = None
        self.pump_on_since: datetime | None = None
        self.started_by: str | None = None
        self.alerts: dict[str, dict[str, Any]] = {}
        # Which wording each raised alert used, when it has more than one.
        self._alert_text_keys: dict[str, str] = {}
        # The kinds reading_stale was last raised or updated for.
        self._stale_kinds: list[str] = []
        self.due_notified: dict[str, str] = {}
        # Reminders held back by the quiet hours, sent when they end.
        self.pending_reminders: list[dict[str, str]] = []
        # A season change the calendar proposes and the owner has not
        # confirmed: {"to", "since", "reminded", "dismissed_for"}.
        self.season_proposal: dict[str, Any] | None = None
        # Open step lists by id (closing, opening, treatment):
        # {"created": iso, "steps": [{"id", "done": iso | None}]}.
        self.checklists: dict[str, dict[str, Any]] = {}
        # The water treatment running, if any: {"type", "severity", "phase",
        # "phase_started", "counted_s", "hours", "requested_hours", "started",
        # "dose", "frost_interrupted"} and "previous_production" when a shock
        # pushed the cell to 100 %.
        self.treatment: dict[str, Any] | None = None
        # Whether today a treatment kept the pump off on purpose (settling or
        # vacuuming): such a day misses no target.
        self.treatment_rest_today = False
        # Whether ``closing_needs_pump`` was already notified: it stays raised
        # all through passive wintering, but reaches the phone once (ruling 26).
        self.closing_needs_pump_notified = False
        # A finished treatment leaves the filter due a backwash, until one is done.
        self.backwash_after_treatment = False
        # When the last shock ended, until a free chlorine inside the range is
        # measured: the water is not for swimming until then.
        self.after_shock_since: datetime | None = None
        # The probe's last distinct pH reading and when it was first seen.
        self._ph_seen: tuple[float, datetime] | None = None
        self._closed_days: list[dict[str, Any]] = []

        # Derived on every run, read by the entities.
        self.decision_source = "mode"
        self.decision_reason = ""
        self.decision_key = ""
        self.chlorinator_reason = ""
        self.safety_active = False
        self.safety_reasons: list[str] = []
        self.freeze_active = False
        self.ph_correction_active = False
        self.ph_correction_forced = False
        self.pump_anomaly = False
        self.pressure_high = False
        self.surplus_w: float | None = None
        self.ph_trend: str | None = None

    # ──────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────

    async def async_load(self) -> None:
        """Read the store and reconcile it with the clock."""
        data = await self._store.async_load() or {}
        today = dt_util.now().date()
        stored_day = data.get("day")
        self.day = date.fromisoformat(stored_day) if stored_day else today
        self.elapsed_s = float(data.get("elapsed_s", 0))
        self.chlorine_s = float(data.get("chlorine_s", 0))
        self.ph_correction_s = float(data.get("ph_correction_s", 0))
        self.target = data.get("target") or {}
        self.target_at = _parse_dt(data.get("target_at"))
        self.settings = data.get("settings") or {}
        self.tasks = data.get("tasks") or {}
        # When HomePool started keeping tasks: a task never marked as done
        # counts from here. Set on first load, and on the first load of 0.1.4.
        self.tasks_since = _parse_dt(data.get("tasks_since")) or dt_util.utcnow()
        self.task_pump_s = {k: float(v) for k, v in (data.get("task_pump_s") or {}).items()}
        self.task_first_seen = data.get("task_first_seen") or {}
        if "task_first_seen" not in data:
            # The first load of 0.2 (or a new install).
            self._seed_legacy_first_seen()
        self.winter_entered = _parse_dt(data.get("winter_entered"))
        self.winter_top_up_from = _parse_dt(data.get("winter_top_up_from"))
        self._seed_task_dates()
        self.manual_readings = data.get("manual_readings") or {}
        self.actions = data.get("actions") or []
        self.history = data.get("history") or []
        self.energy_baseline = data.get("energy_baseline")
        self.air_max = data.get("air_max") or {"today": None, "yesterday": None}
        self.in_season_last = data.get("in_season_last")
        self.cycle_until = _parse_dt(data.get("cycle_until"))
        self.ph_window_until = _parse_dt(data.get("ph_window_until"))
        self.override = data.get("override")
        self.started_by = data.get("started_by")
        self.due_notified = data.get("due_notified") or {}
        self.pending_reminders = data.get("pending_reminders") or []
        self.season_proposal = data.get("season_proposal")
        self.checklists = data.get("checklists") or {}
        self.treatment = data.get("treatment")
        self.backwash_after_treatment = bool(data.get("backwash_after_treatment", False))
        self.treatment_rest_today = bool(data.get("treatment_rest_today", False))
        self.closing_needs_pump_notified = bool(data.get("closing_needs_pump_notified", False))
        self.after_shock_since = _parse_dt(data.get("after_shock_since"))
        if self.in_season_last is None and self.is_salt:
            # Known from the first day, so the first season change after
            # installing is not missed (it used to be set at the first midnight).
            self.in_season_last = is_chlorinator_in_season(self.day, self.active_months)

        if "chlorinator_enabled" not in self.settings and self.is_salt:
            if self.conf.get(CONF_CHLORINATOR_AUTO_TOGGLE, True):
                self.settings["chlorinator_enabled"] = is_chlorinator_in_season(
                    today, self.active_months
                )
            else:
                self.settings["chlorinator_enabled"] = True

        if self.day > today:
            self.day = today
        self._configure_notifier()

        if "season_state" not in self.settings:
            # 0.1 had no season state: deduce it, and say so once. A new
            # install has nothing to be told about.
            first = initial_state(
                today.month in self.swimming_months, self.is_salt, self.chlorinator_enabled
            )
            self.settings["season_state"] = first.value
            if data:
                # Queued, not sent: at load the notify service may not exist
                # yet. The first evaluation with Home Assistant running sends it.
                language = self.hass.config.language
                self.pending_reminders.append(
                    {
                        "title": text(language, "title") + f" · {self.pool_name}",
                        "message": text(
                            language,
                            "season_state_introduced",
                            pool=self.pool_name,
                            state=text(language, f"season_{first.value}"),
                        ),
                    }
                )

    def _configure_notifier(self) -> None:
        if not self.conf.get(CONF_ENABLE_BUILTIN_NOTIFICATIONS):
            self.notifier = None
            return
        self.notifier = NotifyDispatcher(
            self.hass,
            self.conf.get(CONF_NOTIFICATION_SERVICE),
            self.conf.get(CONF_NOTIFICATION_SEVERITY_MIN) or Severity.WARNING,
            self.conf.get(CONF_NOTIFICATION_QUIET_HOURS_START),
            self.conf.get(CONF_NOTIFICATION_QUIET_HOURS_END),
            self.conf.get(CONF_CRITICAL_IGNORE_QUIET_HOURS, True),
        )

    async def async_start(self) -> None:
        """Start watching and make the cell safe before anything else."""
        now = dt_util.utcnow()
        self._last_tick = now
        self._pump_was_on = self._is_on(CONF_PUMP_SWITCH) is True
        self._chlor_was_on = self._is_on(CONF_CHLORINATOR_SWITCH) is True
        pump_state = self.hass.states.get(self.conf[CONF_PUMP_SWITCH])
        # After a restart, last_changed is when Home Assistant started, not
        # when the pump last moved, so the minimum run and rest times start
        # unknown rather than holding the pump for no reason.
        self.pump_changed_at = None
        if pump_state is not None and self._pump_was_on:
            self.pump_on_since = pump_state.last_changed

        # A cell left on with the pump off (a crash, a power cut, a restart in
        # the middle of a switch-off) is the first thing to put right.
        if self._chlor_was_on and not self._pump_was_on:
            await self._async_command(CONF_CHLORINATOR_SWITCH, False)

        watched = [
            self.conf.get(key)
            for key in (
                CONF_PUMP_SWITCH,
                CONF_CHLORINATOR_SWITCH,
                CONF_HANDS_OFF_ENTITY,
                CONF_FLOOD_SENSOR,
                CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR,
                CONF_FILTER_PRESSURE_SENSOR,
                CONF_PUMP_POWER_SENSOR,
                CONF_SOLAR_EXCESS_SENSOR,
                CONF_PH_SENSOR,
                CONF_PH_DOSING_ENTITY,
                CONF_WATER_TEMPERATURE_SENSOR,
                CONF_COVER_ENTITY,
            )
        ]
        watched = [w for w in watched if w]
        self._unsubs.append(
            async_track_state_change_event(self.hass, watched, self._handle_state_change)
        )
        # Bound @callback methods run inline as the event fires, before the
        # automation's own service call can change the pump.
        for event_type in (EVENT_AUTOMATION_TRIGGERED, EVENT_SCRIPT_STARTED):
            self._unsubs.append(self.hass.bus.async_listen(event_type, self._note_runner))

    @callback
    def _note_runner(self, event: Event) -> None:
        """Remember an automation or script run, to tell its changes apart."""
        kind = "automation" if event.event_type == EVENT_AUTOMATION_TRIGGERED else "script"
        name = event.data.get("name") or event.data.get("entity_id") or ""
        self._runner_contexts[event.context.id] = (kind, str(name))
        while len(self._runner_contexts) > RUNNER_CONTEXTS_KEPT:
            self._runner_contexts.pop(next(iter(self._runner_contexts)))

    def _changed_by(self, context: Context) -> tuple[str, str | None]:
        """Who made a change HomePool did not: a person, an automation, a script or else."""
        runner = self._runner_contexts.get(context.id)
        if runner is None and context.parent_id:
            runner = self._runner_contexts.get(context.parent_id)
        if runner is not None:
            return runner
        if context.user_id:
            return "user", None
        # A wall switch, a device's own button, or a relay that reported a
        # change late under a fresh context.
        return "external", None

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._account(dt_util.utcnow())
        await self._store.async_save(self._to_store())

    def _to_store(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "elapsed_s": round(self.elapsed_s, 1),
            "chlorine_s": round(self.chlorine_s, 1),
            "ph_correction_s": round(self.ph_correction_s, 1),
            "target": self.target,
            "target_at": _iso(self.target_at),
            "settings": self.settings,
            "tasks": self.tasks,
            "tasks_since": _iso(self.tasks_since),
            "task_pump_s": {k: round(v, 1) for k, v in self.task_pump_s.items()},
            "task_first_seen": self.task_first_seen,
            "winter_entered": _iso(self.winter_entered),
            "winter_top_up_from": _iso(self.winter_top_up_from),
            "manual_readings": self.manual_readings,
            "actions": self.actions[-ACTIONS_KEPT:],
            "history": self.history[-HISTORY_DAYS:],
            "energy_baseline": self.energy_baseline,
            "air_max": self.air_max,
            "in_season_last": self.in_season_last,
            "cycle_until": _iso(self.cycle_until),
            "ph_window_until": _iso(self.ph_window_until),
            "override": self.override,
            "started_by": self.started_by,
            "due_notified": self.due_notified,
            "pending_reminders": self.pending_reminders,
            "season_proposal": self.season_proposal,
            "checklists": self.checklists,
            "treatment": self.treatment,
            "backwash_after_treatment": self.backwash_after_treatment,
            "treatment_rest_today": self.treatment_rest_today,
            "closing_needs_pump_notified": self.closing_needs_pump_notified,
            "after_shock_since": _iso(self.after_shock_since),
        }

    def _save(self) -> None:
        self._store.async_delay_save(self._to_store, 10)

    # ──────────────────────────────────────────
    # The loop
    # ──────────────────────────────────────────

    @callback
    def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new = event.data["new_state"]
        old = event.data["old_state"]
        now = dt_util.utcnow()

        if entity_id == self.conf.get(CONF_PUMP_SWITCH):
            # Account the time up to the change under the old state first.
            self._account(now)
            new_on = new is not None and new.state == STATE_ON
            valid_new = new is not None and new.state not in BAD_STATES
            valid_old = old is not None and old.state not in BAD_STATES
            if valid_new and new_on != self._pump_was_on:
                self.pump_changed_at = now
                self.pump_on_since = now if new_on else None
                if not new_on:
                    self.started_by = None
            if valid_new:
                self._pump_was_on = new_on
            pending = self._pending.get(CONF_PUMP_SWITCH)
            # A change is HomePool's own if it carries the context of one of
            # its commands, or if it is what a command sent moments ago asked
            # for. The second matters for relays that confirm late: Home
            # Assistant only keeps a service call's context on the state for a
            # few seconds, and a slow or polled integration reports the change
            # under a fresh one. Without this, each such command would read as
            # someone switching the pump by hand.
            ours = new is not None and (
                new.context.id in self._own_contexts
                or (
                    pending is not None
                    and valid_new
                    and pending["state"] == new_on
                    and pending.get("sent") is not None
                    and now - pending["first_sent"] <= timedelta(seconds=OWN_CHANGE_WINDOW_S)
                )
            )
            if pending and valid_new and pending["state"] == new_on:
                self._pending.pop(CONF_PUMP_SWITCH, None)
            if (
                valid_new
                and valid_old
                and not ours
                and old.state != new.state
                # Vacuuming leaves the pump to the owner: their switching is
                # the treatment going as planned, not a change to respect.
                and self.treatment_phase != Phase.VACUUMING
            ):
                minutes = float(
                    self.opt(CONF_MANUAL_OVERRIDE_MINUTES, DEFAULT_MANUAL_OVERRIDE_MINUTES)
                )
                by, by_name = self._changed_by(new.context)
                self.override = {
                    "state": new_on,
                    "until": _iso(now + timedelta(minutes=minutes)),
                    "by": by,
                    "name": by_name,
                }
                self.started_by = None
                self._pending.pop(CONF_PUMP_SWITCH, None)
                _LOGGER.info(
                    "%s: pump switched %s outside HomePool (%s%s); respected for %.0f min",
                    self.pool_name,
                    "on" if new_on else "off",
                    by,
                    f" {by_name}" if by_name else "",
                    minutes,
                )
                self._save()

        elif entity_id == self.conf.get(CONF_CHLORINATOR_SWITCH):
            self._account(now)
            if new is not None and new.state not in BAD_STATES:
                self._chlor_was_on = new.state == STATE_ON
                pending = self._pending.get(CONF_CHLORINATOR_SWITCH)
                if pending and pending["state"] == self._chlor_was_on:
                    self._pending.pop(CONF_CHLORINATOR_SWITCH, None)

        self.hass.async_create_task(self.async_request_refresh())

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        await self._async_rollover(now)
        self._sample_inputs(now)
        await self._async_maybe_recalculate(now)
        await self._async_control(now)
        await self._async_alerts(now)
        await self._async_flush_reminders(now)
        self._save()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "target": self.target_minutes,
            "elapsed": self.elapsed_minutes,
            "pump_on": self.pump_is_on,
            "source": self.decision_source,
        }

    # ── accounting ──

    def _add(self, seconds: float, pump_on: bool, chlor_on: bool) -> None:
        if seconds <= 0:
            return
        if pump_on and self.pump_available:
            self.elapsed_s += seconds
            for defn in TASKS:
                if defn.pump_hours is not None:
                    self.task_pump_s[defn.key] = self.task_pump_s.get(defn.key, 0.0) + seconds
        if chlor_on and self.has(CONF_CHLORINATOR_SWITCH):
            self.chlorine_s += seconds
        if pump_on and self.decision_source == "ph_correction":
            self.ph_correction_s += seconds
        phase = self.treatment_phase
        if phase in (Phase.SETTLING, Phase.VACUUMING):
            # Charged per side of midnight, so the flag lands on the right day.
            self.treatment_rest_today = True
        if phase is not None and (
            (counts_pump_time(phase) and pump_on and self.pump_available)
            or (phase == Phase.SETTLING and not pump_on)
        ):
            # Filtering and mixing count pump time; settling counts rest.
            self.treatment["counted_s"] = float(self.treatment.get("counted_s", 0)) + seconds

    def _account(self, now: datetime) -> None:
        """Add running time since the last call, splitting it at midnight.

        Called before every state change is applied and on every tick, so the
        time is always charged to the state it was spent in. When midnight has
        passed, the part before it closes the old day and only the rest counts
        towards the new one.
        """
        if self._last_tick is None:
            self._last_tick = now
            return
        if now <= self._last_tick:
            return
        today = dt_util.as_local(now).date()
        if today > self.day:
            midnight = dt_util.start_of_local_day(today)
            if self._last_tick < midnight:
                self._add(
                    (midnight - self._last_tick).total_seconds(),
                    self._pump_was_on,
                    self._chlor_was_on,
                )
                self._last_tick = midnight
            self._close_day(today)
        self._add(
            (now - self._last_tick).total_seconds(), self._pump_was_on, self._chlor_was_on
        )
        self._last_tick = now

    def _close_day(self, today: date) -> None:
        """Put the finished day in the history and start a new one."""
        closed = {
            "day": self.day.isoformat(),
            "target": self.target_minutes,
            "elapsed": self.elapsed_minutes,
            "chlorine": self.chlorine_minutes if self.has(CONF_CHLORINATOR_SWITCH) else None,
            "energy_kwh": self.pump_energy_today,
        }
        self.history = [*self.history, closed][-HISTORY_DAYS:]
        self._closed_days.append({**closed, "treatment_rest": self.treatment_rest_today})
        self.treatment_rest_today = False
        self.day = today
        self.elapsed_s = 0.0
        self.chlorine_s = 0.0
        self.ph_correction_s = 0.0
        self.energy_baseline = None
        self.air_max = {"today": None, "yesterday": self.air_max.get("today")}
        self.target = {}
        self.target_at = None
        self._save()

    async def _async_rollover(self, now: datetime) -> None:
        """The asynchronous half of a new day: alerts and the season."""
        self._account(now)
        while self._closed_days:
            closed = self._closed_days.pop(0)
            mode = MODE_REGISTRY.get(self.mode)
            # Passive wintering keeps the pump off on purpose, and so does a
            # treatment settling or waiting to be vacuumed: no target is missed.
            if (
                mode is not None
                and mode.guarantees_target
                and not self.winter_passive
                and not closed.get("treatment_rest")
                and closed["target"]
                and closed["elapsed"] < closed["target"] * 0.9
            ):
                await self._async_raise(
                    "target_missed",
                    Severity.WARNING,
                    {"elapsed": closed["elapsed"], "target": closed["target"]},
                    once=True,
                )
            await self._async_season(self.day)
            await self._async_season_proposal(dt_util.now())
