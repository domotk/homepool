"""Solar mode — run on solar excess only, no guarantee."""
from .base import OperationMode, PoolContext, PumpDecision, PumpAction


class SolarMode(OperationMode):
    """Runs pump only when solar excess is above threshold.

    Does NOT guarantee reaching the daily target. If the sun
    doesn't provide enough, the day ends with a deficit.
    """

    @property
    def mode_id(self) -> str:
        return "solar"

    @property
    def guarantees_target(self) -> bool:
        return False

    def evaluate(self, context: PoolContext) -> PumpDecision:
        if context.target_reached:
            if context.pump_is_on:
                return PumpDecision(
                    action=PumpAction.TURN_OFF,
                    reason="Solar mode: daily target reached",
                )
            return PumpDecision(
                action=PumpAction.NO_CHANGE,
                reason="Solar mode: daily target already reached",
            )

        if context.solar_excess_w is None:
            return PumpDecision(
                action=PumpAction.NO_CHANGE,
                reason="Solar mode: no solar data available",
            )

        has_excess = context.solar_excess_w >= context.solar_excess_threshold_w

        if has_excess and not context.pump_is_on:
            return PumpDecision(
                action=PumpAction.TURN_ON,
                reason=f"Solar mode: excess {context.solar_excess_w:.0f}W "
                       f">= threshold {context.solar_excess_threshold_w:.0f}W",
            )
        if not has_excess and context.pump_is_on:
            return PumpDecision(
                action=PumpAction.TURN_OFF,
                reason=f"Solar mode: excess {context.solar_excess_w:.0f}W "
                       f"< threshold {context.solar_excess_threshold_w:.0f}W",
            )

        return PumpDecision(
            action=PumpAction.NO_CHANGE,
            reason="Solar mode: state matches solar conditions",
        )
