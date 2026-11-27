"""Chemistry readings taken by hand: what is valid, its range, and when it goes stale.

Pure logic, no Home Assistant imports. A reading older than its stale age is no
longer trusted: it is not used for the target and it is not judged against its
range, so an old number cannot keep an alert on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math

from ..const import (
    DEFAULT_FREE_CHLORINE_RANGE_MAX,
    DEFAULT_FREE_CHLORINE_RANGE_MIN,
    DEFAULT_PH_RANGE_MAX,
    DEFAULT_PH_RANGE_MIN,
    DEFAULT_SALT_RANGE_MAX,
    DEFAULT_SALT_RANGE_MIN,
)

KINDS = (
    "ph",
    "free_chlorine",
    "combined_chlorine",
    "total_alkalinity",
    "calcium_hardness",
    "cyanuric_acid",
    "salt",
)

# Kinds that raise ``<kind>_out_of_range`` (pH and salt have their own alerts).
RANGE_ALERT_KINDS = (
    "free_chlorine",
    "combined_chlorine",
    "total_alkalinity",
    "calcium_hardness",
    "cyanuric_acid",
)

# Kinds that have a sensor of their own, besides the ones that already existed.
NEW_SENSOR_KINDS = ("combined_chlorine", "total_alkalinity", "calcium_hardness", "cyanuric_acid")

# Low and high; None leaves that side open. Cyanuric acid is the salt range here.
DEFAULT_RANGES: dict[str, tuple[float | None, float | None]] = {
    "ph": (DEFAULT_PH_RANGE_MIN, DEFAULT_PH_RANGE_MAX),
    "free_chlorine": (DEFAULT_FREE_CHLORINE_RANGE_MIN, DEFAULT_FREE_CHLORINE_RANGE_MAX),
    "combined_chlorine": (None, 0.6),
    "total_alkalinity": (80, 120),
    "calcium_hardness": (200, 400),
    "cyanuric_acid": (30, 50),
    "salt": (DEFAULT_SALT_RANGE_MIN, DEFAULT_SALT_RANGE_MAX),
}

DEFAULT_STALE_DAYS: dict[str, int] = {
    "ph": 7,
    "free_chlorine": 7,
    "combined_chlorine": 14,
    "total_alkalinity": 30,
    "calcium_hardness": 90,
    "cyanuric_acid": 90,
    "salt": 30,
}

# Without a chlorinator on salt, stabiliser can run higher.
_CYANURIC_ACID_NOT_SALT = (30, 80)


def default_range(kind: str, is_salt: bool) -> tuple[float | None, float | None]:
    if kind == "cyanuric_acid" and not is_salt:
        return _CYANURIC_ACID_NOT_SALT
    return DEFAULT_RANGES[kind]


def validate(kind: str, value: float) -> None:
    """Refuse a reading that cannot be real."""
    if kind not in KINDS:
        raise ValueError(f"unknown reading kind {kind!r}")
    if not math.isfinite(value):
        raise ValueError(f"{kind} must be a number")
    if value < 0:
        raise ValueError(f"{kind} cannot be negative")
    if kind == "ph" and value > 14:
        raise ValueError("pH is between 0 and 14")


@dataclass
class ReadingStatus:
    value: float | None
    at: datetime | None
    stale: bool
    out_of_range: bool


def reading_status(
    kind: str,
    value: float | None,
    at: datetime | None,
    now: datetime,
    low: float | None,
    high: float | None,
    stale_days: int,
) -> ReadingStatus:
    """Whether a reading is stale and, only when it is not, whether it is out of range."""
    stale = value is not None and at is not None and now - at > timedelta(days=stale_days)
    out_of_range = (
        value is not None
        and not stale
        and ((low is not None and value < low) or (high is not None and value > high))
    )
    return ReadingStatus(value=value, at=at, stale=stale, out_of_range=out_of_range)
