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
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPower,
)
from homeassistant.core import (
    Context,
    CoreState,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CHLORINATOR_FLOW_DELAY_S,
    COMMAND_MAX_ATTEMPTS,
    COMMAND_RETRY_S,
    CONF_AIR_TEMPERATURE_SENSOR,
    CONF_CHLORINATION_TYPE,
    CONF_CHLORINATOR_ACTIVE_MONTHS,
    CONF_CHLORINATOR_AUTO_TOGGLE,
    CONF_CHLORINATOR_CONTROLLABLE,
    CONF_CHLORINATOR_MIN_WATER_TEMP,
    CONF_CHLORINATOR_NOMINAL_PRODUCTION,
    CONF_CHLORINATOR_PRODUCTION_DEFAULT,
    CONF_CHLORINATOR_PRODUCTION_ENTITY,
    CONF_CHLORINATOR_SELF_REGULATING,
    CONF_CHLORINATOR_SWITCH,
    CONF_COVER_ENTITY,
    CONF_ENABLE_BUILTIN_NOTIFICATIONS,
    CONF_ENERGY_PRICE,
    CONF_ENERGY_PRICE_ENTITY,
    CONF_EQUIPMENT_ROOM_HUMIDITY_SENSOR,
    CONF_EQUIPMENT_ROOM_MAX_TEMP,
    CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR,
    CONF_FILTER_PRESSURE_CRITICAL,
    CONF_FILTER_PRESSURE_NORMAL_MAX,
    CONF_FILTER_PRESSURE_SENSOR,
    CONF_FILTER_TYPE,
    CONF_FLOOD_SENSOR,
    CONF_FREE_CHLORINE_SENSOR,
    CONF_FREEZE_PROTECTION,
    CONF_FREEZE_THRESHOLD,
    CONF_HANDS_OFF_ENTITY,
    CONF_HAS_COVER,
    CONF_HAS_PH_DOSING,
    CONF_IS_COVERED_BY_ROOF,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MANUAL_OVERRIDE_MINUTES,
    CONF_NOTIFICATION_QUIET_HOURS_END,
    CONF_NOTIFICATION_QUIET_HOURS_START,
    CONF_NOTIFICATION_SERVICE,
    CONF_NOTIFICATION_SEVERITY_MIN,
    CONF_CRITICAL_IGNORE_QUIET_HOURS,
    CONF_ORP_SENSOR,
    CONF_PH_CORRECTION_MAX_DAILY,
    CONF_PH_CORRECTION_MINUTES,
    CONF_PH_DOSING_ENTITY,
    CONF_PH_RANGE_MAX,
    CONF_PH_RANGE_MIN,
    CONF_PH_SENSOR,
    CONF_PH_TARGET,
    CONF_POOL_NAME,
    CONF_PUMP_ENERGY_SENSOR,
    CONF_PUMP_NOMINAL_FLOW_RATE,
    CONF_PUMP_NOMINAL_POWER,
    CONF_PUMP_POWER_SENSOR,
    CONF_PUMP_SWITCH,
    CONF_RAIN_SENSOR,
    CONF_SALINITY_SENSOR,
    CONF_SALT_RANGE_MIN,
    CONF_SALT_TARGET,
    CONF_SOLAR_EXCESS_SENSOR,
    CONF_SOLAR_EXCESS_SIGN,
    CONF_SOLAR_IMPORT_TOLERANCE,
    CONF_SWIMMING_MONTHS,
    CONF_TIMER_SLOTS,
    CONF_UV_SENSOR,
    CONF_VOLUME,
    CONF_WATER_TEMPERATURE_SENSOR,
    CONF_WEATHER_ENTITY,
    CONF_WINTER_PRODUCT_DOSE_PER_M3,
    CONF_WINTER_PRODUCT_TYPE,
    DEFAULT_CHLORINATOR_MIN_WATER_TEMP,
    DEFAULT_CHLORINATOR_PRODUCTION_PCT,
    DEFAULT_EQUIPMENT_ROOM_MAX_TEMP,
    DEFAULT_FILTER_PRESSURE_CRITICAL,
    DEFAULT_WINTER_PRODUCT_DOSE_PER_M3,
    DEFAULT_FILTER_PRESSURE_NORMAL_MAX,
    DEFAULT_FREEZE_THRESHOLD,
    DEFAULT_MANUAL_OVERRIDE_MINUTES,
    DEFAULT_OPERATION_MODE,
    DEFAULT_PH_CORRECTION_MAX_DAILY,
    DEFAULT_PH_CORRECTION_MINUTES,
    DEFAULT_PH_RANGE_MAX,
    DEFAULT_PH_RANGE_MIN,
    DEFAULT_PH_TARGET,
    DEFAULT_SALT_RANGE_MIN,
    DEFAULT_SALT_TARGET,
    DEFAULT_SOLAR_IMPORT_TOLERANCE_W,
    DEFAULT_USER_MULTIPLIER,
    DOMAIN,
    END_OF_DAY_MARGIN_MIN,
    EVALUATION_INTERVAL_S,
    EVENT_ALERT,
    EVENT_CHLORINATOR_SEASON_END,
    EVENT_CHLORINATOR_SEASON_START,
    EVENT_MANUAL_ACTION_DUE,
    EVENT_SAFETY_SHUTOFF,
    EVENT_SEASON_PROPOSAL,
    EVENT_SEASON_STATE_CHANGED,
    EVENT_TARGET_RECALCULATED,
    HISTORY_DAYS,
    MIN_OFF_MINUTES,
    MIN_ON_MINUTES,
    RECALC_INTERVAL_MIN,
    SOLAR_START_DELAY_MIN,
    SOLAR_STOP_DELAY_MIN,
    STORAGE_VERSION,
    ChlorinationMode,
    ExcessSign,
    FilterType,
    ManualAction,
    OperationMode,
    OverallStatus,
    PhTrend,
    Severity,
)
from .modes import MODE_REGISTRY, PoolContext, PumpAction, in_slot
from .notify_dispatcher import NotifyDispatcher
from .pool.chlorine_calculator import (
    ChlorineInputs,
    calculate_chlorine_target,
    is_chlorinator_in_season,
)
from .pool.checklists import CLOSING, OPENING, build, step_def
from .pool.dosing import winter_product_dose
from .pool.filtration_calculator import FiltrationInputs, calculate_filtration_target
from .pool.geometry import calculate_cycle_duration_minutes
from .pool.safety import evaluate_safety
from .pool.season import (
    WINTER_STATES,
    SeasonState,
    default_swimming_months,
    initial_state,
    season_proposal,
)
from .pool.scheduler import (
    ChlorinatorInputs,
    ControlInputs,
    SolarDebouncer,
    arbitrate,
    chlorinator_wanted,
    solar_noon_utc,
    surplus_watts,
)
from .pool.tasks import (
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
from .texts import reason_text, text

_LOGGER = logging.getLogger(__name__)

BAD_STATES = (STATE_UNAVAILABLE, STATE_UNKNOWN, None, "")
# A power reading has to stay out of range this long to count as an anomaly.
ANOMALY_MINUTES = 5
ACTIONS_KEPT = 50
# How long after a command a matching state change still counts as its result.
OWN_CHANGE_WINDOW_S = 120


def parse_timer_slots(text_value: str | None) -> list[tuple[int, int]]:
    """``"08:00-12:00, 18:30-20:00"`` → minutes of the day. Bad parts are skipped."""
    slots: list[tuple[int, int]] = []
    for part in (text_value or "").replace(";", ",").split(","):
        start, sep, end = part.strip().partition("-")
        if not sep:
            continue
        try:
            sh, sm = (int(x) for x in start.strip().split(":"))
            eh, em = (int(x) for x in end.strip().split(":"))
        except ValueError:
            continue
        if not (0 <= sh <= 24 and 0 <= eh <= 24 and 0 <= sm < 60 and 0 <= em < 60):
            continue
        slots.append(((sh * 60 + sm) % 1440, (eh * 60 + em) % 1440))
    return slots


def _whole_minutes(seconds: float) -> int:
    """Seconds to the nearest minute. Truncating left the count a minute behind."""
    return int(seconds / 60 + 0.5)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_dt(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


def _parse_date(value: Any) -> date | None:
    return dt_util.parse_date(value) if isinstance(value, str) else None


def _todays_forecast(days: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """The daily forecast entry for ``today``.

    Providers date a day differently: Open-Meteo at 00:00 UTC, so in Spain the
    first entry is still yesterday until 01:00. The date as the provider wrote
    it is the day it means, whatever the offset; the first entry is the
    fallback when no entry names today.
    """
    for day in days:
        stamp = day.get("datetime")
        written = stamp.isoformat() if isinstance(stamp, datetime) else str(stamp or "")
        if written[:10] == today.isoformat():
            return day
    return days[0]


# The events automations and scripts fire as they start, named here rather
# than imported so HomePool does not load either integration.
EVENT_AUTOMATION_TRIGGERED = "automation_triggered"
EVENT_SCRIPT_STARTED = "script_started"

# Automation and script runs remembered to attribute pump changes.
RUNNER_CONTEXTS_KEPT = 300
REMINDERS_KEPT = 20
# An unconfirmed season proposal is brought up again after this many days.
PROPOSAL_REMIND_DAYS = 7
# The proposals that come from the calendar; any other is not the calendar's
# to withdraw.
CALENDAR_PROPOSALS = ("winter", "opening")
# Rungs above freeze protection: with one of them deciding, the pump is not
# kept running however cold the water is.
FREEZE_BLOCKERS = ("unavailable", "hands_off", "maintenance_lock", "safety")
# A pH probe outside this range, or reading exactly the same for this long,
# is not trusted to run the pump.
PH_PLAUSIBLE_MIN = 5.0
PH_PLAUSIBLE_MAX = 9.0
PH_FROZEN_HOURS = 24

# How far the pool's own air sensor may read above the forecast high.
MEASURED_AIR_MARGIN_C = 3.0


class PoolCoordinator(DataUpdateCoordinator[dict[str, Any]]):
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
        self.due_notified: dict[str, str] = {}
        # Reminders held back by the quiet hours, sent when they end.
        self.pending_reminders: list[dict[str, str]] = []
        # A season change the calendar proposes and the owner has not
        # confirmed: {"to", "since", "reminded", "dismissed_for"}.
        self.season_proposal: dict[str, Any] | None = None
        # Open step lists by id (closing, opening, treatment):
        # {"created": iso, "steps": [{"id", "done": iso | None}]}.
        self.checklists: dict[str, dict[str, Any]] = {}
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
    # Configuration
    # ──────────────────────────────────────────

    @property
    def conf(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def opt(self, key: str, default: Any = None) -> Any:
        value = self.conf.get(key)
        return default if value in (None, "") else value

    @property
    def pool_name(self) -> str:
        return self.conf.get(CONF_POOL_NAME) or self.entry.title

    @property
    def is_salt(self) -> bool:
        return self.conf.get(CONF_CHLORINATION_TYPE) == "salt"

    @property
    def self_regulating(self) -> bool:
        return bool(self.conf.get(CONF_CHLORINATOR_SELF_REGULATING))

    def has(self, key: str) -> bool:
        return bool(self.conf.get(key))

    @property
    def volume(self) -> float:
        return float(self.opt(CONF_VOLUME, 0) or 0)

    @property
    def flow_rate(self) -> float:
        return float(self.opt(CONF_PUMP_NOMINAL_FLOW_RATE, 0) or 0)

    @property
    def cycle_duration(self) -> int | None:
        if self.volume <= 0 or self.flow_rate <= 0:
            return None
        return calculate_cycle_duration_minutes(self.volume, self.flow_rate)

    @property
    def active_months(self) -> list[int]:
        months = self.conf.get(CONF_CHLORINATOR_ACTIVE_MONTHS) or []
        return sorted(int(m) for m in months)

    @property
    def swimming_months(self) -> list[int]:
        """The months the pool is used: what season proposals follow."""
        months = self.conf.get(CONF_SWIMMING_MONTHS)
        if months:
            return sorted(int(m) for m in months)
        latitude = float(self.opt(CONF_LATITUDE, self.hass.config.latitude) or 0)
        return default_swimming_months(self.active_months, self.is_salt, latitude)

    # Settings changed from entities: stored, not in the config entry, so that
    # moving a slider does not reload the whole integration.
    def setting(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    @property
    def mode(self) -> str:
        return self.settings.get("mode", DEFAULT_OPERATION_MODE)

    @property
    def user_multiplier(self) -> float:
        return float(self.settings.get("user_multiplier", DEFAULT_USER_MULTIPLIER))

    @property
    def maintenance_lock(self) -> bool:
        return bool(self.settings.get("maintenance_lock", False))

    @property
    def chlorinator_enabled(self) -> bool:
        return bool(self.settings.get("chlorinator_enabled", True))

    @property
    def solar_threshold(self) -> float:
        default = float(self.opt(CONF_PUMP_NOMINAL_POWER, 0) or 0) or 800.0
        return float(self.settings.get("solar_threshold", default))

    @property
    def ph_target(self) -> float:
        return float(
            self.settings.get("ph_target", self.opt(CONF_PH_TARGET, DEFAULT_PH_TARGET))
        )

    @property
    def chlorinator_production(self) -> float:
        return float(
            self.settings.get(
                "chlorinator_production",
                self.opt(CONF_CHLORINATOR_PRODUCTION_DEFAULT, DEFAULT_CHLORINATOR_PRODUCTION_PCT),
            )
        )

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
        self.winter_entered = _parse_dt(data.get("winter_entered"))
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
        }

    def _save(self) -> None:
        self._store.async_delay_save(self._to_store, 10)

    # ──────────────────────────────────────────
    # Reading entities
    # ──────────────────────────────────────────

    def _state(self, key: str):
        entity_id = self.conf.get(key)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in BAD_STATES:
            return None
        return state

    def _is_on(self, key: str) -> bool | None:
        state = self._state(key)
        if state is None:
            return None
        return state.state in (STATE_ON, "open", "heat", "true")

    def _number(self, key: str) -> float | None:
        state = self._state(key)
        if state is None:
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def _watts(self, key: str) -> float | None:
        """A power reading in W, whatever unit the sensor uses."""
        value = self._number(key)
        if value is None:
            return None
        unit = self._state(key).attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if unit == UnitOfPower.KILO_WATT:
            return value * 1000
        return value

    @property
    def pump_power(self) -> float | None:
        """Measured draw, or the nameplate figure while running if unmeasured."""
        measured = self._watts(CONF_PUMP_POWER_SENSOR)
        if measured is not None:
            return measured
        nominal = self.opt(CONF_PUMP_NOMINAL_POWER)
        return float(nominal) if nominal and self._pump_was_on else None

    @property
    def water_temperature(self) -> float | None:
        return self._number(CONF_WATER_TEMPERATURE_SENSOR)

    @property
    def air_temperature(self) -> float | None:
        value = self._number(CONF_AIR_TEMPERATURE_SENSOR)
        if value is not None:
            return value
        weather = self._state(CONF_WEATHER_ENTITY)
        if weather is not None:
            temp = weather.attributes.get("temperature")
            if isinstance(temp, (int, float)):
                return float(temp)
        return None

    @property
    def ph(self) -> float | None:
        return self._number(CONF_PH_SENSOR)

    @property
    def salinity(self) -> tuple[float | None, str | None]:
        value = self._number(CONF_SALINITY_SENSOR)
        if value is not None:
            return value, "salinity_sensor"
        record = self.manual_readings.get("salt")
        if record:
            return float(record["value"]), "manual_record"
        return None, None

    @property
    def free_chlorine(self) -> tuple[float | None, str | None]:
        value = self._number(CONF_FREE_CHLORINE_SENSOR)
        if value is not None:
            return value, "free_chlorine_sensor"
        record = self.manual_readings.get("free_chlorine")
        if record:
            return float(record["value"]), "manual_record"
        return None, None

    @property
    def orp(self) -> float | None:
        return self._number(CONF_ORP_SENSOR)

    @property
    def filter_pressure(self) -> float | None:
        return self._number(CONF_FILTER_PRESSURE_SENSOR)

    @property
    def pump_is_on(self) -> bool:
        return self._pump_was_on

    @property
    def pump_available(self) -> bool:
        return self._is_on(CONF_PUMP_SWITCH) is not None

    @property
    def chlorinator_is_on(self) -> bool:
        return self._chlor_was_on

    # ──────────────────────────────────────────
    # Derived figures, in minutes
    # ──────────────────────────────────────────

    @property
    def elapsed_minutes(self) -> int:
        return _whole_minutes(self.elapsed_s)

    @property
    def chlorine_minutes(self) -> int:
        return _whole_minutes(self.chlorine_s)

    @property
    def ph_correction_minutes(self) -> int:
        return _whole_minutes(self.ph_correction_s)

    @property
    def target_minutes(self) -> int:
        return int(self.target.get("target_minutes") or 0)

    @property
    def filtration_component(self) -> int | None:
        return self.target.get("target_filtration_minutes")

    @property
    def chlorine_component(self) -> int | None:
        return self.target.get("target_chlorine_minutes")

    @property
    def remaining_minutes(self) -> int:
        return max(0, self.target_minutes - self.elapsed_minutes)

    @property
    def target_reached(self) -> bool:
        return self.target_minutes > 0 and self.elapsed_minutes >= self.target_minutes

    @property
    def chlorine_target_reached(self) -> bool:
        target = self.chlorine_component
        if not target:
            return False
        return self.chlorine_minutes >= target

    @property
    def chlorine_remaining(self) -> int | None:
        target = self.chlorine_component
        if target is None:
            return None
        return max(0, target - self.chlorine_minutes)

    @property
    def recommended_production(self) -> float | None:
        return self.target.get("recommended_chlorinator_pct")

    @property
    def in_season(self) -> bool:
        return is_chlorinator_in_season(dt_util.now().date(), self.active_months)

    @property
    def chlorination_mode(self) -> str:
        if (
            self.season_state in WINTER_STATES
            and self.opt(CONF_WINTER_PRODUCT_TYPE, "none") != "none"
        ):
            return ChlorinationMode.WINTER_PRODUCT
        if not self.is_salt:
            return ChlorinationMode.TABLETS
        if self.in_season and self.chlorinator_enabled:
            return ChlorinationMode.SALT
        return ChlorinationMode.OFF

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
    def season_state(self) -> str:
        """The owner's season state; set on the first load when missing."""
        return self.settings.get("season_state", SeasonState.SWIMMING)

    @property
    def winter_passive(self) -> bool:
        return self.season_state == SeasonState.WINTER_PASSIVE

    @property
    def task_overrides(self) -> dict[str, dict[str, Any]]:
        """What the owner changed per task, from the options: ``days``,
        ``pump_hours`` and, for optional tasks, ``enabled``."""
        return self.conf.get("tasks") or {}

    def _task_exists(self, defn: TaskDef) -> bool:
        if defn.optional and self.task_overrides.get(defn.key, {}).get("enabled") is False:
            return False
        return task_applies(defn.key, self.conf)

    def has_task(self, key: str) -> bool:
        return self._task_exists(TASKS_BY_KEY[key])

    def _task_days(self, defn: TaskDef) -> int | None:
        override = self.task_overrides.get(defn.key, {}).get("days")
        if override is not None:
            return int(override)
        return configured_days(defn, self.conf, self.season_state)

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
        if done is None and defn.key not in LEGACY_TASKS:
            first_seen = _parse_dt(self.task_first_seen.get(defn.key))
            if first_seen is None:
                first_seen = dt_util.utcnow()
                self.task_first_seen[defn.key] = first_seen.isoformat()
            counted_from = max(counted_from, first_seen) if counted_from else first_seen
        days = self._task_days(defn)
        task_days = days
        if defn.key == "winter_product" and self.winter_entered is not None:
            if done is None or done < self.winter_entered:
                # Not done since going into winter: it is due that very day.
                done, counted_from, days = None, self.winter_entered, 0
        state = task_state(
            defn,
            last_done=dt_util.as_local(done) if done else None,
            counted_from=dt_util.as_local(counted_from) if counted_from else None,
            today=dt_util.now().date(),
            season_state=self.season_state,
            pump_seconds_since=self.task_pump_s.get(defn.key, 0.0),
            days=days,
            pump_hours=self._task_pump_hours(defn),
            force=self.pressure_high and defn.key in FILTER_TASKS,
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

    @property
    def ph_out_of_range(self) -> bool:
        ph = self.ph
        if ph is None:
            return False
        low = float(self.opt(CONF_PH_RANGE_MIN, DEFAULT_PH_RANGE_MIN))
        high = float(self.opt(CONF_PH_RANGE_MAX, DEFAULT_PH_RANGE_MAX))
        return not low <= ph <= high

    @property
    def critical_water_temperature(self) -> bool:
        temp = self.water_temperature
        if temp is None:
            return False
        return temp < float(self.opt(CONF_FREEZE_THRESHOLD, DEFAULT_FREEZE_THRESHOLD)) or temp > 33

    @property
    def equipment_room_overheat(self) -> bool:
        temp = self._number(CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR)
        if temp is None:
            return False
        return temp > float(self.opt(CONF_EQUIPMENT_ROOM_MAX_TEMP, DEFAULT_EQUIPMENT_ROOM_MAX_TEMP))

    @property
    def flood(self) -> bool:
        return self._is_on(CONF_FLOOD_SENSOR) is True

    @property
    def overall_status(self) -> str:
        if (
            self.safety_active
            or "pump_not_responding" in self.alerts
            or "chlorinator_not_responding" in self.alerts
        ):
            return OverallStatus.ACTION_REQUIRED
        if (
            self.alerts
            or self.manual_action_pending
            or self.ph_out_of_range
            or self.pump_anomaly
        ):
            return OverallStatus.ATTENTION
        return OverallStatus.OK

    @property
    def pump_energy_today(self) -> float | None:
        reading = self._number(CONF_PUMP_ENERGY_SENSOR)
        if reading is None:
            return None
        if self.energy_baseline is None or reading < self.energy_baseline:
            # First reading of the day, or the meter was reset: start from here.
            self.energy_baseline = reading
            self._save()
        return round(reading - self.energy_baseline, 3)

    @property
    def energy_price(self) -> float | None:
        entity_price = self._number(CONF_ENERGY_PRICE_ENTITY)
        if entity_price is not None:
            return entity_price
        price = self.opt(CONF_ENERGY_PRICE)
        return float(price) if price not in (None, "") else None

    @property
    def pump_cost_today(self) -> float | None:
        energy = self.pump_energy_today
        price = self.energy_price
        if energy is None or price is None:
            return None
        return round(energy * price, 3)

    @property
    def timer_slots(self) -> list[tuple[int, int]]:
        return parse_timer_slots(self.conf.get(CONF_TIMER_SLOTS))

    def available_modes(self) -> list[str]:
        modes = [OperationMode.OFF, OperationMode.TIMER, OperationMode.SMART]
        if self.has(CONF_SOLAR_EXCESS_SENSOR):
            modes += [OperationMode.SOLAR, OperationMode.SMART_SOLAR]
        return [str(m) for m in modes]

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
            if valid_new and valid_old and not ours and old.state != new.state:
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
        self._closed_days.append(closed)
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
            # Passive wintering keeps the pump off on purpose: no target is missed.
            if (
                mode is not None
                and mode.guarantees_target
                and not self.winter_passive
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

    async def _async_season(self, today: date) -> None:
        """Fire the chlorinator's season events, as in 0.1.

        The cell no longer follows the calendar: it follows the season state,
        which the owner confirms (``async_set_season_state``).
        """
        if not self.is_salt:
            return
        in_season = is_chlorinator_in_season(today, self.active_months)
        if self.in_season_last is None:
            self.in_season_last = in_season
            return
        if in_season == self.in_season_last:
            return
        self.in_season_last = in_season
        event = EVENT_CHLORINATOR_SEASON_START if in_season else EVENT_CHLORINATOR_SEASON_END
        key = "season_start" if in_season else "season_end"
        message = text(self.hass.config.language, key, pool=self.pool_name)
        self.hass.bus.async_fire(
            event, {"entry_id": self.entry.entry_id, "pool": self.pool_name, "message": message}
        )
        if not self.conf.get(CONF_CHLORINATOR_AUTO_TOGGLE, True):
            # With proposals on, the season proposal's reminder replaces this one.
            await self._async_remind(text(self.hass.config.language, "title"), message)

    async def _async_season_proposal(self, now: datetime) -> None:
        """Propose the season change the calendar calls for, and bring it up
        again every week until it is confirmed or dismissed."""
        current = self.season_proposal
        if current is not None and current.get("to") not in CALENDAR_PROPOSALS:
            # The finished opening list proposes swimming, not the calendar:
            # it is brought up again every week, until confirmed or dismissed.
            if current.get("dismissed_for") != current.get("to") and self._proposal_due(
                current, now
            ):
                await self._async_announce_proposal(current, now)
                self._save()
            return
        to = None
        if self.conf.get(CONF_CHLORINATOR_AUTO_TOGGLE, True):
            to = season_proposal(now.date(), self.swimming_months, self.season_state)
        if to is None:
            if current is not None:
                self.season_proposal = None
                self._save()
            return
        is_new = current is None or current.get("to") != to
        if is_new:
            self.season_proposal = current = {
                "to": to,
                "since": now.isoformat(),
                "reminded": None,
                "dismissed_for": None,
            }
        elif current.get("dismissed_for") == to:
            return
        else:
            if not self._proposal_due(current, now):
                return
        await self._async_announce_proposal(current, now)
        if is_new:
            self._open_season_checklist(to)
        self._save()

    @staticmethod
    def _proposal_due(proposal: dict[str, Any], now: datetime) -> bool:
        """Whether a proposal has gone a week without being brought up."""
        reminded = _parse_dt(proposal.get("reminded"))
        return reminded is None or now.date() >= (
            dt_util.as_local(reminded).date() + timedelta(days=PROPOSAL_REMIND_DAYS)
        )

    async def _async_announce_proposal(self, proposal: dict[str, Any], now: datetime) -> None:
        """Fire the proposal's event and remind the owner of it."""
        to = proposal["to"]
        proposal["reminded"] = now.isoformat()
        self.hass.bus.async_fire(
            EVENT_SEASON_PROPOSAL,
            {"entry_id": self.entry.entry_id, "pool": self.pool_name, "to": to},
        )
        language = self.hass.config.language
        await self._async_remind(
            text(language, "title") + f" · {self.pool_name}",
            text(language, f"season_proposal_{to}", pool=self.pool_name),
        )

    # ──────────────────────────────────────────
    # Checklists
    # ──────────────────────────────────────────

    @property
    def equipment(self) -> set[str]:
        """The equipment flags the step lists filter by."""
        flags = set()
        if self.is_salt:
            flags.add("salt")
        if task_applies("winter_product", self.conf):
            flags.add("winter_product")
        if task_applies("ph_calibration", self.conf):
            flags.add("ph_probe")
        return flags

    def _open_season_checklist(self, to: str) -> None:
        """Open the closing list (``to`` is "winter") or the opening list
        ("opening"), unless one is already open: its progress is kept."""
        list_id = CLOSING if to == "winter" else OPENING if to == "opening" else None
        if list_id is None or list_id in self.checklists:
            return
        self.checklists[list_id] = {
            "created": dt_util.utcnow().isoformat(),
            "steps": [
                {"id": s.id, "done": None} for s in build(list_id, self.equipment)
            ],
        }

    def _prune_passive_steps(self) -> None:
        """Active wintering: the steps for a pool that sits unpowered are moot."""
        closing = self.checklists.get(CLOSING)
        if closing is None:
            return
        closing["steps"] = [
            s
            for s in closing["steps"]
            if not (d := step_def(CLOSING, s["id"])) or not d.only_passive
        ]
        self._drop_if_done(CLOSING)

    def _drop_if_done(self, list_id: str) -> bool:
        checklist = self.checklists.get(list_id)
        if checklist is None or any(s["done"] is None for s in checklist["steps"]):
            return False
        del self.checklists[list_id]
        return True

    def _closing_needs_pump(self) -> bool:
        """Passive wintering with a closing step that needs the pump still open."""
        closing = self.checklists.get(CLOSING)
        if not self.winter_passive or closing is None:
            return False
        for step in closing["steps"]:
            d = step_def(CLOSING, step["id"])
            if step["done"] is None and d is not None and d.needs_pump:
                return True
        return False

    def checklist_view(self) -> dict[str, list[dict[str, Any]]]:
        """The open lists, with their texts in Home Assistant's language."""
        language = self.hass.config.language
        view: dict[str, list[dict[str, Any]]] = {}
        for list_id, checklist in self.checklists.items():
            steps = []
            for step in checklist["steps"]:
                d = step_def(list_id, step["id"], checklist.get("treatment"))
                steps.append(
                    {
                        "id": step["id"],
                        "text": text(language, d.text_key) if d else step["id"],
                        "done": step["done"] is not None,
                        "done_at": step["done"],
                    }
                )
            view[list_id] = steps
        return view

    def has_open_step(self, step: str) -> bool:
        checklist = self.checklists.get(step.split(".", 1)[0])
        return checklist is not None and any(
            s["id"] == step for s in checklist["steps"]
        )

    async def async_complete_step(self, step: str) -> None:
        """Tick a step of an open list, and what it stands for with it."""
        list_id = step.split(".", 1)[0]
        checklist = self.checklists.get(list_id)
        entry = next((s for s in (checklist or {}).get("steps", []) if s["id"] == step), None)
        if entry is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="step_not_open",
                translation_placeholders={"step": step, "pool": self.pool_name},
            )
        if entry["done"] is not None:
            return
        entry["done"] = dt_util.utcnow().isoformat()
        d = step_def(list_id, step, checklist.get("treatment"))
        finished = self._drop_if_done(list_id)
        if finished and list_id == OPENING:
            await self._async_propose_swimming()
        else:
            self._save()
        if d is not None and d.completes_task:
            await self.async_record_action(TASKS_BY_KEY[d.completes_task].action)
        elif step == "opening.reconnect_cell":
            await self.async_set_setting("chlorinator_enabled", True)
        else:
            await self.async_refresh()

    async def async_dismiss_checklist(self, list_id: str) -> None:
        if self.checklists.pop(list_id, None) is not None:
            self._save()
            await self.async_refresh()

    async def _async_propose_swimming(self) -> None:
        """The opening list is done: propose the swimming state, which the owner confirms."""
        now = dt_util.now()
        self.season_proposal = {
            "to": SeasonState.SWIMMING.value,
            "since": now.isoformat(),
            "reminded": None,
            "dismissed_for": None,
        }
        await self._async_announce_proposal(self.season_proposal, now)
        self._save()

    def _sample_inputs(self, now: datetime) -> None:
        air = self.air_temperature
        if air is not None:
            current = self.air_max.get("today")
            if current is None or air > current:
                self.air_max["today"] = air
        ph = self.ph
        if ph is not None and (
            not self._ph_samples or now - self._ph_samples[-1][0] >= timedelta(minutes=10)
        ):
            self._ph_samples.append((now, ph))
        self.ph_trend = self._compute_ph_trend()

    def _compute_ph_trend(self) -> str | None:
        """Slope of the last three hours of readings, in pH per hour."""
        if not self.has(CONF_PH_SENSOR):
            return None
        if len(self._ph_samples) < 4:
            return PhTrend.STABLE
        latest = self._ph_samples[-1][0]
        window = [(t, v) for t, v in self._ph_samples if latest - t <= timedelta(hours=3)]
        if len(window) < 4:
            return PhTrend.STABLE
        t0 = window[0][0]
        xs = [(t - t0).total_seconds() / 3600 for t, _ in window]
        ys = [v for _, v in window]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        den = sum((x - mean_x) ** 2 for x in xs)
        if den == 0:
            return PhTrend.STABLE
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / den
        if slope > 0.03:
            return PhTrend.RISING
        if slope < -0.03:
            return PhTrend.FALLING
        return PhTrend.STABLE

    # ── target ──

    async def _async_forecast(self, now: datetime) -> None:
        """Today's high and rain from the weather entity, at most once an hour."""
        weather = self.conf.get(CONF_WEATHER_ENTITY)
        if not weather or (
            self._forecast_at is not None and now - self._forecast_at < timedelta(hours=1)
        ):
            return
        self._forecast_at = now
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather, "type": "daily"},
                blocking=True,
                return_response=True,
            )
        except Exception:  # noqa: BLE001 - weather is a nice-to-have, never a blocker
            _LOGGER.debug("%s: no daily forecast from %s", self.pool_name, weather)
            self._forecast = {}
            return
        days = ((response or {}).get(weather) or {}).get("forecast") or []
        if not days:
            self._forecast = {}
            return
        first = _todays_forecast(days, dt_util.as_local(now).date())
        self._forecast = {
            "high": first.get("temperature"),
            "rain_mm": first.get("precipitation"),
            "uv": first.get("uv_index"),
        }

    def _temperature_inputs(self) -> tuple[float | None, float | None, str]:
        """Water temperature, or the air figure to estimate it from."""
        water = self.water_temperature
        if water is not None:
            return water, None, "water_temperature_sensor"
        # What the pool's own sensor measured beats a forecast for a grid
        # cell kilometres away. Today's maximum so far, or yesterday's if that
        # was warmer: early in the morning today's is still the night's low,
        # and the target only rises as the day warms up.
        # A sensor in the sun, or on a heat pump's outdoor unit, reads well
        # above the shade temperature, and the maximum is the figure most
        # thrown by it; so with a forecast at hand the measurement may top
        # the forecast high by MEASURED_AIR_MARGIN_C at most.
        high = self._forecast.get("high")
        high = float(high) if isinstance(high, (int, float)) else None
        observed = [v for v in (self.air_max.get("today"), self.air_max.get("yesterday")) if v is not None]
        if observed:
            air = max(observed)
            if high is not None and air > high + MEASURED_AIR_MARGIN_C:
                return None, round(high + MEASURED_AIR_MARGIN_C, 1), "air_temperature_max_capped"
            return None, air, "air_temperature_max"
        if high is not None:
            return None, high, "forecast_high"
        return None, None, "none"

    def _uv(self) -> tuple[float | None, str | None]:
        value = self._number(CONF_UV_SENSOR)
        if value is not None:
            return value, "uv_sensor"
        weather = self._state(CONF_WEATHER_ENTITY)
        if weather is not None and isinstance(weather.attributes.get("uv_index"), (int, float)):
            return float(weather.attributes["uv_index"]), "weather_entity"
        uv = self._forecast.get("uv")
        if isinstance(uv, (int, float)):
            return float(uv), "forecast"
        return None, None

    async def _async_maybe_recalculate(self, now: datetime, force: bool = False) -> None:
        if (
            not force
            and self.target
            and self.target_at is not None
            and now - self.target_at < timedelta(minutes=RECALC_INTERVAL_MIN)
        ):
            return
        await self._async_forecast(now)
        result = self.calculate_target(dt_util.as_local(now).date())
        old = self.target_minutes
        if self.target and not force and result["target_minutes"] < old:
            # During a day the target only ever goes up. A target that drops in
            # the afternoon because a cloud cooled the air is what made the old
            # automations stop half way; the day's demand does not shrink.
            # calculated_minutes keeps what today's conditions ask for now,
            # so the held figure and its components can be told apart.
            result = {
                **result,
                "target_minutes": old,
                "calculated_minutes": result["target_minutes"],
                "held_at_previous": True,
            }
        self.target = result
        self.target_at = now
        if result["target_minutes"] != old:
            self.hass.bus.async_fire(
                EVENT_TARGET_RECALCULATED,
                {
                    "entry_id": self.entry.entry_id,
                    "pool": self.pool_name,
                    "old": old,
                    "new": result["target_minutes"],
                    "factors": result.get("factors", {}),
                },
            )

    def calculate_target(self, today: date) -> dict[str, Any]:
        """Run both calculators with whatever data is available right now."""
        water, air, temp_source = self._temperature_inputs()
        uv, uv_source = self._uv()
        rain_past = self._number(CONF_RAIN_SENSOR)
        rain_next = self._forecast.get("rain_mm")
        cover_on = None
        if self.conf.get(CONF_HAS_COVER) == "automatic":
            cover_state = self._state(CONF_COVER_ENTITY)
            if cover_state is not None:
                cover_on = cover_state.state == "closed"
        latitude = float(self.opt(CONF_LATITUDE, self.hass.config.latitude) or 0)

        if self.volume <= 0 or self.flow_rate <= 0:
            return {
                "target_minutes": 0,
                "target_filtration_minutes": 0,
                "target_chlorine_minutes": None,
                "warnings": ["Pool volume or pump flow rate missing"],
            }

        filt = calculate_filtration_target(
            FiltrationInputs(
                pool_volume_m3=self.volume,
                nominal_flow_rate_m3h=self.flow_rate,
                latitude=latitude,
                has_cover=self.conf.get(CONF_HAS_COVER) or "none",
                is_covered_by_roof=bool(self.conf.get(CONF_IS_COVERED_BY_ROOF)),
                cover_currently_on=cover_on,
                user_multiplier=self.user_multiplier,
                current_date=today,
                water_temperature_c=water,
                air_temperature_c=air,
                uv_index=uv,
                rain_last_24h_mm=rain_past,
                rain_next_24h_mm=float(rain_next) if isinstance(rain_next, (int, float)) else None,
            )
        )
        sources = dict(filt.sources)
        sources["temperature"] = temp_source
        if uv_source:
            sources["uv"] = uv_source
        if rain_past is not None:
            sources["rain"] = "rain_sensor"
        warnings = list(filt.warnings)

        chlorine_minutes = None
        recommended = None
        chlorine_info: dict[str, Any] = {}
        if self.is_salt and self.opt(CONF_CHLORINATOR_NOMINAL_PRODUCTION):
            salt, salt_source = self.salinity
            chlorine_kwargs: dict[str, Any] = {
                "pool_volume_m3": self.volume,
                "chlorinator_nominal_production_g_h": float(
                    self.opt(CONF_CHLORINATOR_NOMINAL_PRODUCTION)
                ),
                "chlorinator_production_pct": self.chlorinator_production,
                "chlorinator_self_regulating": self.self_regulating,
                # With "Chlorinator in use" off the cell produces nothing, so
                # it is treated as out of season and adds no minutes.
                "chlorinator_active_months": (
                    self.active_months if self.chlorinator_enabled else []
                ),
                "water_temperature_c": water,
                "air_temperature_c": air,
                "salt_level_g_l": salt,
                "salt_target_g_l": float(self.opt(CONF_SALT_TARGET, DEFAULT_SALT_TARGET)),
                "current_date": today,
                "latitude": latitude,
            }
            first = calculate_chlorine_target(ChlorineInputs(**chlorine_kwargs))
            chlorine_minutes = first.target_chlorine_minutes
            # The recommended production depends on the final target, so it is
            # worked out again once the final target is known.
            total = max(filt.target_minutes, chlorine_minutes or 0)
            second = calculate_chlorine_target(
                ChlorineInputs(**chlorine_kwargs, total_target_minutes=total)
            )
            recommended = second.recommended_production_pct
            warnings.extend(first.warnings)
            if salt_source:
                sources["salinity"] = salt_source
            chlorine_info = {
                "chlorine_demand_g": first.chlorine_demand_g_per_day,
                "effective_production_g_h": first.effective_production_g_h,
                "salinity_factor": first.salinity_factor,
                "cold_water_factor": first.cold_water_factor,
                # The calendar's answer, as before; whether the cell counted
                # shows in target_chlorine_minutes.
                "chlorinator_in_season": self.in_season,
            }

        target = max(filt.target_minutes, chlorine_minutes or 0)
        return {
            "target_minutes": target,
            "target_filtration_minutes": filt.target_minutes,
            "target_chlorine_minutes": chlorine_minutes,
            "dominant_component": (
                "chlorine" if (chlorine_minutes or 0) > filt.target_minutes else "filtration"
            ),
            "base_minutes": filt.base_minutes,
            "factors": {
                "seasonal": filt.seasonal_factor,
                "temperature": filt.temperature_factor,
                "uv": filt.uv_factor,
                "rain": filt.rain_factor,
                "cover": filt.cover_factor,
                "user_multiplier": filt.user_multiplier,
            },
            "clamped": filt.was_clamped,
            "min_minutes": filt.min_minutes,
            "max_minutes": filt.max_minutes,
            "recommended_chlorinator_pct": recommended,
            "inputs": {
                "water_temperature": water,
                "air_temperature": air,
                "uv_index": uv,
                "rain_last_24h_mm": rain_past,
                "rain_next_24h_mm": rain_next,
            },
            **chlorine_info,
            "sources": sources,
            "warnings": warnings,
        }

    # ── control ──

    def _solar_noon_minute(self) -> int:
        longitude = float(self.opt(CONF_LONGITUDE, self.hass.config.longitude) or 0)
        noon = dt_util.as_local(solar_noon_utc(dt_util.now().date(), longitude))
        return noon.hour * 60 + noon.minute

    def _minutes_until_day_end(self, now: datetime) -> int:
        local = dt_util.as_local(now)
        tomorrow = dt_util.start_of_local_day(local.date() + timedelta(days=1))
        return max(0, int((tomorrow - now).total_seconds() // 60))

    def _evaluate_safety(self, now: datetime) -> None:
        power = self._watts(CONF_PUMP_POWER_SENSOR)
        nominal = self.opt(CONF_PUMP_NOMINAL_POWER)
        anomaly = False
        if power is not None and nominal:
            nominal = float(nominal)
            if self._pump_was_on and self.pump_on_since and (
                now - self.pump_on_since >= timedelta(minutes=2)
            ):
                anomaly = power > nominal * 1.5 or power < nominal * 0.3
            elif not self._pump_was_on:
                anomaly = power > max(50.0, nominal * 0.2)
        if anomaly:
            self._anomaly_since = self._anomaly_since or now
        else:
            self._anomaly_since = None
        self.pump_anomaly = self._anomaly_since is not None and (
            now - self._anomaly_since >= timedelta(minutes=ANOMALY_MINUTES)
        )

        pressure = self.filter_pressure
        normal_max = float(self.opt(CONF_FILTER_PRESSURE_NORMAL_MAX, DEFAULT_FILTER_PRESSURE_NORMAL_MAX))
        if pressure is not None and self._pump_was_on and pressure > normal_max:
            self._pressure_high_since = self._pressure_high_since or now
        elif pressure is not None and self._pump_was_on:
            self._pressure_high_since = None
        self.pressure_high = self._pressure_high_since is not None and (
            now - self._pressure_high_since >= timedelta(minutes=10)
        )

        evaluation = evaluate_safety(
            flood_detected=self._is_on(CONF_FLOOD_SENSOR),
            equipment_room_temp_c=self._number(CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR),
            equipment_room_temp_threshold_c=float(
                self.opt(CONF_EQUIPMENT_ROOM_MAX_TEMP, DEFAULT_EQUIPMENT_ROOM_MAX_TEMP)
            ),
            filter_pressure_bar=pressure,
            filter_pressure_critical_bar=float(
                self.opt(CONF_FILTER_PRESSURE_CRITICAL, DEFAULT_FILTER_PRESSURE_CRITICAL)
            ),
        )
        reasons = [c.id for c in evaluation.active_conditions]
        if self.pump_anomaly and self._pump_was_on:
            reasons.append("pump_power_anomaly")
        self.safety_reasons = reasons
        self.safety_active = bool(reasons)

        freeze = False
        if self.conf.get(CONF_FREEZE_PROTECTION, True):
            threshold = float(self.opt(CONF_FREEZE_THRESHOLD, DEFAULT_FREEZE_THRESHOLD))
            water = self.water_temperature
            air = self._number(CONF_AIR_TEMPERATURE_SENSOR)
            if water is not None:
                freeze = water < threshold
            elif air is not None:
                freeze = air < 0
        self.freeze_active = freeze

    def _evaluate_ph(self, now: datetime) -> bool:
        """Should the pump run so the pH doser can work? Keeps the window open.

        A window opens for the configured time when the doser needs flow and
        the pump is not already running for another reason; it is extended
        while the need lasts, up to the daily cap, so the pump is not stopped
        and restarted every half hour.

        In ``off`` mode HomePool does not start the pump for the pH: only a
        window asked for through the service does. In passive wintering not
        even that: the pipes are drained. A probe reading that cannot be right
        (outside 5-9, or unchanged for a day: a probe in its cup or out of the
        water) does not start it either.
        """
        if self.winter_passive:
            self.ph_correction_active = False
            self.ph_correction_forced = False
            self.ph_window_until = None
            return False
        if self.ph_correction_forced:
            if self.ph_window_until and now < self.ph_window_until:
                # A window forced from the service runs its course regardless.
                return True
            self.ph_correction_forced = False
            self.ph_window_until = None
        if self.mode == "off":
            self.ph_correction_active = False
            self.ph_window_until = None
            return False
        needed = False
        if self._is_on(CONF_PH_DOSING_ENTITY):
            needed = True
        elif self.conf.get(CONF_HAS_PH_DOSING) and self._ph_plausible(now):
            high = float(self.opt(CONF_PH_RANGE_MAX, DEFAULT_PH_RANGE_MAX))
            # Hysteresis: start above the range, stop once back at the target.
            needed = self.ph > high or (self.ph_correction_active and self.ph > self.ph_target)
        self.ph_correction_active = needed
        cap = float(self.opt(CONF_PH_CORRECTION_MAX_DAILY, DEFAULT_PH_CORRECTION_MAX_DAILY))
        if not needed or self.ph_correction_minutes >= cap:
            self.ph_window_until = None
            return False
        if self._pump_was_on and self.started_by != "ph_correction":
            # Water is already flowing for another reason; nothing to force.
            return False
        if self.ph_window_until is None or now >= self.ph_window_until:
            minutes = float(self.opt(CONF_PH_CORRECTION_MINUTES, DEFAULT_PH_CORRECTION_MINUTES))
            self.ph_window_until = now + timedelta(minutes=minutes)
        return True

    def _ph_plausible(self, now: datetime) -> bool:
        """Is the probe's reading believable enough to run the pump for?"""
        ph = self.ph
        if ph is None:
            self._ph_seen = None
            return False
        if self._ph_seen is None or self._ph_seen[0] != ph:
            # Not kept across restarts: after one, the probe gets a fresh day.
            self._ph_seen = (ph, now)
        if not PH_PLAUSIBLE_MIN <= ph <= PH_PLAUSIBLE_MAX:
            return False
        return now - self._ph_seen[1] < timedelta(hours=PH_FROZEN_HOURS)

    async def _async_control(self, now: datetime) -> None:
        self._evaluate_safety(now)
        ph_force = self._evaluate_ph(now)

        if self.override:
            until = _parse_dt(self.override.get("until"))
            if until is None or now >= until:
                self.override = None
        if self.cycle_until and now >= self.cycle_until:
            self.cycle_until = None

        pump_power = self._watts(CONF_PUMP_POWER_SENSOR)
        if pump_power is None and self._pump_was_on and self.opt(CONF_PUMP_NOMINAL_POWER):
            pump_power = float(self.opt(CONF_PUMP_NOMINAL_POWER))
        self.surplus_w = surplus_watts(
            self._watts(CONF_SOLAR_EXCESS_SENSOR),
            self.conf.get(CONF_SOLAR_EXCESS_SIGN) or ExcessSign.EXPORT_POSITIVE,
            self._pump_was_on,
            pump_power,
        )
        solar_available = self._solar.update(
            now,
            self.surplus_w,
            self.solar_threshold,
            float(self.opt(CONF_SOLAR_IMPORT_TOLERANCE, DEFAULT_SOLAR_IMPORT_TOLERANCE_W)),
        )

        local = dt_util.as_local(now)
        mode_cls = MODE_REGISTRY.get(self.mode) or MODE_REGISTRY["off"]
        mode_decision = mode_cls().evaluate(
            PoolContext(
                target_minutes=self.target_minutes,
                elapsed_minutes=self.elapsed_minutes,
                pump_is_on=self._pump_was_on,
                minute_of_day=local.hour * 60 + local.minute,
                minutes_until_day_end=self._minutes_until_day_end(now),
                solar_noon_minute=self._solar_noon_minute(),
                solar_available=solar_available,
                timer_slots=self.timer_slots,
                end_of_day_margin=END_OF_DAY_MARGIN_MIN,
            )
        )
        minutes_in_state = (
            (now - self.pump_changed_at).total_seconds() / 60 if self.pump_changed_at else None
        )
        hands_off = self._is_on(CONF_HANDS_OFF_ENTITY) is True
        decision = arbitrate(
            ControlInputs(
                pump_available=self.pump_available,
                pump_is_on=self._pump_was_on,
                minutes_in_state=minutes_in_state,
                hands_off=hands_off,
                maintenance_lock=self.maintenance_lock,
                winter_passive=self.winter_passive,
                safety_shutoff=self.safety_active,
                safety_reason=", ".join(self.safety_reasons) or None,
                # The alert still tells of the frost; the pump is not run.
                freeze_risk=self.freeze_active and not self.winter_passive,
                ph_correction=ph_force,
                manual_cycle=self.cycle_until is not None,
                manual_override=self.override.get("state") if self.override else None,
                manual_override_by=(self.override or {}).get("by") or "user",
                manual_override_name=(self.override or {}).get("name"),
                mode_decision=mode_decision,
                started_by=self.started_by,
                min_on_minutes=MIN_ON_MINUTES,
                min_off_minutes=MIN_OFF_MINUTES,
            )
        )
        self.decision_source = decision.source
        self.decision_key = decision.key
        self.decision_reason = reason_text(
            self.hass.config.language, decision.key, decision.args, decision.reason
        )

        # The cell first: it must already be off when the pump stops.
        pump_will_be_on = self._pump_was_on if decision.pump is None else decision.pump
        await self._async_control_chlorinator(now, pump_will_be_on)

        if decision.pump is not None and decision.pump != self._pump_was_on:
            if not decision.pump and self._is_on(CONF_CHLORINATOR_SWITCH) is True:
                # Do not stop the pump while the cell is still on: it has just
                # been told to stop, and its state change brings us back here.
                # A cell that ignores every retry must not keep the pump
                # running for ever, through a flood included: once its retries
                # are spent the pump stops anyway, and an alert says why.
                cell = self._pending.get(CONF_CHLORINATOR_SWITCH)
                cell_gave_up = (
                    cell is not None
                    and cell["attempts"] >= COMMAND_MAX_ATTEMPTS
                    and cell["sent"] is not None
                    and now - cell["sent"] >= timedelta(seconds=COMMAND_RETRY_S)
                )
                if not cell_gave_up:
                    await self._async_retry(now)
                    return
            if decision.pump:
                self.started_by = decision.source
            await self._async_command(CONF_PUMP_SWITCH, decision.pump)
        elif decision.pump is None or decision.pump == self._pump_was_on:
            pending = self._pending.get(CONF_PUMP_SWITCH)
            if pending and (decision.pump is None or pending["state"] != decision.pump):
                self._pending.pop(CONF_PUMP_SWITCH, None)
        await self._async_retry(now)

    async def _async_control_chlorinator(self, now: datetime, pump_will_be_on: bool) -> None:
        if not self.conf.get(CONF_CHLORINATOR_SWITCH):
            self.chlorinator_reason = ""
            return
        on_seconds = (
            (now - self.pump_on_since).total_seconds()
            if self._pump_was_on and self.pump_on_since
            else None
        )
        wanted, reason = chlorinator_wanted(
            ChlorinatorInputs(
                has_switch=True,
                pump_is_on=self._pump_was_on and pump_will_be_on,
                pump_on_seconds=on_seconds,
                enabled=self.chlorinator_enabled,
                in_season=self.in_season,
                target_reached=self.chlorine_target_reached,
                blocked=self.maintenance_lock or self.safety_active or self.winter_passive,
                water_temperature_c=self.water_temperature,
                min_water_temperature_c=float(
                    self.opt(CONF_CHLORINATOR_MIN_WATER_TEMP, DEFAULT_CHLORINATOR_MIN_WATER_TEMP)
                ),
                flow_delay_s=CHLORINATOR_FLOW_DELAY_S,
            )
        )
        self.chlorinator_reason = reason
        if self._is_on(CONF_CHLORINATOR_SWITCH) is None:
            return
        if wanted != self._chlor_was_on:
            await self._async_command(CONF_CHLORINATOR_SWITCH, wanted)

    async def _async_command(self, key: str, turn_on: bool) -> None:
        entity_id = self.conf.get(key)
        if not entity_id:
            return
        pending = self._pending.get(key)
        if pending and pending["state"] == turn_on:
            return  # already asked; the retry loop takes it from here
        self._pending[key] = {
            "state": turn_on,
            "attempts": 0,
            "sent": None,
            "first_sent": dt_util.utcnow(),
        }
        await self._async_send(key)

    async def _async_send(self, key: str) -> None:
        pending = self._pending[key]
        context = Context()
        self._own_contexts.append(context.id)
        pending["attempts"] += 1
        pending["sent"] = dt_util.utcnow()
        service = "turn_on" if pending["state"] else "turn_off"
        _LOGGER.debug(
            "%s: %s %s (attempt %d)", self.pool_name, service, self.conf[key], pending["attempts"]
        )
        self._unsubs.append(
            async_call_later(self.hass, COMMAND_RETRY_S + 1, self._retry_due)
        )
        try:
            await self.hass.services.async_call(
                "homeassistant",
                service,
                {"entity_id": self.conf[key]},
                blocking=False,
                context=context,
            )
        except Exception as err:  # noqa: BLE001 - retried below, and alerted if it persists
            _LOGGER.warning("%s: %s %s failed: %s", self.pool_name, service, self.conf[key], err)

    @callback
    def _retry_due(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_retry(self, now: datetime) -> None:
        """Send a command again if the switch has not followed it."""
        for key, pending in list(self._pending.items()):
            actual = self._is_on(key)
            if actual is None:
                continue  # unavailable: wait, do not keep firing
            if actual == pending["state"]:
                self._pending.pop(key, None)
                await self._async_clear(
                    "pump_not_responding" if key == CONF_PUMP_SWITCH else "chlorinator_not_responding"
                )
                continue
            if pending["sent"] and now - pending["sent"] < timedelta(seconds=COMMAND_RETRY_S):
                continue
            if pending["attempts"] >= COMMAND_MAX_ATTEMPTS:
                alert = (
                    "pump_not_responding" if key == CONF_PUMP_SWITCH else "chlorinator_not_responding"
                )
                await self._async_raise(
                    alert,
                    Severity.CRITICAL,
                    {
                        "attempts": pending["attempts"],
                        "state": "on" if pending["state"] else "off",
                    },
                )
                continue
            await self._async_send(key)

    # ── alerts ──

    async def _async_raise(
        self,
        alert: str,
        severity: str,
        values: dict[str, Any],
        once: bool = False,
        reminder: bool = False,
        text_key: str | None = None,
        notify: bool = True,
    ) -> None:
        """Raise an alert on its rising edge: event, and notification if enabled.

        ``reminder`` marks an alert that asks the owner to do something: it is
        notified whatever the severity floor, after the quiet hours if need be.
        ``text_key`` picks another wording for the same alert; ``notify``
        False raises it without a notification.
        """
        if alert in self.alerts and not once:
            return
        message = text(
            self.hass.config.language, text_key or alert, pool=self.pool_name, **values
        )
        if not once:
            self.alerts[alert] = {
                "severity": severity,
                "message": message,
                "since": dt_util.utcnow().isoformat(),
            }
            self._alert_text_keys[alert] = text_key or alert
        payload = {
            "entry_id": self.entry.entry_id,
            "pool": self.pool_name,
            "type": alert,
            "severity": severity,
            "message": message,
            "context": values,
        }
        self.hass.bus.async_fire(EVENT_ALERT, payload)
        if alert == "safety_shutoff":
            self.hass.bus.async_fire(
                EVENT_SAFETY_SHUTOFF,
                {
                    "entry_id": self.entry.entry_id,
                    "pool": self.pool_name,
                    "reason": values.get("reason"),
                    "conditions": self.safety_reasons,
                },
            )
        title = text(self.hass.config.language, "title") + f" · {self.pool_name}"
        if not notify:
            return
        if reminder:
            await self._async_remind(title, message)
        elif self.notifier:
            await self.notifier.async_send(title, message, severity, dt_util.now())

    async def _async_remind(self, title: str, message: str) -> None:
        """Notify a reminder now, or keep it until the quiet hours end."""
        if not self.notifier or not self.notifier.service:
            return
        now = dt_util.now()
        if self.notifier.quiet(now):
            entry = {"title": title, "message": message}
            if entry not in self.pending_reminders:
                self.pending_reminders.append(entry)
            del self.pending_reminders[:-REMINDERS_KEPT]
            return
        await self.notifier.async_send(title, message, Severity.INFO, now, reminder=True)

    async def _async_flush_reminders(self, now: datetime) -> None:
        if not self.pending_reminders:
            return
        if not self.notifier or not self.notifier.service:
            self.pending_reminders = []
            return
        if self.hass.state is not CoreState.running:
            # Still starting: the notify service may not be registered yet.
            return
        local = dt_util.as_local(now)
        if self.notifier.quiet(local):
            return
        pending, self.pending_reminders = self.pending_reminders, []
        for reminder in pending:
            await self.notifier.async_send(
                reminder["title"], reminder["message"], Severity.INFO, local, reminder=True
            )

    async def _async_clear(self, alert: str) -> None:
        self.alerts.pop(alert, None)
        self._alert_text_keys.pop(alert, None)

    async def _async_set(
        self, alert: str, active: bool, severity: str, values: dict[str, Any] | None = None
    ) -> None:
        if active:
            await self._async_raise(alert, severity, values or {})
        else:
            await self._async_clear(alert)

    async def _async_freeze_alert(self) -> None:
        """Freeze risk, worded by whether HomePool can actually run the pump.

        A rung above freeze protection (lock, safety, hands-off, no pump)
        keeps the pump as it is; the alert then says so instead of claiming
        the pump is running, and is raised again if that changes mid-frost.
        """
        if not self.freeze_active:
            await self._async_clear("freeze_protection")
            return
        values: dict[str, Any] = {}
        if self.winter_passive:
            # The pump is never run in passive wintering: the plugs and the
            # gizmos are what protect the pipes.
            text_key = "freeze_protection_passive"
        elif self.decision_source in FREEZE_BLOCKERS:
            text_key = "freeze_protection_blocked"
            values = {"reason": self.decision_reason or ""}
        else:
            text_key = "freeze_protection"
        current = self.alerts.get("freeze_protection")
        if current and self._alert_text_keys.get("freeze_protection") != text_key:
            if text_key == "freeze_protection":
                # Running again: correct the text without another notification.
                current["message"] = text(
                    self.hass.config.language, text_key, pool=self.pool_name
                )
                self._alert_text_keys["freeze_protection"] = text_key
                return
            # Newly kept off in a frost: worth telling whoever is notified.
            await self._async_clear("freeze_protection")
        await self._async_raise(
            "freeze_protection", Severity.WARNING, values, text_key=text_key
        )

    async def _async_alerts(self, now: datetime) -> None:
        await self._async_set(
            "safety_shutoff",
            self.safety_active,
            Severity.CRITICAL,
            {"reason": ", ".join(self.safety_reasons)},
        )
        await self._async_freeze_alert()
        await self._async_set("closing_needs_pump", self._closing_needs_pump(), Severity.WARNING)
        ph = self.ph
        await self._async_set(
            "ph_out_of_range",
            self.ph_out_of_range,
            Severity.WARNING,
            {
                "value": ph or 0,
                "low": float(self.opt(CONF_PH_RANGE_MIN, DEFAULT_PH_RANGE_MIN)),
                "high": float(self.opt(CONF_PH_RANGE_MAX, DEFAULT_PH_RANGE_MAX)),
            },
        )
        if self.is_salt:
            in_season_on = (
                self.season_state == SeasonState.SWIMMING and self.chlorinator_enabled
            )
            salt, _ = self.salinity
            low = float(self.opt(CONF_SALT_RANGE_MIN, DEFAULT_SALT_RANGE_MIN))
            # Salt only matters while the cell is working: out of season an old
            # manual reading must not keep the alert on all winter.
            await self._async_set(
                "salt_low",
                in_season_on and salt is not None and salt < low,
                Severity.WARNING,
                {"value": salt or 0, "low": low},
            )
            water = self.water_temperature
            cold = (
                in_season_on
                and water is not None
                and water
                < float(self.opt(CONF_CHLORINATOR_MIN_WATER_TEMP, DEFAULT_CHLORINATOR_MIN_WATER_TEMP))
            )
            await self._async_set("chlorinator_cold", cold, Severity.WARNING, {"value": water or 0})
            not_producing = (
                in_season_on
                and self.target.get("effective_production_g_h") == 0
                and not cold
            )
            await self._async_set("chlorinator_not_producing", bool(not_producing), Severity.WARNING)

        today = dt_util.now().date().isoformat()
        tasks = self.task_status()
        for task in tasks:
            name = task["task"]
            alert = f"{name}_due"
            if task["overdue"]:
                # Alerts are not kept across restarts: the reminder goes out
                # once a day, not again after every reload.
                first_today = self.due_notified.get(name) != today
                await self._async_raise(
                    alert, Severity.INFO, {}, reminder=True, notify=first_today
                )
                if first_today:
                    self.due_notified[name] = today
                    self.hass.bus.async_fire(
                        EVENT_MANUAL_ACTION_DUE,
                        {
                            "entry_id": self.entry.entry_id,
                            "pool": self.pool_name,
                            "action_type": name,
                            "last_done": task["last_done"],
                        },
                    )
            else:
                await self._async_clear(alert)
        # A task that is gone (switched off in the options, or its equipment
        # removed) takes its reminder with it.
        listed = {t["task"] for t in tasks}
        for defn in TASKS:
            if defn.key not in listed:
                await self._async_clear(f"{defn.key}_due")
                self.due_notified.pop(defn.key, None)

    # ──────────────────────────────────────────
    # Actions from entities and services
    # ──────────────────────────────────────────

    async def async_set_setting(self, key: str, value: Any) -> None:
        self.settings[key] = value
        if key in ("user_multiplier", "chlorinator_production", "chlorinator_enabled"):
            await self._async_maybe_recalculate(dt_util.utcnow(), force=True)
        if key == "chlorinator_production":
            await self._async_push_production(value)
        if key == "mode":
            # A new mode starts from its own decision, not from a held-over one.
            self.override = None
        self._save()
        await self.async_refresh()

    async def async_set_season_state(self, state: str) -> None:
        """The owner confirms a season state, from the select or the service."""
        new = SeasonState(state)
        old = self.season_state
        self.settings["season_state"] = new.value
        if new == SeasonState.SWIMMING:
            self.settings["chlorinator_enabled"] = True
        elif new in WINTER_STATES:
            self.settings["chlorinator_enabled"] = False
        self.season_proposal = None
        if new == SeasonState.WINTER_PASSIVE:
            # The pump never starts in passive wintering: nothing may be left running.
            self.cycle_until = None
            self.override = None
        if new != old:
            if new in WINTER_STATES and old not in WINTER_STATES:
                self.winter_entered = dt_util.utcnow()
                # An opening list left open belongs to a season that is over.
                self.checklists.pop(OPENING, None)
                self._open_season_checklist("winter")
            elif new == SeasonState.OPENING:
                self.checklists.pop(CLOSING, None)
                self._open_season_checklist("opening")
        if new == SeasonState.WINTER_ACTIVE:
            self._prune_passive_steps()
        if new != old:
            self.hass.bus.async_fire(
                EVENT_SEASON_STATE_CHANGED,
                {
                    "entry_id": self.entry.entry_id,
                    "pool": self.pool_name,
                    "old": str(old),
                    "new": new.value,
                },
            )
        await self._async_maybe_recalculate(dt_util.utcnow(), force=True)
        self._save()
        await self.async_refresh()

    async def async_dismiss_season_proposal(self) -> None:
        """Not now: the proposal is not brought up again until the calendar
        calls for another change."""
        if self.season_proposal is not None:
            self.season_proposal["dismissed_for"] = self.season_proposal["to"]
        self._save()
        await self.async_refresh()

    @property
    def season_proposal_shown(self) -> str | None:
        """The change proposed and not dismissed, if any."""
        proposal = self.season_proposal
        if proposal is None or proposal.get("dismissed_for") == proposal.get("to"):
            return None
        return proposal.get("to")

    async def _async_push_production(self, value: float) -> None:
        entity_id = self.conf.get(CONF_CHLORINATOR_PRODUCTION_ENTITY)
        if not entity_id or not self.conf.get(CONF_CHLORINATOR_CONTROLLABLE):
            return
        domain = entity_id.split(".")[0]
        try:
            if domain in ("number", "input_number"):
                await self.hass.services.async_call(
                    domain, "set_value", {"entity_id": entity_id, "value": value}, blocking=False
                )
            elif domain in ("select", "input_select"):
                state = self.hass.states.get(entity_id)
                options = (state.attributes.get("options") if state else None) or []
                numeric = []
                for option in options:
                    try:
                        numeric.append((abs(float(str(option).rstrip("% ")) - value), option))
                    except ValueError:
                        continue
                if numeric:
                    await self.hass.services.async_call(
                        domain,
                        "select_option",
                        {"entity_id": entity_id, "option": min(numeric)[1]},
                        blocking=False,
                    )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("%s: could not set production on %s", self.pool_name, entity_id)

    async def async_start_cycle(self, minutes: float | None = None) -> None:
        if self.winter_passive:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="cycle_in_winter_passive"
            )
        duration = minutes or self.cycle_duration or 60
        self.cycle_until = dt_util.utcnow() + timedelta(minutes=float(duration))
        self.override = None
        self._save()
        await self.async_refresh()

    async def async_stop_cycle(self) -> None:
        """Stop a manual cycle, and stop the pump now if nothing else needs it."""
        self.cycle_until = None
        until = dt_util.utcnow() + timedelta(
            minutes=float(self.opt(CONF_MANUAL_OVERRIDE_MINUTES, DEFAULT_MANUAL_OVERRIDE_MINUTES))
        )
        self.override = {"state": False, "until": until.isoformat()}
        self._save()
        await self.async_refresh()

    async def async_set_pump(self, turn_on: bool) -> None:
        """The HomePool pump switch: a manual action that respects the ladder."""
        if turn_on:
            await self.async_start_cycle(self.remaining_minutes or self.cycle_duration)
        else:
            await self.async_stop_cycle()

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
        self._save()
        await self.async_refresh()

    async def async_record_reading(self, kind: str, value: float) -> None:
        now = dt_util.utcnow()
        self.manual_readings[kind] = {"value": value, "at": now.isoformat()}
        self.actions = [
            *self.actions,
            {"type": f"{kind}_reading", "at": now.isoformat(), "value": value, "notes": None},
        ][-ACTIONS_KEPT:]
        if kind == "salt":
            await self._async_maybe_recalculate(now, force=True)
        self._save()
        await self.async_refresh()

    async def async_recalculate(self) -> None:
        self._forecast_at = None
        await self._async_maybe_recalculate(dt_util.utcnow(), force=True)
        self._save()
        await self.async_refresh()

    async def async_force_ph_window(self, minutes: float | None = None) -> None:
        duration = minutes or float(
            self.opt(CONF_PH_CORRECTION_MINUTES, DEFAULT_PH_CORRECTION_MINUTES)
        )
        self.ph_window_until = dt_util.utcnow() + timedelta(minutes=float(duration))
        self.ph_correction_forced = True
        self._save()
        await self.async_refresh()

    async def async_reset_daily(self) -> None:
        self._account(dt_util.utcnow())
        self.elapsed_s = 0.0
        self.chlorine_s = 0.0
        self.ph_correction_s = 0.0
        self.energy_baseline = None
        await self._async_maybe_recalculate(dt_util.utcnow(), force=True)
        self._save()
        await self.async_refresh()

    # ──────────────────────────────────────────
    # For entities and the card
    # ──────────────────────────────────────────

    def own_entities(self) -> dict[str, str]:
        """HomePool's own entities for this pool, by key: the card's index."""
        from homeassistant.helpers import entity_registry as er

        prefix = f"{self.entry.entry_id}_"
        return {
            entry.unique_id[len(prefix):]: entry.entity_id
            for entry in er.async_entries_for_config_entry(er.async_get(self.hass), self.entry.entry_id)
            if entry.unique_id.startswith(prefix)
        }

    def card_attributes(self) -> dict[str, Any]:
        """What the companion card needs beyond the entity states."""
        conf = self.conf
        return {
            "pool_entities": self.own_entities(),
            "shape": conf.get("shape"),
            "dimensions": {
                k: conf.get(k)
                for k in (
                    "side", "length", "width", "diameter",
                    "length_1", "width_1", "length_2", "width_2",
                    "depth_min", "depth_max",
                )
                if conf.get(k) is not None
            },
            "layout_variant": conf.get("layout_variant"),
            "layout_orientation": conf.get("layout_orientation"),
            "liner_color": conf.get("liner_color"),
            "volume_m3": self.volume,
            "skimmers": conf.get("skimmers_count"),
            "returns": conf.get("returns_count"),
            "has_autofill_skimmer": conf.get("has_autofill_skimmer"),
            "lights": conf.get("light_entities") or [],
            "entities": {
                key: conf.get(key)
                for key in (
                    CONF_PUMP_SWITCH,
                    CONF_CHLORINATOR_SWITCH,
                    CONF_PH_SENSOR,
                    CONF_WATER_TEMPERATURE_SENSOR,
                    CONF_AIR_TEMPERATURE_SENSOR,
                    CONF_ORP_SENSOR,
                    CONF_SALINITY_SENSOR,
                    CONF_FILTER_PRESSURE_SENSOR,
                    CONF_PUMP_POWER_SENSOR,
                    CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR,
                    CONF_EQUIPMENT_ROOM_HUMIDITY_SENSOR,
                    CONF_COVER_ENTITY,
                )
                if conf.get(key)
            },
        }
