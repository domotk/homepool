"""Water treatments: shock, clarifier, flocculant and their phases.

A mixin of ``PoolCoordinator``; see coordinator.py.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_CHLORINATOR_CONTROLLABLE,
    CONF_CHLORINATOR_PRODUCTION_ENTITY,
    CONF_CLARIFIER_DOSE_PER_10M3,
    CONF_CLARIFIER_DOSE_UNIT,
    CONF_FLOCCULANT_DOSE_PER_10M3,
    CONF_FLOCCULANT_DOSE_UNIT,
    CONF_FREE_CHLORINE_SENSOR,
    CONF_SHOCK_CONCENTRATION,
    CONF_SHOCK_PRODUCT,
    DEFAULT_DOSE_UNIT,
    DEFAULT_SHOCK_PRODUCT,
    DOMAIN,
    EVENT_TREATMENT_ENDED,
    EVENT_TREATMENT_PHASE,
    EVENT_TREATMENT_STARTED,
    Severity,
)
from ..pool.checklists import TREATMENT, build
from ..pool.dosing import SHOCK_DEFAULT_CONCENTRATION, Dose, label_dose, shock_dose
from ..pool.treatment import PHASES, Phase, TreatmentType, next_phase, phase_done, phase_hours
from ..pool.tasks import FILTER_TASKS, TASKS_BY_KEY
from .common import _iso, _parse_dt


# Vacuuming waits for the owner: an alert this long into it, then daily.
VACUUMING_REMINDER_FIRST = timedelta(hours=3)
VACUUMING_REMINDER_EVERY = timedelta(days=1)
# The closing and opening steps a finished shock ticks.
SHOCK_STEPS = ("closing.shock", "opening.shock")
# Per treatment that doses by the label: the options with its dose and unit.
LABEL_DOSE_OPTIONS = {
    TreatmentType.CLARIFIER: (CONF_CLARIFIER_DOSE_PER_10M3, CONF_CLARIFIER_DOSE_UNIT),
    TreatmentType.FLOCCULANT: (CONF_FLOCCULANT_DOSE_PER_10M3, CONF_FLOCCULANT_DOSE_UNIT),
}


class TreatmentMixin:
    """Water treatments: shock, clarifier, flocculant and their phases."""

    @property
    def treatment_phase(self) -> Phase | None:
        return Phase(self.treatment["phase"]) if self.treatment else None

    def _treatment_dose(self, kind: TreatmentType, severity: str) -> Dose:
        if kind == TreatmentType.SHOCK:
            product = self.opt(CONF_SHOCK_PRODUCT, DEFAULT_SHOCK_PRODUCT)
            concentration = float(
                self.opt(CONF_SHOCK_CONCENTRATION, SHOCK_DEFAULT_CONCENTRATION[product])
            )
            return shock_dose(product, concentration, self.volume, severity)
        dose_key, unit_key = LABEL_DOSE_OPTIONS[kind]
        per_10m3 = self.opt(dose_key)
        return label_dose(
            kind.value,
            None if per_10m3 is None else float(per_10m3),
            self.opt(unit_key, DEFAULT_DOSE_UNIT),
            self.volume,
        )

    def _treatment_event(self, event: str, kind: str, **data: Any) -> None:
        self.hass.bus.async_fire(
            event, {"entry_id": self.entry.entry_id, "pool": self.pool_name, "type": kind, **data}
        )

    async def _async_treatment_clock(self, now: datetime) -> None:
        """Move to the next phase once this one has counted its hours.

        Runs before the ladder, so the pump follows the new phase in the
        same evaluation. Shock and clarifier end with their only phase; the
        flocculant's settling gives way to vacuuming, which waits for the owner.
        """
        t = self.treatment
        if t is not None and phase_done(
            Phase(t["phase"]), t.get("hours"), float(t.get("counted_s", 0))
        ):
            await self._async_next_phase(now)

    async def _async_next_phase(self, now: datetime) -> None:
        t = self.treatment
        kind = TreatmentType(t["type"])
        following = next_phase(kind, Phase(t["phase"]))
        if following is None:
            await self._async_finish_treatment(now)
            return
        t.update(
            phase=following.value,
            phase_started=now.isoformat(),
            counted_s=0.0,
            hours=phase_hours(kind, following, t.get("requested_hours")),
        )
        self._treatment_event(EVENT_TREATMENT_PHASE, kind.value, phase=following.value)

    async def _async_finish_treatment(self, now: datetime, cut_short: bool = False) -> None:
        """End the treatment: the cell's production back, the backwash due and,
        after a shock, its closing or opening step ticked.

        ``cut_short`` (passive wintering) only stops it: the treatment did not
        run, so it leaves nothing due, the shock step stays open and its own
        step list goes.
        """
        t, self.treatment = self.treatment, None
        # Nothing asked of HomePool during the treatment acts after it: a
        # cycle or a hold left from vacuuming would switch the pump on its own.
        self.cycle_until = None
        self.override = None
        if t.get("previous_production") is not None:
            # The setting as it is now, in case the owner changed it meanwhile.
            await self._async_push_production(self.chlorinator_production)
        if not cut_short:
            # A backwash (or a filter cleaning) done during the treatment,
            # from its step list, already took out what it left in the filter.
            started = _parse_dt(t.get("started"))
            cleaned = [
                _parse_dt(self.tasks.get(TASKS_BY_KEY[key].action)) for key in FILTER_TASKS
            ]
            if started is None or not any(c is not None and c >= started for c in cleaned):
                self.backwash_after_treatment = True
            if t["type"] == TreatmentType.SHOCK:
                self.after_shock_since = now
                await self._async_tick_shock_steps()
        else:
            # Its steps belong to a treatment that is no longer running.
            self.checklists.pop(TREATMENT, None)
        await self._async_clear("treatment_frost")
        self._treatment_event(
            EVENT_TREATMENT_ENDED, t["type"], started=t["started"], ended=now.isoformat()
        )

    async def _async_tick_shock_steps(self) -> None:
        """A shock done is the shock step of an open closing or opening list."""
        for step in SHOCK_STEPS:
            list_id = step.split(".", 1)[0]
            steps = self.checklists.get(list_id, {}).get("steps", [])
            entry = next((s for s in steps if s["id"] == step), None)
            if entry is not None and entry["done"] is None:
                await self._async_tick_step(list_id, entry)

    async def _async_treatment_alerts(self) -> None:
        """A frost interrupting the flocculant's settling; vacuuming left
        waiting; a probe back in range after a shock."""
        frost = (
            self.treatment_phase == Phase.SETTLING
            and self.decision_source == "freeze_protection"
        )
        if frost:
            self.treatment["frost_interrupted"] = True
        await self._async_set("treatment_frost", frost, Severity.WARNING)
        await self._async_vacuuming_alert()
        probe = self._number(CONF_FREE_CHLORINE_SENSOR)
        if probe is not None:
            self._note_free_chlorine(probe)

    def _note_free_chlorine(self, value: float) -> None:
        """Measured back inside the range after a shock: fit to swim again."""
        if self.after_shock_since is not None and not self._outside("free_chlorine", value):
            self.after_shock_since = None

    async def _async_vacuuming_alert(self) -> None:
        """Vacuuming never ends by itself, and meanwhile nothing filters the
        pool: 3 h into it that is an alert, raised again and notified once a
        day. The time of the last one is kept with the treatment, so a
        restart raises it without notifying it again."""
        t = self.treatment
        if t is None or self.treatment_phase != Phase.VACUUMING:
            await self._async_clear("treatment_vacuuming")
            return
        now = dt_util.utcnow()
        reminded = _parse_dt(t.get("vacuuming_reminded"))
        if reminded is None:
            started = _parse_dt(t.get("phase_started")) or now
            if now - started < VACUUMING_REMINDER_FIRST:
                return
            due = True
        else:
            due = now - reminded >= VACUUMING_REMINDER_EVERY
        if due:
            t["vacuuming_reminded"] = now.isoformat()
            self._save()
            # Raised anew: the event and the notification go out again.
            await self._async_clear("treatment_vacuuming")
        # Not due, it was raised before: after a reload it is only put back,
        # with no event and no notification.
        await self._async_raise(
            "treatment_vacuuming", Severity.WARNING, {}, reminder=True, notify=due, event=due
        )

    def _require_treatment(self) -> None:
        if self.treatment is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_treatment",
                translation_placeholders={"pool": self.pool_name},
            )

    def treatment_view(self) -> dict[str, Any]:
        """The water treatment sensor's attributes."""
        t = self.treatment or {}
        until = None
        hours = t.get("hours")
        if hours is not None:
            left = max(0.0, hours * 3600 - float(t.get("counted_s", 0)))
            # To the minute: the estimate is stable while the clock runs, and
            # every change of it would be another row in the recorder.
            until = (dt_util.utcnow() + timedelta(seconds=left)).replace(second=0, microsecond=0)
        return {
            "phase": t.get("phase"),
            "phase_until": _iso(until),
            "started_at": t.get("started"),
            "dose": t.get("dose"),
            "severity": t.get("severity"),
            "frost_interrupted": bool(t.get("frost_interrupted", False)),
        }

    @property
    def swimming_not_advised(self) -> str | None:
        """Why the water is not for swimming now, or None."""
        if self.treatment is not None:
            return "treatment"
        if self.after_shock_since is not None:
            return "after_shock"
        value, _ = self.free_chlorine
        _, high = self.reading_range("free_chlorine")
        if value is not None and high is not None and value > high:
            return "free_chlorine_high"
        return None

    def _refuse_during_treatment(self) -> None:
        """While a treatment runs it decides the pump, in every phase: a cycle
        or a hold asked of HomePool would wait below it, then outlive it and
        act on its own afterwards. While vacuuming the pump is the owner's,
        at its own switch, perhaps with the valve still on waste."""
        phase = self.treatment_phase
        if phase is None:
            return
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key=(
                "pump_in_owner_hands" if phase == Phase.VACUUMING else "pump_in_treatment"
            ),
            translation_placeholders={"pool": self.pool_name},
        )

    def check_can_start_treatment(self) -> None:
        """Refuse a treatment in passive wintering, or while another runs."""
        if self.winter_passive or self.treatment is not None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="treatment_not_allowed",
                translation_placeholders={"pool": self.pool_name},
            )

    async def async_start_treatment(
        self, kind: str, severity: str = "green", hours: float | None = None
    ) -> None:
        """Start a shock, a clarifier or a flocculant, with its dose and its step list."""
        self.check_can_start_treatment()
        kind = TreatmentType(kind)
        now = dt_util.utcnow()
        self._account(now)
        phase = PHASES[kind][0]
        dose = asdict(self._treatment_dose(kind, severity))
        self.treatment = {
            "type": kind.value,
            "severity": severity if kind == TreatmentType.SHOCK else None,
            "phase": phase.value,
            "phase_started": now.isoformat(),
            "counted_s": 0.0,
            "hours": phase_hours(kind, phase, hours),
            "requested_hours": hours,
            "started": now.isoformat(),
            "dose": dose,
            "frost_interrupted": False,
        }
        # The treatment is above it on the ladder; an old one must not
        # outlive it once the treatment ends. Nor a pH window asked for before.
        self.override = None
        self.ph_correction_forced = False
        self.ph_window_until = None
        # A new treatment starts a new list, whatever was left of the last one.
        self.checklists[TREATMENT] = {
            "created": now.isoformat(),
            "treatment": kind.value,
            "dose": dose,
            "steps": [
                {"id": s.id, "done": None} for s in build(TREATMENT, self.equipment, kind.value)
            ],
        }
        if (
            kind == TreatmentType.SHOCK
            and self.is_salt
            and self.chlorinator_enabled
            and self.conf.get(CONF_CHLORINATOR_PRODUCTION_ENTITY)
            and self.conf.get(CONF_CHLORINATOR_CONTROLLABLE)
        ):
            self.treatment["previous_production"] = self.chlorinator_production
            await self._async_push_production(100)
        self._treatment_event(
            EVENT_TREATMENT_STARTED,
            kind.value,
            severity=self.treatment["severity"],
            hours=self.treatment["hours"],
            dose=dose,
        )
        self._save()
        await self.async_refresh()

    async def async_advance_treatment(self) -> None:
        """The next phase now; at the last one (vacuuming done), the end."""
        self._require_treatment()
        now = dt_util.utcnow()
        self._account(now)
        await self._async_next_phase(now)
        self._save()
        await self.async_refresh()

    async def async_end_treatment(self) -> None:
        self._require_treatment()
        now = dt_util.utcnow()
        self._account(now)
        await self._async_finish_treatment(now)
        self._save()
        await self.async_refresh()
