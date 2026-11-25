"""Operation modes for HomePool pump control."""

from .base import OperationMode, PoolContext, PumpDecision, PumpAction
from .off_mode import OffMode
from .timer_mode import TimerMode
from .smart_mode import SmartMode
from .solar_mode import SolarMode
from .smart_solar_mode import SmartSolarMode

MODE_REGISTRY: dict[str, type[OperationMode]] = {
    "off": OffMode,
    "timer": TimerMode,
    "smart": SmartMode,
    "solar": SolarMode,
    "smart_solar": SmartSolarMode,
}

__all__ = [
    "OperationMode", "PoolContext", "PumpDecision", "PumpAction",
    "OffMode", "TimerMode", "SmartMode", "SolarMode", "SmartSolarMode",
    "MODE_REGISTRY",
]
