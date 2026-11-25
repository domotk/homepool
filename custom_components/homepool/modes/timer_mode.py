"""Timer mode — fixed schedule, no intelligence."""
from .base import OperationMode, PoolContext, PumpDecision, PumpAction


class TimerMode(OperationMode):
    @property
    def mode_id(self) -> str:
        return "timer"

    @property
    def guarantees_target(self) -> bool:
        return False

    def evaluate(self, context: PoolContext) -> PumpDecision:
        if not context.timer_slots:
            return PumpDecision(
                action=PumpAction.NO_CHANGE,
                reason="Timer mode: no slots configured",
            )

        now = context.current_hour * 60 + context.current_minute
        in_slot = False
        for start_h, start_m, end_h, end_m in context.timer_slots:
            slot_start = start_h * 60 + start_m
            slot_end = end_h * 60 + end_m
            if slot_start <= now < slot_end:
                in_slot = True
                break

        if in_slot and not context.pump_is_on:
            return PumpDecision(
                action=PumpAction.TURN_ON,
                reason="Timer mode: within scheduled slot",
            )
        if not in_slot and context.pump_is_on:
            return PumpDecision(
                action=PumpAction.TURN_OFF,
                reason="Timer mode: outside scheduled slots",
            )
        return PumpDecision(
            action=PumpAction.NO_CHANGE,
            reason="Timer mode: state matches schedule",
        )
