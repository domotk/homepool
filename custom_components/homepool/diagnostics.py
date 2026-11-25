"""Everything needed to work out why a pool behaves as it does, in one download.

The most useful parts are not attributes at all: the reason behind the last
pump decision, the pending commands, the store and the daily history. Without
this, diagnosing a pool meant asking someone to read them off a screen.

Entity ids are not secret — they are on the device page already — but the
location is personal, so it is redacted.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_LATITUDE, CONF_LONGITUDE

TO_REDACT = {CONF_LATITUDE, CONF_LONGITUDE}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator = getattr(entry, "runtime_data", None)
    out: dict[str, Any] = {
        "entry": {
            "version": entry.version,
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        }
    }
    if coordinator is None:
        out["controller"] = "not loaded"
        return out
    out["controller"] = {
        "decision": {
            "source": coordinator.decision_source,
            "reason": coordinator.decision_reason,
            "reason_key": coordinator.decision_key,
            "chlorinator": coordinator.chlorinator_reason,
        },
        "pump": {
            "available": coordinator.pump_available,
            "on": coordinator.pump_is_on,
            "changed_at": coordinator.pump_changed_at.isoformat()
            if coordinator.pump_changed_at
            else None,
            "pending_commands": {
                key: {
                    **value,
                    "sent": value["sent"].isoformat() if value.get("sent") else None,
                    "first_sent": value["first_sent"].isoformat()
                    if value.get("first_sent")
                    else None,
                }
                for key, value in coordinator._pending.items()  # noqa: SLF001
            },
        },
        "safety": {
            "active": coordinator.safety_active,
            "conditions": coordinator.safety_reasons,
            "freeze": coordinator.freeze_active,
            "pump_anomaly": coordinator.pump_anomaly,
        },
        "solar": {
            "surplus_w": coordinator.surplus_w,
            "threshold_w": coordinator.solar_threshold,
        },
        "target": coordinator.target,
        "alerts": coordinator.alerts,
        "store": coordinator._to_store(),  # noqa: SLF001
    }
    return out
