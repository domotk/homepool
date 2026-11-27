"""The authority ladder, rung by rung."""

from __future__ import annotations

from custom_components.homepool.modes.base import PumpAction, PumpDecision
from custom_components.homepool.pool.scheduler import ControlInputs, arbitrate


def _inputs(**kw) -> ControlInputs:
    base = {"pump_available": True, "pump_is_on": True, "minutes_in_state": 60}
    return ControlInputs(**{**base, **kw})


def test_winter_passive_rung_sits_below_the_lock_and_above_safety() -> None:
    # Everything below it wants the pump on: none of them wins.
    below = {
        "safety_shutoff": True,
        "safety_reason": "flood",
        "freeze_risk": True,
        "ph_correction": True,
        "manual_cycle": True,
        "manual_override": True,
        "mode_decision": PumpDecision(PumpAction.TURN_ON, "on", "smart_in_block"),
        "started_by": "manual_cycle",
    }
    decision = arbitrate(_inputs(winter_passive=True, **below))
    assert (decision.pump, decision.source, decision.key) == (False, "winter_passive", "winter_passive")
    # Not held back by the minimum run time, like the lock.
    assert arbitrate(_inputs(winter_passive=True, minutes_in_state=1)).pump is False

    # Above it: the pump being unavailable, hands-off and the lock.
    assert arbitrate(_inputs(winter_passive=True, pump_available=False)).source == "unavailable"
    hands_off = arbitrate(_inputs(winter_passive=True, hands_off=True))
    assert (hands_off.pump, hands_off.source) == (None, "hands_off")
    assert arbitrate(_inputs(winter_passive=True, maintenance_lock=True)).source == "maintenance_lock"

    # Off by default: nothing changes for a pool that is not wintering.
    assert arbitrate(_inputs(freeze_risk=True)).source == "freeze_protection"
