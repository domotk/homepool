"""Filtration target calculator.

Pure Python module, no Home Assistant dependencies.
Calculates the daily filtration target in minutes based on pool
configuration and environmental conditions.

Calibrated against Astralpool manufacturer table:
  - 24°C → 8 h/day
  - 26°C → 10 h/day
  - >28°C → 13 h/day
"""

from __future__ import annotations

import math

from dataclasses import dataclass, field
from datetime import date


# ──────────────────────────────────────────────
# Interpolation tables (piecewise linear)
# ──────────────────────────────────────────────

# (input_value, factor) pairs, sorted by input_value.
# Values between points are linearly interpolated.

SEASONAL_TABLE_NORTH = [
    (1, 0.50),   # January
    (2, 0.55),
    (3, 0.70),
    (4, 0.85),
    (5, 1.00),   # May — neutral
    (6, 1.15),
    (7, 1.30),   # July — peak
    (8, 1.30),
    (9, 1.10),
    (10, 0.85),
    (11, 0.65),
    (12, 0.50),
]

# From 18 °C up this is calibrated against a manufacturer's table (8 h at
# 24 °C, 10 h at 26 °C, 13 h above 28 °C). Below 15 °C it falls faster:
# algae and bacteria barely grow in cold water, and the first real install
# showed a November target far above what the pool needed.
TEMPERATURE_TABLE = [
    (8, 0.45),
    (10, 0.48),
    (12, 0.52),
    (15, 0.70),
    (18, 0.90),
    (20, 1.00),   # neutral
    (22, 1.15),
    (24, 1.35),
    (26, 1.60),
    (28, 1.85),
    (30, 2.05),
    (32, 2.20),
]

UV_TABLE = [
    (0, 0.90),
    (1, 0.90),
    (4, 1.00),   # neutral
    (7, 1.10),
    (10, 1.18),
    (11, 1.20),
]

RAIN_PAST_TABLE = [
    (0, 1.00),
    (2, 1.05),
    (5, 1.15),
    (10, 1.25),
    (20, 1.40),
    (40, 1.55),
]

RAIN_FUTURE_TABLE = [
    (0, 1.00),
    (5, 1.00),
    (10, 0.95),
    (20, 0.90),
    (40, 0.85),
]


# ──────────────────────────────────────────────
# Interpolation helper
# ──────────────────────────────────────────────

def interpolate(table: list[tuple[float, float]], value: float) -> float:
    """Linearly interpolate a value from a lookup table.

    Values outside the table range are clamped to the nearest endpoint.

    Args:
        table: List of (input, output) tuples, sorted by input.
        value: The input value to look up.

    Returns:
        Interpolated output value.
    """
    if not table:
        return 1.0

    # Clamp to table bounds
    if value <= table[0][0]:
        return table[0][1]
    if value >= table[-1][0]:
        return table[-1][1]

    # Find surrounding points
    for i in range(len(table) - 1):
        x0, y0 = table[i]
        x1, y1 = table[i + 1]
        if x0 <= value <= x1:
            # Linear interpolation
            t = (value - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)

    return table[-1][1]


# ──────────────────────────────────────────────
# Input / Output data structures
# ──────────────────────────────────────────────

@dataclass
class FiltrationInputs:
    """All inputs needed to calculate the daily filtration target."""

    # Pool configuration (required)
    pool_volume_m3: float
    nominal_flow_rate_m3h: float
    latitude: float

    # Cover
    has_cover: str = "none"          # "none", "manual", "automatic"
    is_covered_by_roof: bool = False
    cover_currently_on: bool | None = None  # for automatic covers

    # User calibration
    user_multiplier: float = 1.0

    # Dynamic data (all optional)
    current_date: date | None = None
    water_temperature_c: float | None = None
    air_temperature_c: float | None = None
    uv_index: float | None = None
    rain_last_24h_mm: float | None = None
    rain_next_24h_mm: float | None = None


@dataclass
class FiltrationResult:
    """Result of the filtration target calculation."""

    target_minutes: int
    base_minutes: int

    # Individual factors applied
    seasonal_factor: float = 1.0
    temperature_factor: float = 1.0
    uv_factor: float = 1.0
    rain_factor: float = 1.0
    cover_factor: float = 1.0
    user_multiplier: float = 1.0

    # Combined factor (product of all above)
    combined_factor: float = 1.0

    # Raw target before clamping
    raw_target_minutes: int = 0

    # Limits applied
    min_minutes: int = 0
    max_minutes: int = 0
    was_clamped: bool = False

    # Data sources used (for transparency)
    sources: dict[str, str] = field(default_factory=dict)

    # Warnings generated
    warnings: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────
