"""The step lists of a pool: closing, opening and the water treatments.

Pure logic, no Home Assistant imports. A list is an ordered set of one-off
steps; the coordinator stores which are done. A step may complete a recurring
task, need the pump to run, or exist only in passive wintering.
"""

from __future__ import annotations

from dataclasses import dataclass

CLOSING = "closing"
OPENING = "opening"
TREATMENT = "treatment"
LIST_IDS = (CLOSING, OPENING, TREATMENT)

SHOCK = "shock"
CLARIFIER = "clarifier"
FLOCCULANT = "flocculant"


@dataclass(frozen=True)
class StepDef:
    id: str  # "<list>.<step>"
    text_key: str
    completes_task: str | None = None  # the task key it also marks as done
    needs_pump: bool = False
    only_passive: bool = False
    starts_treatment: str | None = None  # the card offers to start this one
    requires: tuple[str, ...] = ()  # equipment: "salt", "winter_product", "ph_probe"


def _step(step_id: str, **kwargs) -> StepDef:
    return StepDef(id=step_id, text_key="step_" + step_id.replace(".", "_"), **kwargs)


# The steps that need the pump go first: in passive wintering it will not start.
CLOSING_STEPS: tuple[StepDef, ...] = (
    _step("closing.shock", needs_pump=True, starts_treatment=SHOCK),
    _step("closing.cell", requires=("salt",)),
    _step("closing.backwash", completes_task="backwash", needs_pump=True),
    _step("closing.lower_level", only_passive=True),
    _step("closing.plugs", only_passive=True),
    _step(
        "closing.winter_product",
        completes_task="winter_product",
        requires=("winter_product",),
    ),
)

OPENING_STEPS: tuple[StepDef, ...] = (
    _step("opening.remove_winter_product", requires=("winter_product",)),
    _step("opening.backwash", completes_task="backwash", needs_pump=True),
    _step("opening.measure"),
    _step("opening.salt", requires=("salt",)),
    _step("opening.reconnect_cell", requires=("salt",)),
    _step("opening.calibrate_ph", completes_task="ph_calibration", requires=("ph_probe",)),
    _step("opening.shock", needs_pump=True, starts_treatment=SHOCK),
)

_TREATMENT_BACKWASH = _step("treatment.backwash", completes_task="backwash", needs_pump=True)

TREATMENT_SHOCK: tuple[StepDef, ...] = (
    _step("treatment.brush"),
    StepDef("treatment.ph", "step_treatment_ph_shock"),
    _step("treatment.dose"),
    _step("treatment.algaecide"),
    _step("treatment.measure"),
    _TREATMENT_BACKWASH,
)

TREATMENT_CLARIFIER: tuple[StepDef, ...] = (
    StepDef("treatment.ph", "step_treatment_ph_settle"),
    _step("treatment.dose"),
    _TREATMENT_BACKWASH,
)

TREATMENT_FLOCCULANT: tuple[StepDef, ...] = (
    StepDef("treatment.ph", "step_treatment_ph_settle"),
    _step("treatment.dose"),
    _step("treatment.vacuum"),
    _TREATMENT_BACKWASH,
    _step("treatment.refill"),
)

_LISTS: dict[str, tuple[StepDef, ...]] = {
    CLOSING: CLOSING_STEPS,
    OPENING: OPENING_STEPS,
}
_TREATMENTS: dict[str, tuple[StepDef, ...]] = {
    SHOCK: TREATMENT_SHOCK,
    CLARIFIER: TREATMENT_CLARIFIER,
    FLOCCULANT: TREATMENT_FLOCCULANT,
}


def build(list_id: str, equipment: set[str], treatment: str | None = None) -> list[StepDef]:
    """The steps of a list for a pool's equipment, in order."""
    steps = _TREATMENTS[treatment] if list_id == TREATMENT else _LISTS[list_id]
    return [s for s in steps if all(r in equipment for r in s.requires)]


def step_def(list_id: str, step_id: str, treatment: str | None = None) -> StepDef | None:
    """The definition of a stored step, or None if the list no longer has it."""
    steps = _TREATMENTS.get(treatment or "", ()) if list_id == TREATMENT else _LISTS[list_id]
    return next((s for s in steps if s.id == step_id), None)
