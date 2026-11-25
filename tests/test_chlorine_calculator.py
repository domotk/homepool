"""Tests for the chlorine production target calculator.

Uses the reference pool with Astralpool SEL-E4 55 chlorinator (35 g/h).
"""

import pytest
from datetime import date

from custom_components.homepool.pool.chlorine_calculator import (
    ChlorineInputs,
    calculate_chlorine_target,
    is_chlorinator_in_season,
    calculate_recommended_production_pct,
)


REF_VOLUME = 30.0
REF_CHLORINATOR_PRODUCTION = 35.0  # SEL-E4 55
REF_PRODUCTION_PCT = 70.0
REF_ACTIVE_MONTHS = [6, 7, 8, 9]


def make_inputs(**kwargs) -> ChlorineInputs:
    defaults = {
        "pool_volume_m3": REF_VOLUME,
        "chlorinator_nominal_production_g_h": REF_CHLORINATOR_PRODUCTION,
        "chlorinator_production_pct": REF_PRODUCTION_PCT,
        "chlorinator_active_months": REF_ACTIVE_MONTHS,
        "salt_target_g_l": 4.0,
    }
    defaults.update(kwargs)
    return ChlorineInputs(**defaults)


class TestChlorinatorCalendar:
    def test_in_season_july(self):
        assert is_chlorinator_in_season(date(2025, 7, 15), [6, 7, 8, 9])

    def test_out_of_season_january(self):
        assert not is_chlorinator_in_season(date(2025, 1, 15), [6, 7, 8, 9])

    def test_out_of_season_returns_none_target(self):
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 1, 15),
        ))
        assert result.target_chlorine_minutes is None
        assert not result.is_chlorinator_active

    def test_in_season_returns_target(self):
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
        ))
        assert result.target_chlorine_minutes is not None
        assert result.is_chlorinator_active


class TestChlorineDemand:
    def test_summer_demand_30m3(self):
        """At 28°C, demand should be ~5 g/m³/day → 150g for 30m³."""
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
        ))
        assert 120 <= result.chlorine_demand_g_per_day <= 160

    def test_moderate_demand_20c(self):
        """At 20°C, demand should be ~2.5 g/m³/day → 75g for 30m³."""
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 6, 15),
            water_temperature_c=20.0,
        ))
        assert 60 <= result.chlorine_demand_g_per_day <= 90


class TestSalinityEffect:
    def test_optimal_salt_full_production(self):
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
            salt_level_g_l=4.0,
        ))
        assert result.salinity_factor == 1.0

    def test_low_salt_reduces_production(self):
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
            salt_level_g_l=3.0,
        ))
        assert result.salinity_factor < 1.0
        assert result.salinity_factor == pytest.approx(0.75)

    def test_very_low_salt_warns(self):
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
            salt_level_g_l=2.5,
        ))
        assert any("critically low" in w for w in result.warnings)

    def test_low_salt_increases_needed_hours(self):
        result_normal = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
            salt_level_g_l=4.0,
        ))
        result_low = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
            salt_level_g_l=3.0,
        ))
        assert result_low.target_chlorine_minutes > result_normal.target_chlorine_minutes


class TestColdWaterEffect:
    def test_warm_water_full_efficiency(self):
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=25.0,
        ))
        assert result.cold_water_factor == 1.0

    def test_cold_water_reduces_efficiency(self):
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 6, 1),
            water_temperature_c=15.0,
            chlorinator_active_months=[6, 7, 8, 9],
        ))
        assert result.cold_water_factor < 1.0
        assert result.cold_water_factor == pytest.approx(0.6)

    def test_very_cold_water_warns(self):
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 6, 1),
            water_temperature_c=12.0,
            chlorinator_active_months=[6, 7, 8, 9],
        ))
        assert any("reduces" in w for w in result.warnings)


class TestRecommendedProduction:
    def test_oversized_chlorinator_recommends_lower_pct(self):
        """SEL-55 on a 30m³ pool at 28°C with 13h filtration should
        recommend much less than the typical 70% setting."""
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
            salt_level_g_l=4.0,
            total_target_minutes=784,  # ~13h
        ))
        assert result.recommended_production_pct is not None
        assert result.recommended_production_pct < 50.0
        # For 150g demand, 35 g/h × 13h = 455g at 100%, so ~33% needed
        assert 20.0 <= result.recommended_production_pct <= 45.0

    def test_self_regulating_skips_recommendation(self):
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 7, 15),
            water_temperature_c=28.0,
            chlorinator_self_regulating=True,
            total_target_minutes=784,
        ))
        assert result.recommended_production_pct is None

    def test_calculate_recommended_direct(self):
        pct = calculate_recommended_production_pct(
            chlorine_demand_g=120.0,
            nominal_production_g_h=35.0,
            total_target_hours=13.0,
            salinity_factor=1.0,
            cold_water_factor=1.0,
        )
        assert pct is not None
        assert 25.0 <= pct <= 30.0  # 120 / (35 × 13) × 100 ≈ 26.4%


class TestReferencePoolAugust:
    """Full validation of the reference pool in August conditions."""

    def test_august_typical(self):
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 8, 15),
            water_temperature_c=28.0,
            salt_level_g_l=4.0,
        ))
        hours = result.target_chlorine_minutes / 60
        # Should be around 4-6h (chlorinator is oversized)
        assert 4.0 <= hours <= 7.0, f"Expected 4-7h, got {hours:.1f}h"

    def test_august_low_salt(self):
        result = calculate_chlorine_target(make_inputs(
            current_date=date(2025, 8, 15),
            water_temperature_c=28.0,
            salt_level_g_l=3.0,
        ))
        hours = result.target_chlorine_minutes / 60
        # Should be higher than normal due to reduced efficiency
        assert hours > 6.0