# Factor calculation functions
# ──────────────────────────────────────────────

def get_hemisphere(latitude: float) -> str:
    """Determine hemisphere from latitude."""
    return "north" if latitude >= 0 else "south"


def calculate_seasonal_factor(month: int, latitude: float) -> float:
    """Calculate seasonal factor based on month and hemisphere.

    In the southern hemisphere, months are shifted by 6.

    Args:
        month: Month number (1-12).
        latitude: Latitude in degrees.

    Returns:
        Seasonal adjustment factor.
    """
    if latitude < 0:
        # Southern hemisphere: shift 6 months
        month = ((month - 1 + 6) % 12) + 1

    return interpolate(SEASONAL_TABLE_NORTH, month)


# Below this water temperature one turnover a day is more than the water
# needs: algae and bacteria barely grow, and the usual advice for a pool left
# open in winter is one to two hours. The floor eases from one turnover at
# WINTER_FLOOR_WARM_C to half of one at WINTER_FLOOR_COLD_C.
WINTER_FLOOR_WARM_C = 15.0
WINTER_FLOOR_COLD_C = 12.0
WINTER_FLOOR_TURNOVERS = 0.5


def minimum_turnovers(
    water_temp_c: float | None,
    air_temp_c: float | None,
    air_offset: float = -2.0,
) -> float:
    """The fewest turnovers a day the target may fall to.

    One turnover, unless the water is known to be cold. Without any
    temperature the floor stays at one: a cold-water allowance needs evidence.
    """
    if water_temp_c is not None:
        water = water_temp_c
    elif air_temp_c is not None:
        water = air_temp_c + air_offset
    else:
        return 1.0
    if water >= WINTER_FLOOR_WARM_C:
        return 1.0
    if water <= WINTER_FLOOR_COLD_C:
        return WINTER_FLOOR_TURNOVERS
    span = WINTER_FLOOR_WARM_C - WINTER_FLOOR_COLD_C
    return WINTER_FLOOR_TURNOVERS + (1.0 - WINTER_FLOOR_TURNOVERS) * (water - WINTER_FLOOR_COLD_C) / span


def calculate_temperature_factor(
    water_temp_c: float | None,
    air_temp_c: float | None,
    air_offset: float = -2.0,
) -> tuple[float, str]:
    """Calculate temperature factor.

    Prefers water temperature; falls back to air temperature with offset.

    Args:
        water_temp_c: Water temperature in °C (preferred).
        air_temp_c: Air temperature in °C (fallback).
        air_offset: Offset applied to air temp to estimate water temp.

    Returns:
        Tuple of (factor, source_description).
    """
    if water_temp_c is not None:
        return interpolate(TEMPERATURE_TABLE, water_temp_c), "water_temperature_sensor"

    if air_temp_c is not None:
        estimated_water = air_temp_c + air_offset
        return interpolate(TEMPERATURE_TABLE, estimated_water), "air_temperature_with_offset"

    return 1.0, "fallback_neutral"


def calculate_uv_factor(
    uv_index: float | None,
    is_covered_by_roof: bool,
) -> tuple[float, str]:
    """Calculate UV factor.

    Forced to 1.0 if pool is covered by a roof.

    Args:
        uv_index: Current UV index.
        is_covered_by_roof: Whether the pool is under a fixed roof.

    Returns:
        Tuple of (factor, source_description).
    """
    if is_covered_by_roof:
        return 1.0, "covered_by_roof_override"

    if uv_index is not None:
        return interpolate(UV_TABLE, uv_index), "uv_sensor"

    return 1.0, "fallback_neutral"


def calculate_rain_factor(
    rain_last_24h_mm: float | None,
    rain_next_24h_mm: float | None,
    is_covered_by_roof: bool,
) -> tuple[float, str]:
    """Calculate rain factor combining past and future precipitation.

    Past rain increases demand (contamination already in water).
    Future rain slightly decreases demand (don't over-filter today).
    Forced to 1.0 if pool is covered by a roof.

    Args:
        rain_last_24h_mm: Precipitation in last 24 hours (mm).
        rain_next_24h_mm: Predicted precipitation in next 24 hours (mm).
        is_covered_by_roof: Whether the pool is under a fixed roof.

    Returns:
        Tuple of (factor, source_description).
    """
    if is_covered_by_roof:
        return 1.0, "covered_by_roof_override"

    past_factor = 1.0
    future_factor = 1.0
    source = "fallback_neutral"

    if rain_last_24h_mm is not None:
        past_factor = interpolate(RAIN_PAST_TABLE, rain_last_24h_mm)
        source = "weather_entity"

    if rain_next_24h_mm is not None:
        future_factor = interpolate(RAIN_FUTURE_TABLE, rain_next_24h_mm)
        if source == "fallback_neutral":
            source = "weather_entity"

    return past_factor * future_factor, source


