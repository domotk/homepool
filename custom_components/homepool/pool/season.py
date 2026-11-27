"""The season state of a pool, and what the calendar proposes.

Pure logic, no Home Assistant imports. The state is the owner's: HomePool
works out from ``swimming_months`` when a change is due and proposes it, but
never changes the state on its own.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from enum import StrEnum


class SeasonState(StrEnum):
    SWIMMING = "swimming"
    WINTER_ACTIVE = "winter_active"
    WINTER_PASSIVE = "winter_passive"
    OPENING = "opening"


WINTER_STATES = (SeasonState.WINTER_ACTIVE, SeasonState.WINTER_PASSIVE)

# How long before the season the opening is proposed.
OPENING_LEAD_DAYS = 14

NORTH_SWIMMING_MONTHS = [6, 7, 8, 9]
SOUTH_SWIMMING_MONTHS = [12, 1, 2, 3]


def _next_month(month: int) -> int:
    return month % 12 + 1


def _previous_month(month: int) -> int:
    return (month - 2) % 12 + 1


def _days_to_next_run(today: date, months: set[int]) -> int:
    """Days from ``today`` to the first day of the next run of months."""
    starts = [m for m in months if _previous_month(m) not in months]
    upcoming = [
        date(year, m, 1)
        for m in starts
        for year in (today.year, today.year + 1)
        if date(year, m, 1) > today
    ]
    return (min(upcoming) - today).days


def season_proposal(today: date, swimming_months: list[int], state: str) -> str | None:
    """The change the calendar calls for today, if any.

    ``"winter"`` while swimming on the last day of a run of months, or on any
    day after it that is out of season, except in the fourteen days before the
    next run (a pool opened early); ``"opening"`` while wintering, from those
    fourteen days until the run ends, so a missed reminder does not leave a
    pool wintering all summer. A calendar of no months or of all twelve never
    changes, so it proposes nothing.
    """
    months = {int(m) for m in swimming_months if 1 <= int(m) <= 12}
    if not months or len(months) == 12:
        return None
    lead_in = _days_to_next_run(today, months) <= OPENING_LEAD_DAYS
    if state == SeasonState.SWIMMING:
        if today.month not in months:
            return None if lead_in else "winter"
        last_of_run = _next_month(today.month) not in months
        last_day = today.day == monthrange(today.year, today.month)[1]
        return "winter" if last_of_run and last_day else None
    if state in WINTER_STATES:
        return "opening" if lead_in or today.month in months else None
    return None


def default_swimming_months(
    chlorinator_months: list[int] | None, is_salt: bool, latitude: float
) -> list[int]:
    """The swimming months when none were given: the chlorinator's, in a salt
    pool that has them, or summer for the hemisphere."""
    if is_salt and chlorinator_months:
        return sorted(int(m) for m in chlorinator_months)
    return list(SOUTH_SWIMMING_MONTHS if latitude < 0 else NORTH_SWIMMING_MONTHS)


def initial_state(in_season: bool, is_salt: bool, chlorinator_enabled: bool) -> SeasonState:
    """The state of a pool that had none (an upgrade from 0.1), without asking.

    Swimming when the calendar says so and, in a salt pool, the cell is in use;
    active wintering otherwise. Never passive wintering: that would stop the
    pump of someone who has it running.
    """
    if in_season and (chlorinator_enabled or not is_salt):
        return SeasonState.SWIMMING
    return SeasonState.WINTER_ACTIVE
