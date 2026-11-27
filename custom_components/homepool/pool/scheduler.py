"""Who gets to decide what the pump does, and the surplus debouncer.

Pure Python, no Home Assistant. The coordinator gathers the facts, this module
decides, and the coordinator carries the decision out. Keeping the decision
here is what lets the tests drive a whole simulated day minute by minute.

Authority over the pump, highest first:

1. **Hands off** — an external entity says nobody touches the pump. HomePool
   neither switches it on nor off, it only keeps counting.
2. **Maintenance lock** — forces it off.
3. **Passive wintering** — the pool is closed with its pipes drained and
   plugged. Forces it off, like the lock: a pump started by hand is stopped
   again, because running it dry can damage the motor. Only hands-off, above,
   lets someone run it.
4. **Safety shutoff** — flood, overheat, filter pressure, a pump drawing far
   more than it should. Forces it off.
5. **Freeze protection** — water near freezing. Forces it *on*: moving water
   does not freeze in the pipes, still water does.
6. **Water treatment** — a shock, a clarifier or a flocculant the owner
   started. On while it filters or mixes, off while the flocculant settles,
   and left as it is while the owner vacuums. A person asked for it, so it
   runs in ``off`` mode too.
7. **pH correction** — the dosing pump only works with water flowing, so a pH
   that needs correcting forces the pump on for a while, capped per day so a
   faulty probe cannot run it all night.
8. **Manual cycle** — a cycle started from HomePool (button or service).
9. **Manual override** — someone switched the pump by hand, outside HomePool.
   Respected for a while instead of being undone on the next tick.
10. **The operation mode.**

The last two are also subject to minimum on and off times: the motor and the
relay both last longer when they are not cycled every few minutes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from ..modes.base import PumpAction, PumpDecision


@dataclass
class ControlInputs:
    """Everything the arbiter needs, already reduced to booleans and minutes."""

    pump_available: bool
    pump_is_on: bool
    # Minutes since the pump last changed state, None if unknown.
    minutes_in_state: float | None

    hands_off: bool = False
    maintenance_lock: bool = False
    winter_passive: bool = False
    safety_shutoff: bool = False
    safety_reason: str | None = None
    freeze_risk: bool = False
    # What a running treatment wants of the pump, None meaning "leave it",
    # and the phase's reason key. An empty key means no treatment.
    treatment: bool | None = None
    treatment_key: str = ""

    ph_correction: bool = False

    manual_cycle: bool = False
    # The state a person chose by hand, while that choice is still respected.
    manual_override: bool | None = None
    # Who made that choice: "user", "automation", "script" or "external"
    # (a wall switch, a device's button), and the automation's or script's name.
    manual_override_by: str = "user"
    manual_override_name: str | None = None

    mode_decision: PumpDecision | None = None

    # Why HomePool itself last switched the pump on, if it did. When that
    # reason ends and the mode has no opinion (off mode, a timer with no
    # slots), the pump is switched off again: HomePool started it, so
    # HomePool stops it.
    started_by: str | None = None

    min_on_minutes: float = 20
    min_off_minutes: float = 10


# Reasons for which HomePool switches the pump on regardless of the mode.
FORCING_SOURCES = ("freeze_protection", "ph_correction", "manual_cycle", "treatment")


@dataclass
class ControlDecision:
    """What to do with the pump. ``pump`` None means leave it as it is."""

    pump: bool | None
    source: str
    reason: str
    # Stable id of the reason and the values it is written with, for the
    # recorder and for translating it into the user's language.
    key: str = ""
    args: dict[str, str] = field(default_factory=dict)


def _released(inp: ControlInputs, source: str) -> ControlDecision:
    """Stop a pump HomePool itself started for a reason that has passed."""
    return ControlDecision(
        False,
        source,
        f"No longer needed for {inp.started_by.replace('_', ' ')}",
        f"released_{inp.started_by}",
    )


def arbitrate(inp: ControlInputs) -> ControlDecision:
    """Apply the authority ladder and return the one decision that wins."""
    if not inp.pump_available:
        return ControlDecision(None, "unavailable", "The pump switch is unavailable", "unavailable")
    if inp.hands_off:
        return ControlDecision(None, "hands_off", "Hands off: the pump is being run by hand", "hands_off")
    if inp.maintenance_lock:
        return ControlDecision(False, "maintenance_lock", "Maintenance lock is on", "maintenance_lock")
    if inp.winter_passive:
        return ControlDecision(False, "winter_passive", "Passive wintering: the pump stays off", "winter_passive")
    if inp.safety_shutoff:
        return ControlDecision(
            False,
            "safety",
            f"Safety shutoff: {inp.safety_reason or 'a safety condition'}",
            "safety",
            {"reason": inp.safety_reason or ""},
        )
    if inp.freeze_risk:
        return ControlDecision(True, "freeze_protection", "Freeze protection: water near 0 °C", "freeze_protection")
    if inp.treatment_key:
        # Decided on the key, not the pump: while vacuuming the pump is
        # None, and the rung still holds the pump for the owner.
        if inp.treatment is None and inp.pump_is_on and inp.started_by in FORCING_SOURCES:
            # Except a pump HomePool itself started (a frost that has passed):
            # HomePool started it, so HomePool stops it.
            return _released(inp, "treatment")
        phase = inp.treatment_key.removeprefix("treatment_")
        return ControlDecision(inp.treatment, "treatment", f"Water treatment: {phase}", inp.treatment_key)
    if inp.ph_correction:
        return ControlDecision(True, "ph_correction", "pH correction needs water flowing", "ph_correction")
    if inp.manual_cycle:
        return ControlDecision(True, "manual_cycle", "Manual cycle in progress", "manual_cycle")
    if inp.manual_override is not None:
        state = "on" if inp.manual_override else "off"
        by = inp.manual_override_by
        if by in ("automation", "script") and inp.manual_override_name:
            return ControlDecision(
                inp.manual_override,
                "manual_override",
                f"Switched {state} by the {by} {inp.manual_override_name}; respected for now",
                f"{by}_override_{state}",
                {"name": inp.manual_override_name},
            )
        if by == "external":
            return ControlDecision(
                inp.manual_override,
                "manual_override",
                f"Switched {state} outside HomePool; respected for now",
                f"external_override_{state}",
            )
        return ControlDecision(
            inp.manual_override,
            "manual_override",
            f"Switched {state} by hand; respected for now",
            f"manual_override_{state}",
        )

    decision = inp.mode_decision
    if decision is None or decision.action == PumpAction.NO_CHANGE:
        if inp.pump_is_on and inp.started_by in FORCING_SOURCES:
            return _released(inp, "mode")
        if decision is None:
            return ControlDecision(None, "mode", "No mode", "no_mode")
        return ControlDecision(None, "mode", decision.reason, decision.key)

    want_on = decision.action == PumpAction.TURN_ON
    if want_on == inp.pump_is_on:
        return ControlDecision(want_on, "mode", decision.reason, decision.key)

    # A change the mode wants: hold it back until the current state has lasted
    # long enough. Only the mode is held back like this; everything above it
    # acts at once.
    if inp.minutes_in_state is not None:
        needed = inp.min_on_minutes if inp.pump_is_on else inp.min_off_minutes
        if inp.minutes_in_state < needed:
            wait = needed - inp.minutes_in_state
            return ControlDecision(
                None,
                "mode",
                f"{decision.reason} (waiting {wait:.0f} min: minimum "
                f"{'run' if inp.pump_is_on else 'rest'} time)",
                "min_run" if inp.pump_is_on else "min_rest",
                {"reason_key": decision.key, "minutes": f"{wait:.0f}"},
            )
    return ControlDecision(want_on, "mode", decision.reason, decision.key)


@dataclass
class ChlorinatorInputs:
    """Facts for the salt cell, which may only ever run with water flowing."""

    has_switch: bool
    pump_is_on: bool
    pump_on_seconds: float | None
    enabled: bool
    in_season: bool
    target_reached: bool
    # The lock, a safety condition, passive wintering, or a treatment phase
    # with no water through the cell.
    blocked: bool
    water_temperature_c: float | None
    min_water_temperature_c: float
    flow_delay_s: float = 120


def chlorinator_wanted(inp: ChlorinatorInputs) -> tuple[bool, str]:
    """Should the cell be on? The interlock with the pump is checked first."""
    if not inp.pump_is_on:
        return False, "No water flowing: the pump is off"
    if inp.pump_on_seconds is None or inp.pump_on_seconds < inp.flow_delay_s:
        return False, "Waiting for the flow to settle after the pump started"
    if inp.blocked:
        return False, "Blocked: maintenance lock, safety, passive wintering or a treatment"
    if not inp.enabled:
        return False, "The chlorinator is disabled"
    if not inp.in_season:
        return False, "Out of the chlorinator's season"
    if (
        inp.water_temperature_c is not None
        and inp.water_temperature_c < inp.min_water_temperature_c
    ):
        return False, "Water too cold for the cell"
    if inp.target_reached:
        return False, "Today's chlorine production is done"
    return True, "Producing chlorine"


def surplus_watts(
    reading_w: float | None,
    sign: str,
    pump_is_on: bool,
    pump_power_w: float | None,
) -> float | None:
    """The surplus there would be with the pump off.

    A grid meter sees the pump's own draw. Without adding it back, the surplus
    drops by the pump's consumption the moment it starts, and a pump that
    started on surplus would immediately see none and stop: the oscillation
    every naive solar automation has.
    """
    if reading_w is None:
        return None
    value = -reading_w if sign == "import_positive" else reading_w
    # A surplus sensor (production minus consumption) nets the pump out the
    # same way a grid meter does, so it gets the same correction.
    if pump_is_on and pump_power_w:
        value += pump_power_w
    return value


class SolarDebouncer:
    """Turns a noisy surplus into a steady yes or no.

    It takes ``start_delay`` minutes above the threshold to say yes, and
    ``stop_delay`` minutes below ``threshold - tolerance`` to say no again. The
    tolerance lets a running pump ride out short peaks of house consumption
    without stopping.
    """

    def __init__(self, start_delay_min: float = 5, stop_delay_min: float = 10) -> None:
        self.start_delay = timedelta(minutes=start_delay_min)
        self.stop_delay = timedelta(minutes=stop_delay_min)
        self.available: bool | None = None
        self._since: datetime | None = None

    def update(
        self,
        now: datetime,
        surplus_w: float | None,
        threshold_w: float,
        tolerance_w: float,
    ) -> bool | None:
        if surplus_w is None:
            self.available = None
            self._since = None
            return None
        if self.available is None:
            self.available = False
        if self.available:
            crossing = surplus_w < threshold_w - tolerance_w
            delay = self.stop_delay
        else:
            crossing = surplus_w >= threshold_w
            delay = self.start_delay
        if not crossing:
            self._since = None
            return self.available
        if self._since is None:
            self._since = now
        if now - self._since >= delay:
            self.available = not self.available
            self._since = None
        return self.available


def solar_noon_utc(day: date, longitude: float) -> datetime:
    """When the sun is highest at this longitude, in UTC. Within a minute or so.

    Uses the pool's own coordinates rather than Home Assistant's home location:
    a second home's pool is not at the first home.
    """
    import math

    n = day.timetuple().tm_yday
    b = 2 * math.pi * (n - 81) / 364
    equation_of_time = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    minutes = 720 - 4 * longitude - equation_of_time
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(minutes=minutes)
