"""Chlorine production target calculator.

Pure Python module, no Home Assistant dependencies.
Calculates the daily chlorine production target in minutes for salt
chlorinator pools, considering salinity and water temperature effects
on chlorinator efficiency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .filtration_calculator import interpolate


# ──────────────────────────────────────────────
# Interpolation tables
# ──────────────────────────────────────────────

# Chlorine demand: g of chlorine needed per m³ per day
# based on water temperature
CHLORINE_DEMAND_TABLE = [
    (10, 1.0),    # winter, minimal biological activity
    (15, 1.5),
    (18, 2.0),
    (20, 2.5),
    (22, 3.0),
    (24, 3.5),
    (26, 4.0),    # summer standard
    (28, 5.0),
    (30, 5.5),
    (32, 6.0),    # extreme summer / heavy use
]

# Salinity effect on chlorinator production efficiency
SALINITY_FACTOR_TABLE = [
    (2.0, 0.00),   # too low, won't produce
    (2.5, 0.50),
    (3.0, 0.75),
    (3.5, 0.95),
    (4.0, 1.00),   # ideal
    (5.0, 1.00),
    (5.5, 0.95),
    (6.0, 0.90),   # too high, stress on cell
]

# Cold water effect on chlorinator production
COLD_WATER_FACTOR_TABLE = [
    (8, 0.00),    # too cold, chlorinator off
    (10, 0.00),
    (12, 0.30),
    (15, 0.60),   # manufacturer minimum operating temp
    (18, 0.85),
    (20, 1.00),   # full efficiency
]


# ──────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────

@dataclass
class ChlorineInputs:
    """All inputs for chlorine production target calculation."""

    # Pool
    pool_volume_m3: float

    # Chlorinator specs
    chlorinator_nominal_production_g_h: float
    chlorinator_production_pct: float  # current configured %
    chlorinator_self_regulating: bool = False

    # Chlorinator calendar
    chlorinator_active_months: list[int] | None = None  # e.g. [6,7,8,9]

    # Water conditions
    water_temperature_c: float | None = None
    air_temperature_c: float | None = None
    salt_level_g_l: float | None = None
    salt_target_g_l: float = 4.0  # fallback if no measurement

    # Context
    current_date: date | None = None
    latitude: float = 0.0

    # Total filtration target (needed for optimal production calc)
    total_target_minutes: int | None = None


@dataclass
class ChlorineResult:
    """Result of the chlorine production target calculation."""

    # Core result
    target_chlorine_minutes: int | None  # None if chlorinator not active
    is_chlorinator_active: bool

    # Calculation details
    chlorine_demand_g_per_day: float = 0.0
    effective_production_g_h: float = 0.0
    salinity_factor: float = 1.0
    cold_water_factor: float = 1.0

    # Recommended production % to avoid over-chlorination
    recommended_production_pct: float | None = None

    # Alerts
    warnings: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)


# ──────────────────────────────────────────────
# Calculation functions
# ──────────────────────────────────────────────

def is_chlorinator_in_season(
    current_date: date,
    active_months: list[int] | None,
) -> bool:
    """Check if the chlorinator should be active based on calendar.

    Args:
        current_date: Today's date.
        active_months: List of month numbers when chlorinator is active.

    Returns:
        True if chlorinator should be active today.
    """
    if active_months is None or len(active_months) == 0:
        return False
    return current_date.month in active_months


def calculate_chlorine_demand(
    pool_volume_m3: float,
    water_temperature_c: float | None,
    air_temperature_c: float | None,
) -> tuple[float, str]:
    """Calculate daily chlorine demand in grams.

    Args:
        pool_volume_m3: Pool volume in m³.
        water_temperature_c: Water temperature (preferred).
        air_temperature_c: Air temperature (fallback).

    Returns:
        Tuple of (demand_grams, source).
    """
    if water_temperature_c is not None:
        demand_factor = interpolate(CHLORINE_DEMAND_TABLE, water_temperature_c)
        return pool_volume_m3 * demand_factor, "water_temperature_sensor"

    if air_temperature_c is not None:
        estimated_water = air_temperature_c - 2.0
        demand_factor = interpolate(CHLORINE_DEMAND_TABLE, estimated_water)
        return pool_volume_m3 * demand_factor, "air_temperature_with_offset"

    # Fallback: assume moderate demand (20°C equivalent)
    demand_factor = interpolate(CHLORINE_DEMAND_TABLE, 20.0)
    return pool_volume_m3 * demand_factor, "fallback_moderate"


def calculate_effective_production(
    nominal_production_g_h: float,
    production_pct: float,
    salt_level_g_l: float | None,
    salt_target_g_l: float,
    water_temperature_c: float | None,
    air_temperature_c: float | None,
) -> tuple[float, float, float, dict[str, str], list[str]]:
    """Calculate effective chlorinator production rate.

    Args:
        nominal_production_g_h: Nominal production at 100%.
        production_pct: Currently configured production %.
        salt_level_g_l: Measured salt level (None if unknown).
        salt_target_g_l: Configured salt target (fallback).
        water_temperature_c: Water temperature.
        air_temperature_c: Air temperature (fallback).

    Returns:
        Tuple of (effective_g_h, salinity_factor, cold_factor, sources, warnings).
    """
    warnings: list[str] = []
    sources: dict[str, str] = {}

    # Salinity factor
    salt = salt_level_g_l if salt_level_g_l is not None else salt_target_g_l
    sources["salinity"] = "salinity_sensor" if salt_level_g_l is not None else "salt_target_fallback"

    salinity_factor = interpolate(SALINITY_FACTOR_TABLE, salt)
    if salinity_factor <= 0.5:
        warnings.append(
            f"Salt level {salt:.1f} g/L is critically low; "
            "chlorinator production severely reduced"
        )
    elif salinity_factor < 0.9:
        warnings.append(
            f"Salt level {salt:.1f} g/L is below optimal; "
            "consider adding salt"
        )

    # Cold water factor
    temp = water_temperature_c
    temp_source = "water_temperature_sensor"
    if temp is None and air_temperature_c is not None:
        temp = air_temperature_c - 2.0
        temp_source = "air_temperature_with_offset"
    if temp is None:
        temp = 20.0  # fallback
        temp_source = "fallback_neutral"

    sources["cold_water"] = temp_source
    cold_factor = interpolate(COLD_WATER_FACTOR_TABLE, temp)

    if cold_factor <= 0.0:
        warnings.append(
            f"Water temperature {temp:.0f}°C is too low; "
            "chlorinator should not operate below 15°C"
        )
    elif cold_factor < 0.6:
        warnings.append(
            f"Water temperature {temp:.0f}°C reduces chlorinator efficiency "
            f"to {cold_factor*100:.0f}%"
        )

    effective = (
        nominal_production_g_h
        * (production_pct / 100.0)
        * salinity_factor
        * cold_factor
    )

    return effective, salinity_factor, cold_factor, sources, warnings


def calculate_recommended_production_pct(
    chlorine_demand_g: float,
    nominal_production_g_h: float,
    total_target_hours: float,
    salinity_factor: float,
    cold_water_factor: float,
) -> float | None:
    """Calculate the optimal production % to match demand exactly.

    This prevents over-chlorination when the pump runs longer than
    needed for chlorine production alone.

    Args:
        chlorine_demand_g: Daily chlorine demand in grams.
        nominal_production_g_h: Nominal production at 100%.
        total_target_hours: Total daily target (filtration or chlorine, whichever is higher).
        salinity_factor: Current salinity adjustment.
        cold_water_factor: Current cold water adjustment.

    Returns:
        Recommended production % (0-100), or None if not calculable.
    """
    if total_target_hours <= 0 or nominal_production_g_h <= 0:
        return None

    adjusted_nominal = nominal_production_g_h * salinity_factor * cold_water_factor
    if adjusted_nominal <= 0:
        return None

    # How much % do we need so that running for total_target_hours
    # produces exactly chlorine_demand_g?
    optimal_pct = (chlorine_demand_g / (adjusted_nominal * total_target_hours)) * 100.0

    return round(min(max(optimal_pct, 0.0), 100.0), 1)


# ──────────────────────────────────────────────
# Main calculation
# ──────────────────────────────────────────────

def calculate_chlorine_target(inputs: ChlorineInputs) -> ChlorineResult:
    """Calculate the daily chlorine production target in minutes.

    If the chlorinator is not in season (according to the calendar),
    returns None as target_chlorine_minutes.

    Args:
        inputs: All inputs for the calculation.

    Returns:
        ChlorineResult with target, factors, recommendations, and warnings.
    """
    today = inputs.current_date or date.today()

    # Check if chlorinator is active this month
    in_season = is_chlorinator_in_season(today, inputs.chlorinator_active_months)

    if not in_season:
        return ChlorineResult(
            target_chlorine_minutes=None,
            is_chlorinator_active=False,
            warnings=[],
            sources={"calendar": f"month_{today.month}_not_in_season"},
        )

    all_warnings: list[str] = []
    all_sources: dict[str, str] = {"calendar": f"month_{today.month}_in_season"}

    # --- Chlorine demand ---
    demand_g, demand_source = calculate_chlorine_demand(
        inputs.pool_volume_m3,
        inputs.water_temperature_c,
        inputs.air_temperature_c,
    )
    all_sources["chlorine_demand"] = demand_source

    # --- Effective production ---
    effective_g_h, sal_factor, cold_factor, prod_sources, prod_warnings = (
        calculate_effective_production(
            inputs.chlorinator_nominal_production_g_h,
            inputs.chlorinator_production_pct,
            inputs.salt_level_g_l,
            inputs.salt_target_g_l,
            inputs.water_temperature_c,
            inputs.air_temperature_c,
        )
    )
    all_sources.update(prod_sources)
    all_warnings.extend(prod_warnings)

    # --- Target minutes ---
    if effective_g_h <= 0:
        all_warnings.append(
            "Chlorinator effective production is zero; "
            "cannot calculate chlorine target"
        )
        return ChlorineResult(
            target_chlorine_minutes=None,
            is_chlorinator_active=True,
            chlorine_demand_g_per_day=round(demand_g, 1),
            effective_production_g_h=0.0,
            salinity_factor=round(sal_factor, 3),
            cold_water_factor=round(cold_factor, 3),
            warnings=all_warnings,
            sources=all_sources,
        )

    target_min = round((demand_g / effective_g_h) * 60)

    # --- Recommended production % ---
    recommended_pct = None
    if not inputs.chlorinator_self_regulating and inputs.total_target_minutes is not None:
        total_hours = inputs.total_target_minutes / 60.0
        recommended_pct = calculate_recommended_production_pct(
            demand_g,
            inputs.chlorinator_nominal_production_g_h,
            total_hours,
            sal_factor,
            cold_factor,
        )

    return ChlorineResult(
        target_chlorine_minutes=target_min,
        is_chlorinator_active=True,
        chlorine_demand_g_per_day=round(demand_g, 1),
        effective_production_g_h=round(effective_g_h, 2),
        salinity_factor=round(sal_factor, 3),
        cold_water_factor=round(cold_factor, 3),
        recommended_production_pct=recommended_pct,
        warnings=all_warnings,
        sources=all_sources,
    )
