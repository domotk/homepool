"""Base class for operation modes.

A mode answers one question: *when* should the pump run to cover today's
target? It does not know about locks, safety or manual actions. Those have
more authority than any mode and are applied around it by ``pool.scheduler``.
Keeping them out of here means each mode stays small enough to read whole.

Everything a mode sees is in minutes of the local day, already computed by
the coordinator with Home Assistant's clock and time zone. That keeps DST and
the length of the day out of the modes entirely.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class PumpAction(StrEnum):
    """What a mode wants the pump to do."""

    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"
    NO_CHANGE = "no_change"


@dataclass
class PoolContext:
    """Runtime context passed to a mode."""

    # Today's target and progress
    target_minutes: int
    elapsed_minutes: int

    # Pump
    pump_is_on: bool

    # Clock, in minutes of the local day
    minute_of_day: int
    minutes_until_day_end: int
    solar_noon_minute: int = 13 * 60 + 30

    # Solar: True/False once the debounced surplus has an opinion, None when
    # there is no surplus sensor or it is not reporting.
    solar_available: bool | None = None

    # Timer slots, as (start_minute, end_minute) of the day. A slot whose end
    # is before its start crosses midnight.
    timer_slots: list[tuple[int, int]] | None = None

    # A guaranteed mode must have finished this long before the day ends.
    end_of_day_margin: int = 10

    @property
    def remaining_minutes(self) -> int:
        return max(0, self.target_minutes - self.elapsed_minutes)

    @property
    def target_reached(self) -> bool:
        return self.elapsed_minutes >= self.target_minutes

    @property
    def must_run_now(self) -> bool:
        """Is there only just enough day left to finish the target?

        The pump has to be on from now until the margin before midnight. A
        target that is still unmet at midnight is a day lost: the counter starts
        again, and nothing carries the shortfall over.
        """
        if self.target_reached:
            return False
        latest_start = self.minutes_until_day_end - self.end_of_day_margin - self.remaining_minutes
        return latest_start <= 0


@dataclass
class PumpDecision:
    """A mode's decision, with the reason shown on the control sensor."""

    action: PumpAction
    reason: str


def turn_on(reason: str) -> PumpDecision:
    return PumpDecision(PumpAction.TURN_ON, reason)


def turn_off(reason: str) -> PumpDecision:
    return PumpDecision(PumpAction.TURN_OFF, reason)


def no_change(reason: str) -> PumpDecision:
    return PumpDecision(PumpAction.NO_CHANGE, reason)


class OperationMode(ABC):
    """A pump operation mode."""

    mode_id: str = ""
    guarantees_target: bool = False
    needs_solar: bool = False

    @abstractmethod
    def evaluate(self, context: PoolContext) -> PumpDecision:
        """Decide what the pump should be doing right now."""
