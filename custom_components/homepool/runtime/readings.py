"""Reading the pool's entities, and the samples the loop keeps of them.

A mixin of ``PoolCoordinator``; see coordinator.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import math

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_ON, UnitOfPower
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_AIR_TEMPERATURE_SENSOR,
    CONF_FILTER_PRESSURE_SENSOR,
    CONF_FREE_CHLORINE_SENSOR,
    CONF_ORP_SENSOR,
    CONF_PH_SENSOR,
    CONF_PUMP_NOMINAL_POWER,
    CONF_PUMP_POWER_SENSOR,
    CONF_PUMP_SWITCH,
    CONF_SALINITY_SENSOR,
    CONF_WATER_TEMPERATURE_SENSOR,
    CONF_WEATHER_ENTITY,
    PhTrend,
)
from ..pool.season import SeasonState
from ..pool.readings import DEFAULT_STALE_DAYS, ReadingStatus, default_range, reading_status
from ..pool.tasks import TASKS_BY_KEY
from .common import BAD_STATES, WATER_TEST_KINDS, _parse_dt


class ReadingsMixin:
    """Reading the pool's entities, and the samples the loop keeps of them."""

    def _state(self, key: str):
        entity_id = self.conf.get(key)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in BAD_STATES:
            return None
        return state

    def _is_on(self, key: str) -> bool | None:
        state = self._state(key)
        if state is None:
            return None
        return state.state in (STATE_ON, "open", "heat", "true")

    def _number(self, key: str) -> float | None:
        """A sensor's number, or None: nan and inf are a faulty sensor, not a
        reading, and every comparison with them would quietly be false."""
        state = self._state(key)
        if state is None:
            return None
        try:
            value = float(state.state)
        except ValueError:
            return None
        return value if math.isfinite(value) else None

    def _watts(self, key: str) -> float | None:
        """A power reading in W, whatever unit the sensor uses."""
        value = self._number(key)
        if value is None:
            return None
        unit = self._state(key).attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if unit == UnitOfPower.KILO_WATT:
            return value * 1000
        return value

    @property
    def pump_power(self) -> float | None:
        """Measured draw, or the nameplate figure while running if unmeasured."""
        measured = self._watts(CONF_PUMP_POWER_SENSOR)
        if measured is not None:
            return measured
        nominal = self.opt(CONF_PUMP_NOMINAL_POWER)
        return float(nominal) if nominal and self._pump_was_on else None

    @property
    def water_temperature(self) -> float | None:
        return self._number(CONF_WATER_TEMPERATURE_SENSOR)

    @property
    def air_temperature(self) -> float | None:
        value = self._number(CONF_AIR_TEMPERATURE_SENSOR)
        if value is not None:
            return value
        weather = self._state(CONF_WEATHER_ENTITY)
        if weather is not None:
            temp = weather.attributes.get("temperature")
            if isinstance(temp, (int, float)):
                return float(temp)
        return None

    @property
    def ph_probe(self) -> float | None:
        """The pH probe alone: the correction and the trend never run on a reading by hand."""
        return self._number(CONF_PH_SENSOR)

    @property
    def ph(self) -> float | None:
        probe = self.ph_probe
        if probe is not None:
            return probe
        return self._fresh_manual("ph")

    @property
    def salinity(self) -> tuple[float | None, str | None]:
        value = self._number(CONF_SALINITY_SENSOR)
        if value is not None:
            return value, "salinity_sensor"
        manual = self._fresh_manual("salt")
        if manual is not None:
            return manual, "manual_record"
        return None, None

    @property
    def free_chlorine(self) -> tuple[float | None, str | None]:
        value = self._number(CONF_FREE_CHLORINE_SENSOR)
        if value is not None:
            return value, "free_chlorine_sensor"
        manual = self._fresh_manual("free_chlorine")
        if manual is not None:
            return manual, "manual_record"
        return None, None

    def reading_range(self, kind: str) -> tuple[float | None, float | None]:
        """The acceptable range of a kind: its options over the defaults."""
        low, high = default_range(kind, self.is_salt)
        low = self.opt(f"{kind}_range_min", low)
        high = self.opt(f"{kind}_range_max", high)
        return (
            None if low is None else float(low),
            None if high is None else float(high),
        )

    def reading_stale_days(self, kind: str) -> int:
        """How long a reading by hand is trusted. In active wintering the pH
        and the free chlorine are measured on the water test's (longer)
        interval, so they are not stale before it falls due."""
        days = int(self.opt(f"{kind}_stale_days", DEFAULT_STALE_DAYS[kind]))
        if kind in WATER_TEST_KINDS and self.season_state == SeasonState.WINTER_ACTIVE:
            interval = self._task_days(TASKS_BY_KEY["water_test"])
            if interval is not None:
                days = max(days, interval)
        return days

    def manual_status(self, kind: str) -> ReadingStatus:
        """The last reading taken by hand, whether it is stale and whether it is out of range."""
        record = self.manual_readings.get(kind)
        low, high = self.reading_range(kind)
        return reading_status(
            kind,
            float(record["value"]) if record else None,
            _parse_dt(record.get("at")) if record else None,
            dt_util.utcnow(),
            low,
            high,
            self.reading_stale_days(kind),
        )

    def _fresh_manual(self, kind: str) -> float | None:
        """A reading by hand that is not stale, or None."""
        status = self.manual_status(kind)
        return None if status.stale else status.value

    @property
    def orp(self) -> float | None:
        return self._number(CONF_ORP_SENSOR)

    @property
    def filter_pressure(self) -> float | None:
        return self._number(CONF_FILTER_PRESSURE_SENSOR)

    @property
    def pump_is_on(self) -> bool:
        return self._pump_was_on

    @property
    def pump_available(self) -> bool:
        return self._is_on(CONF_PUMP_SWITCH) is not None

    @property
    def chlorinator_is_on(self) -> bool:
        return self._chlor_was_on

    def _sample_inputs(self, now: datetime) -> None:
        air = self.air_temperature
        if air is not None:
            current = self.air_max.get("today")
            if current is None or air > current:
                self.air_max["today"] = air
        ph = self.ph_probe
        if ph is not None and (
            not self._ph_samples or now - self._ph_samples[-1][0] >= timedelta(minutes=10)
        ):
            self._ph_samples.append((now, ph))
        self.ph_trend = self._compute_ph_trend()

    def _compute_ph_trend(self) -> str | None:
        """Slope of the last three hours of readings, in pH per hour."""
        if not self.has(CONF_PH_SENSOR):
            return None
        if len(self._ph_samples) < 4:
            return PhTrend.STABLE
        latest = self._ph_samples[-1][0]
        window = [(t, v) for t, v in self._ph_samples if latest - t <= timedelta(hours=3)]
        if len(window) < 4:
            return PhTrend.STABLE
        t0 = window[0][0]
        xs = [(t - t0).total_seconds() / 3600 for t, _ in window]
        ys = [v for _, v in window]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        den = sum((x - mean_x) ** 2 for x in xs)
        if den == 0:
            return PhTrend.STABLE
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / den
        if slope > 0.03:
            return PhTrend.RISING
        if slope < -0.03:
            return PhTrend.FALLING
        return PhTrend.STABLE
