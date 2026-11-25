"""Whole days, minute by minute, without Home Assistant.

The modes and the arbiter are pure, so a day can be simulated in a few
milliseconds: a clock, a pump that does what it is told, and a solar profile.
What is checked is what matters to a pool and to a motor — is the target met
before midnight, and how many times was the pump started.

The solar profile is synthetic but shaped on real November traces from a
4.6 kW installation: export rising from 09:00 to ~4 kW at 13:00 and gone by
17:00, with clouds that cut it for five to ten minutes and household peaks
(an oven, a kettle) that turn export into import for a while.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

import pytest

from custom_components.homepool.modes import MODE_REGISTRY, PoolContext
from custom_components.homepool.pool.scheduler import (
    ControlInputs,
    SolarDebouncer,
    arbitrate,
    surplus_watts,
)

PUMP_W = 880.0
START = datetime(2026, 11, 16, tzinfo=timezone.utc)


def house_export(minute: int, day: int, cloudy: bool) -> float:
    """Grid export (W, + = export) with the pump off."""
    hour = minute / 60
    if hour < 8.5 or hour > 17.2:
        return -350.0
    sun = max(0.0, math.sin(math.pi * (hour - 8.5) / 8.7))
    production = 4500 * sun * (0.25 if cloudy else 1.0)
    load = 400
    # Household peaks, different each day.
    peaks = [(11 * 60 + 25 + 20 * day, 35, 3000), (14 * 60 + 20, 15, 2500), (9 * 60 + 55, 10, 2200)]
    for start, length, watts in peaks:
        if start <= minute < start + length:
            load += watts
    # Passing clouds.
    if not cloudy and minute % 97 < 6 and 10 * 60 < minute < 16 * 60:
        production *= 0.4
    return production - load


class Sim:
    def __init__(self, mode: str, target: int, cloudy_days: set[int] = frozenset()) -> None:
        self.mode = MODE_REGISTRY[mode]()
        self.target = target
        self.cloudy_days = cloudy_days
        self.pump = False
        self.changed: datetime | None = None
        self.debouncer = SolarDebouncer(5, 10)
        self.starts = 0
        self.elapsed: dict[int, int] = {}
        self.imported_wh = 0.0
        self.import_streak = 0
        self.longest_import = 0

    def run(self, days: int = 2) -> None:
        for step in range(days * 1440):
            day, minute = divmod(step, 1440)
            now = START + timedelta(minutes=step)
            export = house_export(minute, day, day in self.cloudy_days)
            grid = export - (PUMP_W if self.pump else 0)
            if self.pump and grid < 0:
                self.imported_wh += min(-grid, PUMP_W) / 60
            if self.pump and grid < -400:
                self.import_streak += 1
                self.longest_import = max(self.longest_import, self.import_streak)
            else:
                self.import_streak = 0
            surplus = surplus_watts(grid, "export_positive", self.pump, PUMP_W if self.pump else None)
            available = self.debouncer.update(now, surplus, PUMP_W, 400)
            elapsed = self.elapsed.get(day, 0)
            decision = arbitrate(
                ControlInputs(
                    pump_available=True,
                    pump_is_on=self.pump,
                    minutes_in_state=(now - self.changed).total_seconds() / 60 if self.changed else None,
                    mode_decision=self.mode.evaluate(
                        PoolContext(
                            target_minutes=self.target,
                            elapsed_minutes=elapsed,
                            pump_is_on=self.pump,
                            minute_of_day=minute,
                            minutes_until_day_end=1440 - minute,
                            solar_noon_minute=13 * 60 + 5,
                            solar_available=available,
                        )
                    ),
                )
            )
            if decision.pump is not None and decision.pump != self.pump:
                self.pump = decision.pump
                self.changed = now
                if self.pump:
                    self.starts += 1
            if self.pump:
                self.elapsed[day] = elapsed + 1


@pytest.mark.parametrize("target", [140, 300, 480])
def test_smart_meets_the_target_in_one_block_a_day(target: int) -> None:
    sim = Sim("smart", target)
    sim.run(2)
    assert all(sim.elapsed[d] >= target for d in (0, 1))
    assert sim.starts == 2  # one block each day


def test_smart_solar_on_sunny_days_uses_the_sun() -> None:
    sim = Sim("smart_solar", 140)
    sim.run(2)
    assert all(sim.elapsed[d] >= 140 for d in (0, 1))
    # No more than a couple of starts a day despite clouds and peaks.
    assert sim.starts <= 4
    # Import within the tolerance is ridden out rather than stopping and
    # restarting the motor; import beyond it never lasts longer than the stop
    # delay. The case seen in the real traces — an hour and a quarter
    # importing 2 kW — cannot happen.
    assert sim.longest_import <= 11


def test_smart_solar_finishes_from_the_grid_before_midnight() -> None:
    sim = Sim("smart_solar", 300, cloudy_days={0, 1})
    sim.run(2)
    assert all(sim.elapsed[d] >= 300 for d in (0, 1))


def test_solar_mode_does_not_chase_a_weak_sun() -> None:
    sim = Sim("solar", 300, cloudy_days={0})
    sim.run(1)
    # 25 % of a clear day never exceeds the pump's draw: it stays off.
    assert sim.elapsed.get(0, 0) == 0
    assert sim.starts == 0


def test_solar_mode_on_a_sunny_day_does_not_cycle() -> None:
    sim = Sim("solar", 600)
    sim.run(1)
    assert sim.elapsed[0] >= 300
    assert sim.starts <= 3


def test_timer_mode_follows_its_slots_across_midnight() -> None:
    mode = MODE_REGISTRY["timer"]()
    slots = [(22 * 60, 2 * 60)]
    on = [
        mode.evaluate(
            PoolContext(
                target_minutes=0, elapsed_minutes=0, pump_is_on=False,
                minute_of_day=m, minutes_until_day_end=1440 - m, timer_slots=slots,
            )
        ).action
        == "turn_on"
        for m in (21 * 60 + 59, 22 * 60, 23 * 60, 60, 2 * 60)
    ]
    assert on == [False, True, True, True, False]
