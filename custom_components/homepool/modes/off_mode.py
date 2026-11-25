"""Off: no automation. HomePool counts and warns, and never switches the pump."""

from __future__ import annotations

from .base import OperationMode, PoolContext, PumpDecision, no_change


class OffMode(OperationMode):
    mode_id = "off"
    guarantees_target = False

    def evaluate(self, context: PoolContext) -> PumpDecision:
        return no_change("Off mode: the pump is controlled by hand", "off_mode")
