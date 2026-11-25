"""Base class for operation modes.

Each mode determines *when* to run the pump to cover the daily target.
The target itself is calculated by the filtration/chlorine calculators.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class PumpAction(StrEnum):
    """Action the mode wants to take on the pump."""

    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"
    NO_CHANGE = "no_change"


@dataclass
class PoolContext:
    """Runtime context passed to the mode for evaluation."""

    # Target
    target_minutes: int
    elapsed_minutes: int
    remaining_minutes: int
    target_reached: bool

    # Pump state
    pump_is_on: bool

    # Time
    current_hour: int
    current_minute: int
    minutes_until_midnight: int

    # Solar (optional)
    solar_excess_w: float | None = None
    solar_excess_threshold_w: float = 500.0
    solar_forecast_today_wh: float | None = None

    # Timer config (for timer mode)
    timer_slots: list[tuple[int, int, int, int]] | None = None  # [(start_h, start_m, end_h, end_m)]

    # Chlorine
    chlorine_target_reached: bool = False

    # Safety / lock
    maintenance_lock: bool = False
    safety_shutoff: bool = False
    ph_correction_active: bool = False


@dataclass
class PumpDecision:
    """Decision made by a mode."""

    action: PumpAction
    reason: str
    duration_minutes: int | None = None  # for how long (if applicable)


class OperationMode(ABC):
    """Abstract base class for pump operation modes."""

    @property
    @abstractmethod
    def mode_id(self) -> str:
        """Return the mode identifier (matches OperationMode enum)."""

    @property
    @abstractmethod
    def guarantees_target(self) -> bool:
        """Whether this mode guarantees reaching the daily target."""

    @abstractmethod
    def evaluate(self, context: PoolContext) -> PumpDecision:
        """Evaluate current conditions and decide pump action.

        This is called periodically (every few minutes) by the coordinator.

        Args:
            context: Current pool state and conditions.

        Returns:
            PumpDecision indicating what to do.
        """

    def on_pump_state_change(self, was_on: bool, is_on: bool) -> None:
        """Called when the pump state changes (from any source)."""

    def on_target_change(self, old_target: int, new_target: int) -> None:
        """Called when the daily target is recalculated."""
