"""Module-level helpers and constants the runtime mixins share."""

from __future__ import annotations

from datetime import datetime

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.util import dt as dt_util


BAD_STATES = (STATE_UNAVAILABLE, STATE_UNKNOWN, None, "")
ACTIONS_KEPT = 50


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# Measuring either of these is the water test.
WATER_TEST_KINDS = ("ph", "free_chlorine")


def _parse_dt(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None
