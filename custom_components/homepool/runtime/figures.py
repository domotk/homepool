"""Figures derived from the counters, the target and the readings.

A mixin of ``PoolCoordinator``; see coordinator.py.
"""

from __future__ import annotations

from homeassistant.util import dt as dt_util

from ..const import (
    CONF_ENERGY_PRICE,
    CONF_ENERGY_PRICE_ENTITY,
    CONF_EQUIPMENT_ROOM_MAX_TEMP,
    CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR,
    CONF_FLOOD_SENSOR,
    CONF_FREEZE_THRESHOLD,
    CONF_PH_RANGE_MAX,
    CONF_PH_RANGE_MIN,
    CONF_PUMP_ENERGY_SENSOR,
    CONF_SOLAR_EXCESS_SENSOR,
    CONF_TIMER_SLOTS,
    CONF_WINTER_PRODUCT_TYPE,
    DEFAULT_EQUIPMENT_ROOM_MAX_TEMP,
    DEFAULT_FREEZE_THRESHOLD,
    DEFAULT_PH_RANGE_MAX,
    DEFAULT_PH_RANGE_MIN,
    ChlorinationMode,
    OperationMode,
    OverallStatus,
)
from ..pool.chlorine_calculator import is_chlorinator_in_season
from ..pool.season import WINTER_STATES, SeasonState


def parse_timer_slots(text_value: str | None) -> list[tuple[int, int]]:
    """``"08:00-12:00, 18:30-20:00"`` → minutes of the day. Bad parts are skipped."""
    slots: list[tuple[int, int]] = []
    for part in (text_value or "").replace(";", ",").split(","):
        start, sep, end = part.strip().partition("-")
        if not sep:
            continue
        try:
            sh, sm = (int(x) for x in start.strip().split(":"))
            eh, em = (int(x) for x in end.strip().split(":"))
        except ValueError:
            continue
        if not (0 <= sh <= 24 and 0 <= eh <= 24 and 0 <= sm < 60 and 0 <= em < 60):
            continue
        slots.append(((sh * 60 + sm) % 1440, (eh * 60 + em) % 1440))
    return slots


def _whole_minutes(seconds: float) -> int:
    """Seconds to the nearest minute. Truncating left the count a minute behind."""
    return int(seconds / 60 + 0.5)


class FiguresMixin:
    """Figures derived from the counters, the target and the readings."""

    @property
    def elapsed_minutes(self) -> int:
        return _whole_minutes(self.elapsed_s)

    @property
    def chlorine_minutes(self) -> int:
        return _whole_minutes(self.chlorine_s)

    @property
    def ph_correction_minutes(self) -> int:
        return _whole_minutes(self.ph_correction_s)

    @property
    def target_minutes(self) -> int:
        return int(self.target.get("target_minutes") or 0)

    @property
    def filtration_component(self) -> int | None:
        return self.target.get("target_filtration_minutes")

    @property
    def chlorine_component(self) -> int | None:
        return self.target.get("target_chlorine_minutes")

    @property
    def remaining_minutes(self) -> int:
        return max(0, self.target_minutes - self.elapsed_minutes)

    @property
    def target_reached(self) -> bool:
        return self.target_minutes > 0 and self.elapsed_minutes >= self.target_minutes

    @property
    def chlorine_target_reached(self) -> bool:
        target = self.chlorine_component
        if not target:
            return False
        return self.chlorine_minutes >= target

    @property
    def chlorine_remaining(self) -> int | None:
        target = self.chlorine_component
        if target is None:
            return None
        return max(0, target - self.chlorine_minutes)

    @property
    def recommended_production(self) -> float | None:
        return self.target.get("recommended_chlorinator_pct")

    @property
    def in_season(self) -> bool:
        return is_chlorinator_in_season(dt_util.now().date(), self.active_months)

    @property
    def cell_in_season(self) -> bool:
        """Whether the season state has the cell working (ruling 24).

        Swimming, and opening once "Chlorinator in use" is on; never in
        winter. ``chlorinator_active_months`` no longer decides this: it only
        seeds the swimming months and fires the calendar's season events.
        """
        if self.season_state == SeasonState.SWIMMING:
            return True
        if self.season_state == SeasonState.OPENING:
            return self.chlorinator_enabled
        return False

    @property
    def chlorination_mode(self) -> str:
        if (
            self.season_state in WINTER_STATES
            and self.opt(CONF_WINTER_PRODUCT_TYPE, "none") != "none"
        ):
            return ChlorinationMode.WINTER_PRODUCT
        if not self.is_salt:
            return ChlorinationMode.TABLETS
        if self.cell_in_season and self.chlorinator_enabled:
            return ChlorinationMode.SALT
        return ChlorinationMode.OFF

    @property
    def ph_out_of_range(self) -> bool:
        ph = self.ph
        if ph is None or (self.winter_passive and self.ph_probe is not None):
            # Drained pipes in passive wintering: the probe reads air or a dry cup.
            return False
        low = float(self.opt(CONF_PH_RANGE_MIN, DEFAULT_PH_RANGE_MIN))
        high = float(self.opt(CONF_PH_RANGE_MAX, DEFAULT_PH_RANGE_MAX))
        return not low <= ph <= high

    @property
    def critical_water_temperature(self) -> bool:
        temp = self.water_temperature
        if temp is None:
            return False
        return temp < float(self.opt(CONF_FREEZE_THRESHOLD, DEFAULT_FREEZE_THRESHOLD)) or temp > 33

    @property
    def equipment_room_overheat(self) -> bool:
        temp = self._number(CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR)
        if temp is None:
            return False
        return temp > float(self.opt(CONF_EQUIPMENT_ROOM_MAX_TEMP, DEFAULT_EQUIPMENT_ROOM_MAX_TEMP))

    @property
    def flood(self) -> bool:
        return self._is_on(CONF_FLOOD_SENSOR) is True

    @property
    def overall_status(self) -> str:
        if (
            self.safety_active
            or "pump_not_responding" in self.alerts
            or "chlorinator_not_responding" in self.alerts
        ):
            return OverallStatus.ACTION_REQUIRED
        if (
            any(name != "reading_stale" for name in self.alerts)
            or self.manual_action_pending
            or self.ph_out_of_range
            or self.pump_anomaly
        ):
            return OverallStatus.ATTENTION
        return OverallStatus.OK

    @property
    def pump_energy_today(self) -> float | None:
        reading = self._number(CONF_PUMP_ENERGY_SENSOR)
        if reading is None:
            return None
        if self.energy_baseline is None or reading < self.energy_baseline:
            # First reading of the day, or the meter was reset: start from here.
            self.energy_baseline = reading
            self._save()
        return round(reading - self.energy_baseline, 3)

    @property
    def energy_price(self) -> float | None:
        entity_price = self._number(CONF_ENERGY_PRICE_ENTITY)
        if entity_price is not None:
            return entity_price
        price = self.opt(CONF_ENERGY_PRICE)
        return float(price) if price not in (None, "") else None

    @property
    def pump_cost_today(self) -> float | None:
        energy = self.pump_energy_today
        price = self.energy_price
        if energy is None or price is None:
            return None
        return round(energy * price, 3)

    @property
    def timer_slots(self) -> list[tuple[int, int]]:
        return parse_timer_slots(self.conf.get(CONF_TIMER_SLOTS))

    def available_modes(self) -> list[str]:
        modes = [OperationMode.OFF, OperationMode.TIMER, OperationMode.SMART]
        if self.has(CONF_SOLAR_EXCESS_SENSOR):
            modes += [OperationMode.SOLAR, OperationMode.SMART_SOLAR]
        return [str(m) for m in modes]
