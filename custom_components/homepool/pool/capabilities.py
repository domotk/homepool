"""Capabilities resolver.

Pure Python module, no Home Assistant dependencies.
Determines which capabilities are active based on the entities
the user has connected during setup.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConnectedEntities:
    """Represents which entities the user has connected."""

    pump_switch: bool = False
    pump_power_sensor: bool = False
    pump_energy_sensor: bool = False
    ph_sensor: bool = False
    water_temperature_sensor: bool = False
    salinity_sensor: bool = False
    orp_sensor: bool = False
    free_chlorine_sensor: bool = False
    filter_pressure_sensor: bool = False
    equipment_room_temperature_sensor: bool = False
    equipment_room_humidity_sensor: bool = False
    flood_sensor: bool = False
    chlorinator_switch: bool = False
    chlorinator_production_entity: bool = False
    solar_excess_sensor: bool = False
    solar_forecast_entity: bool = False
    weather_entity: bool = False
    uv_sensor: bool = False


@dataclass
class Capability:
    """A single capability that can be unlocked."""

    id: str
    name: str
    description: str
    requires: list[str]
    active: bool = False


def resolve_capabilities(
    connected: ConnectedEntities,
    chlorination_type: str = "tablets",
) -> list[Capability]:
    """Determine which capabilities are active.

    Args:
        connected: Which entities are connected.
        chlorination_type: Type of chlorination system.

    Returns:
        List of all capabilities with their active status.
    """
    is_salt = chlorination_type == "salt"

    capabilities = [
        # Level 0 — always available with pump_switch
        Capability(
            id="filtration_planning",
            name="Filtration planning",
            description="Calculate daily filtration target and manage pump schedules",
            requires=["pump_switch"],
        ),
        Capability(
            id="manual_task_tracking",
            name="Manual task tracking",
            description="Track backwash, salt additions, pH calibration, and other manual tasks",
            requires=["pump_switch"],
        ),

        # Level 1 — with additional sensors
        Capability(
            id="ph_monitoring",
            name="pH monitoring & alerts",
            description="pH out-of-range alerts, correction suggestions, trend detection, "
                        "and probe calibration reminders",
            requires=["ph_sensor"],
        ),
        Capability(
            id="pump_anomaly_detection",
            name="Pump anomaly detection",
            description="Detect abnormal power consumption indicating filter saturation "
                        "or mechanical issues",
            requires=["pump_power_sensor"],
        ),
        Capability(
            id="energy_reporting",
            name="Energy cost reporting",
            description="Track daily/monthly pump energy consumption and estimated cost",
            requires=["pump_power_sensor"],
        ),
        Capability(
            id="smart_filtration",
            name="Temperature-adjusted filtration",
            description="Adjust daily filtration target based on real water temperature",
            requires=["water_temperature_sensor"],
        ),
        Capability(
            id="solar_modes",
            name="Solar operation modes",
            description="Enable solar and smart_solar operation modes for the pump",
            requires=["solar_excess_sensor"],
        ),
        Capability(
            id="solar_planning",
            name="Solar production planning",
            description="Plan filtration schedule based on solar production forecast",
            requires=["solar_excess_sensor", "solar_forecast_entity"],
        ),
        Capability(
            id="backwash_detection",
            name="Automatic backwash detection",
            description="Detect when filter pressure indicates backwash is needed",
            requires=["filter_pressure_sensor"],
        ),
        Capability(
            id="flood_safety",
            name="Flood safety shutoff",
            description="Automatically stop pump when flood is detected in equipment room",
            requires=["flood_sensor"],
        ),
        Capability(
            id="overheat_safety",
            name="Overheat safety shutoff",
            description="Stop pump when equipment room temperature is dangerously high",
            requires=["equipment_room_temperature_sensor"],
        ),
        Capability(
            id="weather_adjustment",
            name="Weather-adjusted filtration",
            description="Adjust filtration target based on UV index and rain forecast",
            requires=["weather_entity"],
        ),
    ]

    # Salt-specific capabilities
    if is_salt:
        capabilities.extend([
            Capability(
                id="chlorinator_management",
                name="Independent chlorinator control",
                description="Manage chlorinator independently from pump to prevent "
                            "over-chlorination and extend cell life",
                requires=["chlorinator_switch"],
            ),
            Capability(
                id="chlorinator_production_control",
                name="Automatic production adjustment",
                description="Automatically adjust chlorinator production percentage",
                requires=["chlorinator_production_entity"],
            ),
            Capability(
                id="salinity_monitoring",
                name="Salinity monitoring",
                description="Monitor salt levels and alert when salt needs to be added",
                requires=["salinity_sensor"],
            ),
        ])

    # Resolve active status
    for cap in capabilities:
        cap.active = all(
            getattr(connected, req, False) for req in cap.requires
        )

    return capabilities


def get_unlocked_summary(capabilities: list[Capability]) -> dict:
    """Generate a summary of unlocked vs locked capabilities.

    Returns dict with 'unlocked' and 'available' lists for UI display.
    """
    return {
        "unlocked": [
            {"id": c.id, "name": c.name, "description": c.description}
            for c in capabilities if c.active
        ],
        "available": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "requires": c.requires,
            }
            for c in capabilities if not c.active
        ],
    }
