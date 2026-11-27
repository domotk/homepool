"""The water treatments: their phases, what the pump does in each, and how long.

Pure logic, no Home Assistant imports. The coordinator keeps the running
treatment and its clock; this module says what each phase asks of the pump
and when it is over.

How the clock counts (spec §8.1): the phases with the pump on count *pump
time*, so a lock or a safety stop makes them wait instead of ending short;
settling counts wall time while the pump is off, so a frost that runs the
pump does not count as rest. Vacuuming has no clock: the owner ends it.
"""

from __future__ import annotations

from enum import StrEnum


class TreatmentType(StrEnum):
    SHOCK = "shock"
    CLARIFIER = "clarifier"
    FLOCCULANT = "flocculant"


class Phase(StrEnum):
    FILTERING = "filtering"
    MIXING = "mixing"
    SETTLING = "settling"
    VACUUMING = "vacuuming"


PHASES: dict[TreatmentType, tuple[Phase, ...]] = {
    TreatmentType.SHOCK: (Phase.FILTERING,),
    TreatmentType.CLARIFIER: (Phase.FILTERING,),
    TreatmentType.FLOCCULANT: (Phase.MIXING, Phase.SETTLING, Phase.VACUUMING),
}

DEFAULT_HOURS: dict[tuple[TreatmentType, Phase], float] = {
    (TreatmentType.SHOCK, Phase.FILTERING): 24,
    (TreatmentType.CLARIFIER, Phase.FILTERING): 48,
    (TreatmentType.FLOCCULANT, Phase.MIXING): 2,
    (TreatmentType.FLOCCULANT, Phase.SETTLING): 12,
}

# The phase the owner's ``hours`` replaces.
MAIN_PHASE: dict[TreatmentType, Phase] = {
    TreatmentType.SHOCK: Phase.FILTERING,
    TreatmentType.CLARIFIER: Phase.FILTERING,
    TreatmentType.FLOCCULANT: Phase.SETTLING,
}

# What the pump does: on, off, or None for "as the owner leaves it".
PUMP: dict[Phase, bool | None] = {
    Phase.FILTERING: True,
    Phase.MIXING: True,
    Phase.SETTLING: False,
    Phase.VACUUMING: None,
}


def counts_pump_time(phase: Phase) -> bool:
    """Whether the phase's clock runs only while the pump runs."""
    return phase in (Phase.FILTERING, Phase.MIXING)


def phase_hours(kind: TreatmentType, phase: Phase, requested: float | None) -> float | None:
    """How long a phase lasts: the owner's hours for the main phase, else the default."""
    if requested is not None and phase == MAIN_PHASE[kind]:
        return float(requested)
    return DEFAULT_HOURS.get((kind, phase))


def phase_done(phase: Phase, hours: float | None, counted_s: float) -> bool:
    """Whether a phase has counted its hours. Vacuuming, which has none, never
    ends by itself."""
    if phase == Phase.VACUUMING or hours is None:
        return False
    return counted_s >= hours * 3600


def next_phase(kind: TreatmentType, phase: Phase) -> Phase | None:
    """The phase after ``phase``, or None when the treatment is over."""
    phases = PHASES[kind]
    index = phases.index(phase) + 1
    return phases[index] if index < len(phases) else None
