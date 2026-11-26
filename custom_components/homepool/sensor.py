"""HomePool sensors: the target, today's progress, and the pool's health."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CHLORINATOR_SWITCH,
    CONF_ENERGY_PRICE,
    CONF_ENERGY_PRICE_ENTITY,
    CONF_PH_SENSOR,
    CONF_PUMP_ENERGY_SENSOR,
    ChlorinationMode,
    OverallStatus,
    PhTrend,
)
from .coordinator import PoolCoordinator
from .entity import PoolEntity


@dataclass(frozen=True, kw_only=True)
class PoolSensorDescription(SensorEntityDescription):
    value_fn: Callable[[PoolCoordinator], Any]
    exists_fn: Callable[[PoolCoordinator], bool] = lambda c: True
    attrs_fn: Callable[[PoolCoordinator], dict[str, Any]] | None = None


def _target_attrs(c: PoolCoordinator) -> dict[str, Any]:
    t = c.target
    return {
        "base_minutes": t.get("base_minutes"),
        **{f"{k}_factor": v for k, v in (t.get("factors") or {}).items()},
        "target_filtration_minutes": t.get("target_filtration_minutes"),
        "target_chlorine_minutes": t.get("target_chlorine_minutes"),
        "dominant_component": t.get("dominant_component"),
        "clamped": t.get("clamped"),
        # The floor and ceiling the target was clamped between: the floor is
        # why a cold day's target stops falling.
        "min_minutes": t.get("min_minutes"),
        "max_minutes": t.get("max_minutes"),
        "held_at_previous": t.get("held_at_previous", False),
        "calculated_minutes": t.get("calculated_minutes", t.get("target_minutes")),
        "inputs": t.get("inputs"),
        "sources": t.get("sources"),
        "warnings": t.get("warnings"),
        "calculated_at": c.target_at.isoformat() if c.target_at else None,
        **c.card_attributes(),
        "history": c.history[-14:],
    }


def _control_attrs(c: PoolCoordinator) -> dict[str, Any]:
    return {
        "reason": c.decision_reason,
        "reason_key": c.decision_key or None,
        "operation_mode": c.mode,
        "chlorinator": c.chlorinator_reason or None,
        # To the nearest 100 W: every change of an attribute is a new state
        # row in the recorder, and a grid meter changes every few seconds.
        "surplus_w": int(round(c.surplus_w, -2)) if c.surplus_w is not None else None,
        "solar_threshold_w": c.solar_threshold,
        "manual_override_until": (c.override or {}).get("until"),
        # An override saved by 0.1.1 has no "by": it was a person, as the
        # control already assumes.
        "manual_override_by": (
            ((c.override or {}).get("by") or "user") if c.override else None
        ),
        "manual_cycle_until": c.cycle_until.isoformat() if c.cycle_until else None,
        "safety_conditions": c.safety_reasons,
    }


SENSORS: tuple[PoolSensorDescription, ...] = (
    PoolSensorDescription(
        key="daily_filtration_target",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda c: c.target_minutes,
        attrs_fn=_target_attrs,
    ),
    PoolSensorDescription(
        key="target_filtration_component",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.filtration_component,
    ),
    PoolSensorDescription(
        key="target_chlorine_component",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda c: c.is_salt,
        value_fn=lambda c: c.chlorine_component,
    ),
    PoolSensorDescription(
        key="filtration_elapsed_today",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda c: c.elapsed_minutes,
    ),
    PoolSensorDescription(
        key="filtration_remaining_today",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda c: c.remaining_minutes,
    ),
    PoolSensorDescription(
        key="cycle_duration",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.cycle_duration,
    ),
    PoolSensorDescription(
        key="pool_volume",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.VOLUME,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.volume or None,
    ),
    PoolSensorDescription(
        key="pump_control",
        device_class=SensorDeviceClass.ENUM,
        options=[
            "hands_off", "maintenance_lock", "safety", "freeze_protection",
            "ph_correction", "manual_cycle", "manual_override", "mode", "unavailable",
        ],
        value_fn=lambda c: c.decision_source,
        attrs_fn=_control_attrs,
    ),
    PoolSensorDescription(
        key="chlorine_production_elapsed_today",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        exists_fn=lambda c: c.is_salt and c.has(CONF_CHLORINATOR_SWITCH),
        value_fn=lambda c: c.chlorine_minutes,
    ),
    PoolSensorDescription(
        key="chlorine_production_remaining_today",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        exists_fn=lambda c: c.is_salt and c.has(CONF_CHLORINATOR_SWITCH),
        value_fn=lambda c: c.chlorine_remaining,
    ),
    PoolSensorDescription(
        key="recommended_chlorinator_production",
        native_unit_of_measurement=PERCENTAGE,
        exists_fn=lambda c: c.is_salt and not c.self_regulating,
        value_fn=lambda c: c.recommended_production,
        attrs_fn=lambda c: {"configured_production": c.chlorinator_production},
    ),
    PoolSensorDescription(
        key="chlorination_mode",
        device_class=SensorDeviceClass.ENUM,
        options=[m.value for m in ChlorinationMode],
        exists_fn=lambda c: c.is_salt,
        value_fn=lambda c: c.chlorination_mode,
        attrs_fn=lambda c: {"active_months": c.active_months},
    ),
    PoolSensorDescription(
        key="days_since_last_backwash",
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda c: c.days_since("backwash" if c.uses_backwash else "filter_cleaned"),
    ),
    PoolSensorDescription(
        key="days_since_ph_calibration",
        native_unit_of_measurement=UnitOfTime.DAYS,
        exists_fn=lambda c: c.has(CONF_PH_SENSOR),
        value_fn=lambda c: c.days_since("ph_calibrated"),
    ),
    PoolSensorDescription(
        key="next_manual_task",
        device_class=SensorDeviceClass.ENUM,
        options=["none", "backwash", "filter_cleaning", "ph_calibration"],
        value_fn=lambda c: c.next_manual_task,
        attrs_fn=lambda c: {"tasks": c.task_status(), "recent_actions": c.actions[-10:]},
    ),
    PoolSensorDescription(
        key="overall_status",
        device_class=SensorDeviceClass.ENUM,
        options=[s.value for s in OverallStatus],
        value_fn=lambda c: c.overall_status,
        attrs_fn=lambda c: {"alerts": c.alerts},
    ),
    PoolSensorDescription(
        key="ph_trend",
        device_class=SensorDeviceClass.ENUM,
        options=[t.value for t in PhTrend],
        exists_fn=lambda c: c.has(CONF_PH_SENSOR),
        value_fn=lambda c: c.ph_trend,
    ),
    PoolSensorDescription(
        key="salinity",
        native_unit_of_measurement="g/L",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        exists_fn=lambda c: c.is_salt,
        value_fn=lambda c: c.salinity[0],
        attrs_fn=lambda c: {
            "source": c.salinity[1],
            "recorded_at": (c.manual_readings.get("salt") or {}).get("at"),
        },
    ),
    PoolSensorDescription(
        key="free_chlorine",
        native_unit_of_measurement="ppm",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda c: c.free_chlorine[0],
        attrs_fn=lambda c: {
            "source": c.free_chlorine[1],
            "recorded_at": (c.manual_readings.get("free_chlorine") or {}).get("at"),
        },
    ),
    PoolSensorDescription(
        key="pump_energy_today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        exists_fn=lambda c: c.has(CONF_PUMP_ENERGY_SENSOR),
        value_fn=lambda c: c.pump_energy_today,
    ),
    PoolSensorDescription(
        key="pump_cost_today",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        exists_fn=lambda c: c.has(CONF_PUMP_ENERGY_SENSOR)
        and (c.has(CONF_ENERGY_PRICE) or c.has(CONF_ENERGY_PRICE_ENTITY)),
        value_fn=lambda c: c.pump_cost_today,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolCoordinator = entry.runtime_data
    classes = {"daily_filtration_target": TargetSensor, "pump_control": ControlSensor}
    async_add_entities(
        classes.get(d.key, PoolSensor)(coordinator, d) for d in SENSORS if d.exists_fn(coordinator)
    )


class PoolSensor(PoolEntity, SensorEntity):
    entity_description: PoolSensorDescription

    def __init__(self, coordinator: PoolCoordinator, description: PoolSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if description.key == "pump_cost_today":
            self._attr_native_unit_of_measurement = coordinator.hass.config.currency

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator)


class TargetSensor(PoolSensor):
    """The target, whose bulky attributes are for the card, not the recorder."""

    _unrecorded_attributes = frozenset(
        {"history", "pool_entities", "entities", "dimensions", "inputs", "lights"}
    )


class ControlSensor(PoolSensor):
    """Who decides the pump.

    The surplus and the reason change with every reading of the grid meter;
    recording them would write a row every few seconds all day.
    """

    _unrecorded_attributes = frozenset({"surplus_w", "reason", "chlorinator"})