def calculate_cover_factor(
    has_cover: str,
    cover_currently_on: bool | None,
) -> float:
    """Calculate cover factor.

    Args:
        has_cover: "none", "manual", or "automatic".
        cover_currently_on: State of automatic cover (True=closed/on).

    Returns:
        Cover adjustment factor.
    """
    if has_cover == "none":
        return 1.0

    if has_cover == "automatic":
        if cover_currently_on is True:
            return 0.65
        if cover_currently_on is False:
            return 1.0
        # Unknown state for automatic cover → treat as manual
        return 0.80

    if has_cover == "manual":
        # Heuristic: assume on at night, off during day → average reduction
        return 0.80

    return 1.0


# ──────────────────────────────────────────────
# Main calculation
# ──────────────────────────────────────────────

def calculate_filtration_target(inputs: FiltrationInputs) -> FiltrationResult:
    """Calculate the daily filtration target in minutes.

    This function considers only the filtration demand (biological/physical).
    The chlorine production demand is calculated separately in
    chlorine_calculator.py. The final daily target is max(filtration, chlorine).

    Args:
        inputs: All inputs for the calculation.

    Returns:
        FiltrationResult with target, factors, sources, and warnings.
    """
    warnings: list[str] = []
    sources: dict[str, str] = {}

    # Base calculation: 2 turnovers
    base_minutes = round((inputs.pool_volume_m3 / inputs.nominal_flow_rate_m3h) * 60 * 2)

    # Current date
    today = inputs.current_date or date.today()

    # --- Seasonal factor ---
    seasonal = calculate_seasonal_factor(today.month, inputs.latitude)
    sources["seasonal"] = f"month_{today.month}"

    # --- Temperature factor ---
    temp_factor, temp_source = calculate_temperature_factor(
        inputs.water_temperature_c,
        inputs.air_temperature_c,
    )
    sources["temperature"] = temp_source
    if temp_source == "fallback_neutral":
        warnings.append("No temperature data available; using neutral factor")

    # --- UV factor ---
    uv_factor, uv_source = calculate_uv_factor(
        inputs.uv_index,
        inputs.is_covered_by_roof,
    )
    sources["uv"] = uv_source
    if uv_source == "fallback_neutral":
        warnings.append("No UV data available; using neutral factor")

    # --- Rain factor ---
    rain_factor, rain_source = calculate_rain_factor(
        inputs.rain_last_24h_mm,
        inputs.rain_next_24h_mm,
        inputs.is_covered_by_roof,
    )
    sources["rain"] = rain_source

    # --- Cover factor ---
    cover_factor = calculate_cover_factor(
        inputs.has_cover,
        inputs.cover_currently_on,
    )
    sources["cover"] = inputs.has_cover

    # --- User multiplier ---
    user_mult = inputs.user_multiplier

    # Combined
    combined = seasonal * temp_factor * uv_factor * rain_factor * cover_factor * user_mult
    raw_target = round(base_minutes * combined)

    # Limits
    min_minutes = math.ceil(base_minutes / 2 * minimum_turnovers(
        inputs.water_temperature_c, inputs.air_temperature_c
    ))
    max_minutes = round(base_minutes * 3.5)  # 7 turnovers
    clamped = max(min_minutes, min(raw_target, max_minutes))
    was_clamped = clamped != raw_target

    return FiltrationResult(
        target_minutes=clamped,
        base_minutes=base_minutes,
        seasonal_factor=round(seasonal, 3),
        temperature_factor=round(temp_factor, 3),
        uv_factor=round(uv_factor, 3),
        rain_factor=round(rain_factor, 3),
        cover_factor=round(cover_factor, 3),
        user_multiplier=round(user_mult, 3),
        combined_factor=round(combined, 3),
        raw_target_minutes=raw_target,
        min_minutes=min_minutes,
        max_minutes=max_minutes,
        was_clamped=was_clamped,
        sources=sources,
        warnings=warnings,
    )
