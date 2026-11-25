"""Timer: fixed time slots, whatever the target says.

Rigid on purpose. It is for people who want the old mechanical timer back,
with the counting and the warnings on top.
"""

from __future__ import annotations

from .base import OperationMode, PoolContext, PumpDecision, no_change, turn_off, turn_on


def in_slot(minute: int, slots: list[tuple[int, int]]) -> bool:
    """Is this minute of the day inside any slot? Slots may cross midnight."""
    for start, end in slots:
        if start == end:
            continue
        if start < end:
            if start <= minute < end:
                return True
        elif minute >= start or minute < end:
            return True
    return False


class TimerMode(OperationMode):
    mode_id = "timer"
    guarantees_target = False

    def evaluate(self, context: PoolContext) -> PumpDecision:
        if not context.timer_slots:
            return no_change("Timer mode: no time slots configured")
        if in_slot(context.minute_of_day, context.timer_slots):
            return turn_on("Timer mode: inside a scheduled slot")
        return turn_off("Timer mode: outside the scheduled slots")
