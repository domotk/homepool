"""Smart+Solar: run on surplus first, finish from the grid if the sun falls short.

The grid is used as late as possible and no earlier: the pump waits for
surplus until the moment the remaining target only just fits before the end of
the day, then runs straight through. Starting the grid top-up at a fixed hour
was what made the old automations run into the next day.
"""

from __future__ import annotations

from .base import OperationMode, PoolContext, PumpDecision, turn_off, turn_on


class SmartSolarMode(OperationMode):
    mode_id = "smart_solar"
    guarantees_target = True
    needs_solar = True

    def evaluate(self, context: PoolContext) -> PumpDecision:
        if context.target_reached:
            return turn_off("Smart+Solar: today's target is reached")
        if context.must_run_now:
            return turn_on("Smart+Solar: finishing from the grid before the day ends")
        if context.solar_available:
            return turn_on("Smart+Solar: running on surplus")
        return turn_off("Smart+Solar: waiting for surplus")
