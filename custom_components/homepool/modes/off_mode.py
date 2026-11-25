"""Off mode — no automation, monitor only."""
from .base import OperationMode, PoolContext, PumpDecision, PumpAction


class OffMode(OperationMode):
    @property
    def mode_id(self) -> str:
        return "off"

    @property
    def guarantees_target(self) -> bool:
        return False

    def evaluate(self, context: PoolContext) -> PumpDecision:
        return PumpDecision(
            action=PumpAction.NO_CHANGE,
            reason="Off mode: pump control is manual",
        )
