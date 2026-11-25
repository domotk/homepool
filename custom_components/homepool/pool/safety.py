"""Safety shutoff logic.

Pure Python module, no Home Assistant dependencies.
Evaluates safety conditions that should force the pump off.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SafetyCondition:
    """A single safety condition to evaluate."""

    id: str
    name: str
    triggered: bool
    value: float | bool | None = None
    threshold: float | None = None
    sensor_available: bool = False


@dataclass
class SafetyEvaluation:
    """Result of evaluating all safety conditions."""

    shutoff_required: bool
    active_conditions: list[SafetyCondition]
    reason: str | None = None


def evaluate_safety(
    # Flood
    flood_detected: bool | None = None,
    # Equipment room temperature
    equipment_room_temp_c: float | None = None,
    equipment_room_temp_threshold_c: float = 50.0,
    # Filter pressure
    filter_pressure_bar: float | None = None,
    filter_pressure_critical_bar: float = 2.0,
    # Pump power anomaly
    pump_power_w: float | None = None,
    pump_nominal_power_w: float | None = None,
    pump_power_anomaly_factor: float = 1.5,
) -> SafetyEvaluation:
    """Evaluate all safety conditions.

    Returns a SafetyEvaluation indicating whether the pump should be
    forced off and which conditions triggered.

    Freezing water is deliberately not here. It calls for the opposite —
    running the pump so the water in the pipes keeps moving — and is handled
    as freeze protection by the scheduler.
    """
    conditions: list[SafetyCondition] = []

    # Flood detection
    if flood_detected is not None:
        conditions.append(SafetyCondition(
            id="flood",
            name="Equipment room flood",
            triggered=flood_detected,
            value=flood_detected,
            sensor_available=True,
        ))

    # Equipment room overheat
    if equipment_room_temp_c is not None:
        conditions.append(SafetyCondition(
            id="overheat",
            name="Equipment room overheat",
            triggered=equipment_room_temp_c > equipment_room_temp_threshold_c,
            value=equipment_room_temp_c,
            threshold=equipment_room_temp_threshold_c,
            sensor_available=True,
        ))

    # Filter pressure critical
    if filter_pressure_bar is not None:
        conditions.append(SafetyCondition(
            id="filter_pressure_critical",
            name="Filter pressure critical",
            triggered=filter_pressure_bar > filter_pressure_critical_bar,
            value=filter_pressure_bar,
            threshold=filter_pressure_critical_bar,
            sensor_available=True,
        ))

    # Pump power anomaly
    if pump_power_w is not None and pump_nominal_power_w is not None:
        threshold = pump_nominal_power_w * pump_power_anomaly_factor
        conditions.append(SafetyCondition(
            id="pump_power_anomaly",
            name="Pump power anomaly",
            triggered=pump_power_w > threshold,
            value=pump_power_w,
            threshold=threshold,
            sensor_available=True,
        ))

    active = [c for c in conditions if c.triggered]
    shutoff = len(active) > 0

    reason = None
    if active:
        reasons = [c.name for c in active]
        reason = "; ".join(reasons)

    return SafetyEvaluation(
        shutoff_required=shutoff,
        active_conditions=active,
        reason=reason,
    )
