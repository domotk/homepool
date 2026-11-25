"""Solar: run on surplus only. Opportunistic, and it does not promise the target.

On a cloudy day it can end the day short, and says so. Use Smart+Solar for a
mode that tops up from the grid.
"""

from __future__ import annotations

from .base import OperationMode, PoolContext, PumpDecision, turn_off, turn_on


class SolarMode(OperationMode):
    mode_id = "solar"
    guarantees_target = False
    needs_solar = True

    def evaluate(self, context: PoolContext) -> PumpDecision:
        if context.target_reached:
            return turn_off("Solar mode: today's target is reached")
        if context.solar_available is None:
            return turn_off("Solar mode: no surplus reading")
        if context.solar_available:
            return turn_on("Solar mode: there is enough surplus")
        return turn_off("Solar mode: not enough surplus")
