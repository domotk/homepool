"""Operation modes for HomePool pump control."""

from .base import OperationMode, PoolContext, PumpAction, PumpDecision
from .off_mode import OffMode
from .smart_mode import SmartMode
from .smart_solar_mode import SmartSolarMode
from .solar_mode import SolarMode
from .timer_mode import TimerMode, in_slot

MODE_REGISTRY: dict[str, type[OperationMode]] = {
    "off": OffMode,
    "timer": TimerMode,
    "smart": SmartMode,
    "solar": SolarMode,
    "smart_solar": SmartSolarMode,
}

__all__ = [
    "MODE_REGISTRY",
    "OffMode",
    "OperationMode",
    "PoolContext",
    "PumpAction",
    "PumpDecision",
    "SmartMode",
    "SmartSolarMode",
    "SolarMode",
    "TimerMode",
    "in_slot",
]
