"""Smart+Solar mode — prioritize solar, guarantee target with grid."""
from .base import OperationMode, PoolContext, PumpDecision, PumpAction


class SmartSolarMode(OperationMode):
    """Combines solar priority with target guarantee.

    Runs on solar excess when available. If solar hours are
    insufficient to reach the target, completes with grid power
    (typically after sunset or early morning).
    """

    FALLBACK_START_HOUR = 20  # Start grid fallback after 8 PM

    @property
    def mode_id(self) -> str:
        return "smart_solar"

    @property
    def guarantees_target(self) -> bool:
        return True

    def evaluate(self, context: PoolContext) -> PumpDecision:
        if context.target_reached:
            if context.pump_is_on:
                return PumpDecision(
                    action=PumpAction.TURN_OFF,
                    reason="Smart+Solar: daily target reached",
                )
            return PumpDecision(
                action=PumpAction.NO_CHANGE,
                reason="Smart+Solar: daily target already reached",
            )

        hour = context.current_hour
        remaining_h = context.remaining_minutes / 60
        hours_left = context.minutes_until_midnight / 60

        # Check solar excess
        has_solar = (
            context.solar_excess_w is not None
            and context.solar_excess_w >= context.solar_excess_threshold_w
        )

        # If solar available, run on solar
        if has_solar:
            if not context.pump_is_on:
                return PumpDecision(
                    action=PumpAction.TURN_ON,
                    reason=f"Smart+Solar: solar excess {context.solar_excess_w:.0f}W available",
                )
            return PumpDecision(
                action=PumpAction.NO_CHANGE,
                reason="Smart+Solar: running on solar",
            )

        # No solar — check if we need grid fallback
        # If remaining time is close to time left in day, force grid
        if remaining_h >= hours_left * 0.85:
            if not context.pump_is_on:
                return PumpDecision(
                    action=PumpAction.TURN_ON,
                    reason="Smart+Solar: grid fallback to guarantee target",
                )
            return PumpDecision(
                action=PumpAction.NO_CHANGE,
                reason="Smart+Solar: running on grid to reach target",
            )

        # After fallback hour, if still remaining, run on grid
        if hour >= self.FALLBACK_START_HOUR and context.remaining_minutes > 0:
            if not context.pump_is_on:
                return PumpDecision(
                    action=PumpAction.TURN_ON,
                    reason="Smart+Solar: evening grid fallback",
                )
            return PumpDecision(
                action=PumpAction.NO_CHANGE,
                reason="Smart+Solar: evening grid session",
            )

        # During day without solar, wait for solar to return
        if context.pump_is_on:
            return PumpDecision(
                action=PumpAction.TURN_OFF,
                reason="Smart+Solar: no solar, waiting (grid fallback later if needed)",
            )

        return PumpDecision(
            action=PumpAction.NO_CHANGE,
            reason="Smart+Solar: waiting for solar or fallback window",
        )
