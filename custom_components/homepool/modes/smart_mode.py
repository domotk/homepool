"""Smart: one block a day, centred on solar noon.

The middle of the day is when the water is warmest and the sun is working
hardest against the chlorine, so that is where filtration does most good. The
block is as long as what is left of the target. If the day starts late — the
pump was off for maintenance, or the target rose in the afternoon — it simply
runs from now, and it always finishes before midnight: a target carried past
the end of the day is lost, because the counter starts again at zero.
"""

from __future__ import annotations

from .base import OperationMode, PoolContext, PumpDecision, turn_off, turn_on


class SmartMode(OperationMode):
    mode_id = "smart"
    guarantees_target = True

    def evaluate(self, context: PoolContext) -> PumpDecision:
        if context.target_reached:
            return turn_off("Smart mode: today's target is reached", "smart_target_reached")
        if context.must_run_now:
            return turn_on("Smart mode: only just enough day left to reach the target", "smart_must_run")
        window_start = context.solar_noon_minute - context.target_minutes // 2
        if context.minute_of_day >= window_start:
            return turn_on("Smart mode: inside the block centred on solar noon", "smart_in_block")
        return turn_off("Smart mode: waiting for the block centred on solar noon", "smart_waiting_block")
