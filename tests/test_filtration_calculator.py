"""Tests for the filtration target calculator.

Validates the algorithm against the Astralpool manufacturer table
and various environmental scenarios using the reference pool:
  - 30 m³, Astralpool Sena 12.8 m³/h, Mediterranean coast (lat 39.6)
"""

import pytest
from datetime import date

from custom_components.homepool.pool.filtration_calculator import (
    FiltrationInputs,
    calculate_filtration_target,
    interpolate,
    calculate_seasonal_factor,
)


# ──────────────────────────────────────────────
# Reference pool constants
# ──────────────────────────────────────────────

REF_VOLUME = 30.0
REF_FLOW_RATE = 12.8
REF_LATITUDE = 39.6  # Mediterranean coast, Spain


def make_inputs(**kwargs) -> FiltrationInputs:
    """Create FiltrationInputs with reference pool defaults."""
    defaults = {
        "pool_volume_m3": REF_VOLUME,
        "nominal_flow_rate_m3h": REF_FLOW_RATE,
        "latitude": REF_LATITUDE,
        "user_multiplier": 1.0,
    }
    defaults.update(kwargs)
    return FiltrationInputs(**defaults)


# ──────────────────────────────────────────────
# Interpolation tests
# ──────────────────────────────────────────────

class TestInterpolation:
    def test_exact_match(self):
        table = [(10, 0.5), (20, 1.0), (30, 1.5)]
        assert interpolate(table, 20) == 1.0

    def test_midpoint(self):
        table = [(10, 0.5), (20, 1.0)]
        assert interpolate(table, 15) == pytest.approx(0.75)

    def test_below_range(self):
        table = [(10, 0.5), (20, 1.0)]
        assert interpolate(table, 5) == 0.5

    def test_above_range(self):
        table = [(10, 0.5), (20, 1.0)]
        assert interpolate(table, 25) == 1.0

    def test_empty_table(self):
        assert interpolate([], 10) == 1.0


# ──────────────────────────────────────────────
# Seasonal factor tests
# ──────────────────────────────────────────────

class TestSeasonalFactor:
    def test_may_is_neutral(self):
        assert calculate_seasonal_factor(5, 40.0) == 1.0

    def test_july_is_peak(self):
        assert calculate_seasonal_factor(7, 40.0) == 1.30

    def test_january_is_minimum(self):
        assert calculate_seasonal_factor(1, 40.0) == 0.50

    def test_southern_hemisphere_inverts(self):
        # July in south = January in north
        assert calculate_seasonal_factor(7, -30.0) == 0.50
        # January in south = July in north
        assert calculate_seasonal_factor(1, -30.0) == 1.30


# ──────────────────────────────────────────────
# Manufacturer validation tests
#
# Astralpool table:
#   ≤24°C → 8h, 26°C → 10h, >28°C → 13h
#
# These are for "typical" conditions at those temperatures,
# meaning summer months with typical UV. We test with
# corresponding month/UV combinations.
# ──────────────────────────────────────────────

class TestManufacturerValidation:
    """Validate algorithm output against Astralpool's recommended hours."""

    def test_24c_gives_approximately_8h(self):
        """June at 24°C with UV 7 should give ~8h."""
        result = calculate_filtration_target(make_inputs(
            current_date=date(2025, 6, 15),
            water_temperature_c=24.0,
            uv_index=7.0,
        ))
        hours = result.target_minutes / 60
        assert 7.0 <= hours <= 9.0, f"Expected ~8h, got {hours:.1f}h"

    def test_26c_gives_approximately_10h(self):
        """July at 26°C with UV 8 should give ~10h."""
        result = calculate_filtration_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=26.0,
            uv_index=8.0,
        ))
        hours = result.target_minutes / 60
        assert 9.0 <= hours <= 11.5, f"Expected ~10h, got {hours:.1f}h"

    def test_28c_gives_approximately_13h(self):
        """August at 28°C with UV 9 should give ~13h."""
        result = calculate_filtration_target(make_inputs(
            current_date=date(2025, 8, 15),
            water_temperature_c=28.0,
            uv_index=9.0,
        ))
        hours = result.target_minutes / 60
        assert 12.0 <= hours <= 14.0, f"Expected ~13h, got {hours:.1f}h"


# ──────────────────────────────────────────────
# Full year simulation
# ──────────────────────────────────────────────

