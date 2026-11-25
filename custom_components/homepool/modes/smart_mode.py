"""Smart mode — optimal distribution ignoring solar."""
from .base import OperationMode, PoolContext, PumpDecision, PumpAction


class SmartMode(OperationMode):
    """Distributes the daily target in optimal time blocks.

    Default strategy for v1: run during central daylight hours
    (11:00 - 17:00 first, then expand outward if needed).
    """

    PREFERRED_START_HOUR = 11
    PREFERRED_END_HOUR = 17

    @property
    def mode_id(self) -> str:
        return "smart"

    @property
    def guarantees_target(self) -> bool:
        return True

    def evaluate(self, context: PoolContext) -> PumpDecision:
        if context.target_reached:
            if context.pump_is_on:
                return PumpDecision(
                    action=PumpAction.TURN_OFF,
                    reason="Smart mode: daily target reached",
                )
            return PumpDecision(
                action=PumpAction.NO_CHANGE,
                reason="Smart mode: daily target already reached",
            )

        hour = context.current_hour
        remaining_h = context.remaining_minutes / 60
        hours_left_today = context.minutes_until_midnight / 60

        # If we're running out of daylight and still have remaining,
        # force pump on regardless of preferred window
        if remaining_h >= hours_left_today * 0.9:
            if not context.pump_is_on:
                return PumpDecision(
                    action=PumpAction.TURN_ON,
                    reason="Smart mode: must run now to reach target today",
                )
            return PumpDecision(
                action=PumpAction.NO_CHANGE,
                reason="Smart mode: running to reach target",
            )

        # Within preferred window
        if self.PREFERRED_START_HOUR <= hour < self.PREFERRED_END_HOUR:
            if not context.pump_is_on:
                return PumpDecision(
                    action=PumpAction.TURN_ON,
                    reason="Smart mode: within optimal filtration window",
                )
            return PumpDecision(
                action=PumpAction.NO_CHANGE,
                reason="Smart mode: running in optimal window",
            )

        # Outside preferred window but pump is on
        if context.pump_is_on and not context.target_reached:
            return PumpDecision(
                action=PumpAction.NO_CHANGE,
                reason="Smart mode: continuing to reach target",
            )

        return PumpDecision(
            action=PumpAction.NO_CHANGE,
            reason="Smart mode: waiting for optimal window",
        )
