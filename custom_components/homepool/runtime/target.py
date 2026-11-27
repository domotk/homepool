"""The forecast and the daily filtration target.

A mixin of ``PoolCoordinator``; see coordinator.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.util import dt as dt_util

from ..const import (
    CONF_CHLORINATOR_NOMINAL_PRODUCTION,
    CONF_COVER_ENTITY,
    CONF_HAS_COVER,
    CONF_IS_COVERED_BY_ROOF,
    CONF_LATITUDE,
    CONF_RAIN_SENSOR,
    CONF_SALT_TARGET,
    CONF_UV_SENSOR,
    CONF_WEATHER_ENTITY,
    DEFAULT_SALT_TARGET,
    EVENT_TARGET_RECALCULATED,
    RECALC_INTERVAL_MIN,
)
from ..pool.chlorine_calculator import ChlorineInputs, calculate_chlorine_target
from ..pool.filtration_calculator import FiltrationInputs, calculate_filtration_target

_LOGGER = logging.getLogger("custom_components.homepool.coordinator")


def _todays_forecast(days: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """The daily forecast entry for ``today``.

    Providers date a day differently: Open-Meteo at 00:00 UTC, so in Spain the
    first entry is still yesterday until 01:00. The date as the provider wrote
    it is the day it means, whatever the offset; the first entry is the
    fallback when no entry names today.
    """
    for day in days:
        stamp = day.get("datetime")
        written = stamp.isoformat() if isinstance(stamp, datetime) else str(stamp or "")
        if written[:10] == today.isoformat():
            return day
    return days[0]

# How far the pool's own air sensor may read above the forecast high.
MEASURED_AIR_MARGIN_C = 3.0


class TargetMixin:
    """The forecast and the daily filtration target."""

    async def _async_forecast(self, now: datetime) -> None:
        """Today's high and rain from the weather entity, fetched at most once an hour.

        A new local day fetches again, and today's entry is picked from what was
        fetched on every call: a forecast fetched at 23:26 still names
        yesterday, and the recalculation at midnight must not use it.
        """
        weather = self.conf.get(CONF_WEATHER_ENTITY)
        if not weather:
            return
        today = dt_util.as_local(now).date()
        fresh = (
            self._forecast_at is not None
            and now - self._forecast_at < timedelta(hours=1)
            and dt_util.as_local(self._forecast_at).date() == today
        )
        if not fresh:
            self._forecast_at = now
            try:
                response = await self.hass.services.async_call(
                    "weather",
                    "get_forecasts",
                    {"entity_id": weather, "type": "daily"},
                    blocking=True,
                    return_response=True,
                )
            except Exception:  # noqa: BLE001 - weather is a nice-to-have, never a blocker
                _LOGGER.debug("%s: no daily forecast from %s", self.pool_name, weather)
                response = None
            self._forecast_days = ((response or {}).get(weather) or {}).get("forecast") or []
        if not self._forecast_days:
            self._forecast = {}
            return
        first = _todays_forecast(self._forecast_days, today)
        self._forecast = {
            "high": first.get("temperature"),
            "rain_mm": first.get("precipitation"),
            "uv": first.get("uv_index"),
        }

    def _temperature_inputs(self) -> tuple[float | None, float | None, str]:
        """Water temperature, or the air figure to estimate it from."""
        water = self.water_temperature
        if water is not None:
            return water, None, "water_temperature_sensor"
        # What the pool's own sensor measured beats a forecast for a grid
        # cell kilometres away. Today's maximum so far, or yesterday's if that
        # was warmer: early in the morning today's is still the night's low,
        # and the target only rises as the day warms up.
        # A sensor in the sun, or on a heat pump's outdoor unit, reads well
        # above the shade temperature, and the maximum is the figure most
        # thrown by it; so with a forecast at hand the measurement may top
        # the forecast high by MEASURED_AIR_MARGIN_C at most.
        high = self._forecast.get("high")
        high = float(high) if isinstance(high, (int, float)) else None
        observed = [v for v in (self.air_max.get("today"), self.air_max.get("yesterday")) if v is not None]
        if observed:
            air = max(observed)
            if high is not None and air > high + MEASURED_AIR_MARGIN_C:
                return None, round(high + MEASURED_AIR_MARGIN_C, 1), "air_temperature_max_capped"
            return None, air, "air_temperature_max"
        if high is not None:
            return None, high, "forecast_high"
        return None, None, "none"

    def _uv(self) -> tuple[float | None, str | None]:
        value = self._number(CONF_UV_SENSOR)
        if value is not None:
            return value, "uv_sensor"
        weather = self._state(CONF_WEATHER_ENTITY)
        if weather is not None and isinstance(weather.attributes.get("uv_index"), (int, float)):
            return float(weather.attributes["uv_index"]), "weather_entity"
        uv = self._forecast.get("uv")
        if isinstance(uv, (int, float)):
            return float(uv), "forecast"
        return None, None

    async def _async_maybe_recalculate(self, now: datetime, force: bool = False) -> None:
        if (
            not force
            and self.target
            and self.target_at is not None
            and now - self.target_at < timedelta(minutes=RECALC_INTERVAL_MIN)
        ):
            return
        await self._async_forecast(now)
        result = self.calculate_target(dt_util.as_local(now).date())
        old = self.target_minutes
        if self.target and not force and result["target_minutes"] < old:
            # During a day the target only ever goes up. A target that drops in
            # the afternoon because a cloud cooled the air is what made the old
            # automations stop half way; the day's demand does not shrink.
            # calculated_minutes keeps what today's conditions ask for now,
            # so the held figure and its components can be told apart.
            result = {
                **result,
                "target_minutes": old,
                "calculated_minutes": result["target_minutes"],
                "held_at_previous": True,
            }
        self.target = result
        self.target_at = now
        if result["target_minutes"] != old:
            self.hass.bus.async_fire(
                EVENT_TARGET_RECALCULATED,
                {
                    "entry_id": self.entry.entry_id,
                    "pool": self.pool_name,
                    "old": old,
                    "new": result["target_minutes"],
                    "factors": result.get("factors", {}),
                },
            )

    def calculate_target(self, today: date) -> dict[str, Any]:
        """Run both calculators with whatever data is available right now."""
        water, air, temp_source = self._temperature_inputs()
        uv, uv_source = self._uv()
        rain_past = self._number(CONF_RAIN_SENSOR)
        rain_next = self._forecast.get("rain_mm")
        cover_on = None
        if self.conf.get(CONF_HAS_COVER) == "automatic":
            cover_state = self._state(CONF_COVER_ENTITY)
            if cover_state is not None:
                cover_on = cover_state.state == "closed"
        latitude = float(self.opt(CONF_LATITUDE, self.hass.config.latitude) or 0)

        if self.volume <= 0 or self.flow_rate <= 0:
            return {
                "target_minutes": 0,
                "target_filtration_minutes": 0,
                "target_chlorine_minutes": None,
                "warnings": ["Pool volume or pump flow rate missing"],
            }

        filt = calculate_filtration_target(
            FiltrationInputs(
                pool_volume_m3=self.volume,
                nominal_flow_rate_m3h=self.flow_rate,
                latitude=latitude,
                has_cover=self.conf.get(CONF_HAS_COVER) or "none",
                is_covered_by_roof=bool(self.conf.get(CONF_IS_COVERED_BY_ROOF)),
                cover_currently_on=cover_on,
                user_multiplier=self.user_multiplier,
                current_date=today,
                water_temperature_c=water,
                air_temperature_c=air,
                uv_index=uv,
                rain_last_24h_mm=rain_past,
                rain_next_24h_mm=float(rain_next) if isinstance(rain_next, (int, float)) else None,
            )
        )
        sources = dict(filt.sources)
        sources["temperature"] = temp_source
        if uv_source:
            sources["uv"] = uv_source
        if rain_past is not None:
            sources["rain"] = "rain_sensor"
        warnings = list(filt.warnings)

        chlorine_minutes = None
        recommended = None
        chlorine_info: dict[str, Any] = {}
        if self.is_salt and self.opt(CONF_CHLORINATOR_NOMINAL_PRODUCTION):
            salt, salt_source = self.salinity
            chlorine_kwargs: dict[str, Any] = {
                "pool_volume_m3": self.volume,
                "chlorinator_nominal_production_g_h": float(
                    self.opt(CONF_CHLORINATOR_NOMINAL_PRODUCTION)
                ),
                "chlorinator_production_pct": self.chlorinator_production,
                "chlorinator_self_regulating": self.self_regulating,
                # The season state decides whether the cell works today
                # (ruling 24); with "Chlorinator in use" off it produces
                # nothing either. Out of season it adds no minutes.
                "chlorinator_active_months": (
                    [today.month] if self.cell_in_season and self.chlorinator_enabled else []
                ),
                "water_temperature_c": water,
                "air_temperature_c": air,
                "salt_level_g_l": salt,
                "salt_target_g_l": float(self.opt(CONF_SALT_TARGET, DEFAULT_SALT_TARGET)),
                "current_date": today,
                "latitude": latitude,
            }
            first = calculate_chlorine_target(ChlorineInputs(**chlorine_kwargs))
            chlorine_minutes = first.target_chlorine_minutes
            # The recommended production depends on the final target, so it is
            # worked out again once the final target is known.
            total = max(filt.target_minutes, chlorine_minutes or 0)
            second = calculate_chlorine_target(
                ChlorineInputs(**chlorine_kwargs, total_target_minutes=total)
            )
            recommended = second.recommended_production_pct
            warnings.extend(first.warnings)
            if salt_source:
                sources["salinity"] = salt_source
            chlorine_info = {
                "chlorine_demand_g": first.chlorine_demand_g_per_day,
                "effective_production_g_h": first.effective_production_g_h,
                "salinity_factor": first.salinity_factor,
                "cold_water_factor": first.cold_water_factor,
                # The calendar's answer, as before; whether the cell counted
                # shows in target_chlorine_minutes.
                "chlorinator_in_season": self.in_season,
            }

        target = max(filt.target_minutes, chlorine_minutes or 0)
        return {
            "target_minutes": target,
            "target_filtration_minutes": filt.target_minutes,
            "target_chlorine_minutes": chlorine_minutes,
            "dominant_component": (
                "chlorine" if (chlorine_minutes or 0) > filt.target_minutes else "filtration"
            ),
            "base_minutes": filt.base_minutes,
            "factors": {
                "seasonal": filt.seasonal_factor,
                "temperature": filt.temperature_factor,
                "uv": filt.uv_factor,
                "rain": filt.rain_factor,
                "cover": filt.cover_factor,
                "user_multiplier": filt.user_multiplier,
            },
            "clamped": filt.was_clamped,
            "min_minutes": filt.min_minutes,
            "max_minutes": filt.max_minutes,
            "recommended_chlorinator_pct": recommended,
            "inputs": {
                "water_temperature": water,
                "air_temperature": air,
                "uv_index": uv,
                "rain_last_24h_mm": rain_past,
                "rain_next_24h_mm": rain_next,
            },
            **chlorine_info,
            "sources": sources,
            "warnings": warnings,
        }