class TestFullYearSimulation:
    """Validate that the algorithm produces reasonable results all year."""

    YEAR_SCENARIOS = [
        # (month, water_temp, uv, expected_min_h, expected_max_h, description)
        (1, 12.0, 1, 2.0, 3.0, "January hibernation"),
        (2, 12.0, 2, 2.0, 3.0, "February hibernation"),
        (3, 14.0, 3, 2.0, 3.5, "March cold"),
        (4, 17.0, 4, 3.0, 4.5, "April warming"),
        (5, 20.0, 5, 4.0, 6.0, "May neutral"),
        (6, 24.0, 7, 7.0, 9.0, "June start season"),
        (7, 28.0, 9, 12.0, 14.0, "July peak"),
        (8, 28.0, 9, 12.0, 14.0, "August peak"),
        (9, 23.0, 5, 5.5, 7.5, "September end season"),
        (10, 18.0, 3, 3.0, 4.5, "October cooling"),
        (11, 14.0, 2, 2.0, 3.5, "November cold"),
        (12, 12.0, 1, 2.0, 3.0, "December hibernation"),
    ]

    @pytest.mark.parametrize(
        "month,water_temp,uv,min_h,max_h,desc",
        YEAR_SCENARIOS,
        ids=[s[5] for s in YEAR_SCENARIOS],
    )
    def test_monthly_range(self, month, water_temp, uv, min_h, max_h, desc):
        result = calculate_filtration_target(make_inputs(
            current_date=date(2025, month, 15),
            water_temperature_c=water_temp,
            uv_index=uv,
        ))
        hours = result.target_minutes / 60
        assert min_h <= hours <= max_h, (
            f"{desc}: expected {min_h}-{max_h}h, got {hours:.1f}h "
            f"(factors: s={result.seasonal_factor}, t={result.temperature_factor}, "
            f"uv={result.uv_factor})"
        )


# ──────────────────────────────────────────────
# Edge cases and special conditions
# ──────────────────────────────────────────────

class TestSpecialConditions:
    def test_no_sensor_data_still_works(self):
        """With no optional sensors, algorithm should still produce a result."""
        result = calculate_filtration_target(make_inputs(
            current_date=date(2025, 7, 15),
        ))
        assert result.target_minutes > 0
        assert "No temperature data" in result.warnings[0]

    def test_covered_by_roof_neutralizes_uv_and_rain(self):
        """Covered pool should ignore UV and rain effects."""
        result = calculate_filtration_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
            uv_index=10.0,
            rain_last_24h_mm=30.0,
            is_covered_by_roof=True,
        ))
        assert result.uv_factor == 1.0
        assert result.rain_factor == 1.0

    def test_automatic_cover_on_reduces_target(self):
        result_no_cover = calculate_filtration_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
            uv_index=9.0,
        ))
        result_cover_on = calculate_filtration_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
            uv_index=9.0,
            has_cover="automatic",
            cover_currently_on=True,
        ))
        assert result_cover_on.target_minutes < result_no_cover.target_minutes

    def test_heavy_rain_increases_target(self):
        result_dry = calculate_filtration_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=26.0,
            uv_index=7.0,
            rain_last_24h_mm=0.0,
        ))
        result_rain = calculate_filtration_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=26.0,
            uv_index=7.0,
            rain_last_24h_mm=30.0,
        ))
        assert result_rain.target_minutes > result_dry.target_minutes

    def test_future_rain_slightly_reduces_target(self):
        result_no_rain = calculate_filtration_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=26.0,
            uv_index=7.0,
            rain_next_24h_mm=0.0,
        ))
        result_rain_coming = calculate_filtration_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=26.0,
            uv_index=7.0,
            rain_next_24h_mm=30.0,
        ))
        assert result_rain_coming.target_minutes < result_no_rain.target_minutes

    def test_user_multiplier_scales_target(self):
        result_normal = calculate_filtration_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=26.0,
            uv_index=7.0,
        ))
        result_high = calculate_filtration_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=26.0,
            uv_index=7.0,
            user_multiplier=1.5,
        ))
        # Should be approximately 1.5x
        ratio = result_high.target_minutes / result_normal.target_minutes
        assert 1.3 <= ratio <= 1.6

    def test_minimum_never_below_one_turnover(self):
        """Even in winter with cover, target should never go below 1 turnover."""
        result = calculate_filtration_target(make_inputs(
            current_date=date(2025, 1, 15),
            water_temperature_c=8.0,
            uv_index=0.0,
            has_cover="automatic",
            cover_currently_on=True,
            user_multiplier=0.5,
        ))
        one_turnover = round((REF_VOLUME / REF_FLOW_RATE) * 60)
        assert result.target_minutes >= one_turnover

    def test_result_includes_sources(self):
        result = calculate_filtration_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
            uv_index=9.0,
        ))
        assert "temperature" in result.sources
        assert result.sources["temperature"] == "water_temperature_sensor"
        assert "uv" in result.sources
