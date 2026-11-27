"""Configuration and the settings people change from entities.

A mixin of ``PoolCoordinator``; see coordinator.py.
"""

from __future__ import annotations

from typing import Any

from ..const import (
    CONF_CHLORINATION_TYPE,
    CONF_CHLORINATOR_ACTIVE_MONTHS,
    CONF_CHLORINATOR_PRODUCTION_DEFAULT,
    CONF_CHLORINATOR_SELF_REGULATING,
    CONF_LATITUDE,
    CONF_PH_TARGET,
    CONF_POOL_NAME,
    CONF_PUMP_NOMINAL_FLOW_RATE,
    CONF_PUMP_NOMINAL_POWER,
    CONF_SWIMMING_MONTHS,
    CONF_VOLUME,
    DEFAULT_CHLORINATOR_PRODUCTION_PCT,
    DEFAULT_OPERATION_MODE,
    DEFAULT_PH_TARGET,
    DEFAULT_USER_MULTIPLIER,
)
from ..pool.geometry import calculate_cycle_duration_minutes
from ..pool.season import default_swimming_months


class ConfigMixin:
    """Configuration and the settings people change from entities."""

    @property
    def conf(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def opt(self, key: str, default: Any = None) -> Any:
        value = self.conf.get(key)
        return default if value in (None, "") else value

    @property
    def pool_name(self) -> str:
        return self.conf.get(CONF_POOL_NAME) or self.entry.title

    @property
    def is_salt(self) -> bool:
        return self.conf.get(CONF_CHLORINATION_TYPE) == "salt"

    @property
    def self_regulating(self) -> bool:
        return bool(self.conf.get(CONF_CHLORINATOR_SELF_REGULATING))

    def has(self, key: str) -> bool:
        return bool(self.conf.get(key))

    @property
    def volume(self) -> float:
        return float(self.opt(CONF_VOLUME, 0) or 0)

    @property
    def flow_rate(self) -> float:
        return float(self.opt(CONF_PUMP_NOMINAL_FLOW_RATE, 0) or 0)

    @property
    def cycle_duration(self) -> int | None:
        if self.volume <= 0 or self.flow_rate <= 0:
            return None
        return calculate_cycle_duration_minutes(self.volume, self.flow_rate)

    @property
    def active_months(self) -> list[int]:
        months = self.conf.get(CONF_CHLORINATOR_ACTIVE_MONTHS) or []
        return sorted(int(m) for m in months)

    @property
    def swimming_months(self) -> list[int]:
        """The months the pool is used: what season proposals follow."""
        months = self.conf.get(CONF_SWIMMING_MONTHS)
        if months:
            return sorted(int(m) for m in months)
        latitude = float(self.opt(CONF_LATITUDE, self.hass.config.latitude) or 0)
        return default_swimming_months(self.active_months, self.is_salt, latitude)

    # Settings changed from entities: stored, not in the config entry, so that
    # moving a slider does not reload the whole integration.
    @property
    def mode(self) -> str:
        return self.settings.get("mode", DEFAULT_OPERATION_MODE)

    @property
    def user_multiplier(self) -> float:
        return float(self.settings.get("user_multiplier", DEFAULT_USER_MULTIPLIER))

    @property
    def maintenance_lock(self) -> bool:
        return bool(self.settings.get("maintenance_lock", False))

    @property
    def chlorinator_enabled(self) -> bool:
        return bool(self.settings.get("chlorinator_enabled", True))

    @property
    def solar_threshold(self) -> float:
        default = float(self.opt(CONF_PUMP_NOMINAL_POWER, 0) or 0) or 800.0
        return float(self.settings.get("solar_threshold", default))

    @property
    def ph_target(self) -> float:
        return float(
            self.settings.get("ph_target", self.opt(CONF_PH_TARGET, DEFAULT_PH_TARGET))
        )

    @property
    def chlorinator_production(self) -> float:
        return float(
            self.settings.get(
                "chlorinator_production",
                self.opt(CONF_CHLORINATOR_PRODUCTION_DEFAULT, DEFAULT_CHLORINATOR_PRODUCTION_PCT),
            )
        )
