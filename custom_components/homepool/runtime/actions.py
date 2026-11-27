"""What entities and services ask for: settings, cycles, the pump, readings.

A mixin of ``PoolCoordinator``; see coordinator.py.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_CHLORINATOR_CONTROLLABLE,
    CONF_CHLORINATOR_PRODUCTION_ENTITY,
    CONF_MANUAL_OVERRIDE_MINUTES,
    CONF_PH_CORRECTION_MINUTES,
    DEFAULT_MANUAL_OVERRIDE_MINUTES,
    DEFAULT_PH_CORRECTION_MINUTES,
    DOMAIN,
    ManualAction,
)
from ..pool.readings import validate
from .common import ACTIONS_KEPT, WATER_TEST_KINDS

_LOGGER = logging.getLogger("custom_components.homepool.coordinator")


class ActionsMixin:
    """What entities and services ask for: settings, cycles, the pump, readings."""

    async def async_set_setting(self, key: str, value: Any) -> None:
        self.settings[key] = value
        if key in ("user_multiplier", "chlorinator_production", "chlorinator_enabled"):
            await self._async_maybe_recalculate(dt_util.utcnow(), force=True)
        if key == "chlorinator_production":
            await self._async_push_production(value)
        if key == "mode":
            # A new mode starts from its own decision, not from a held-over one.
            self.override = None
        self._save()
        await self.async_refresh()

    async def _async_push_production(self, value: float) -> None:
        entity_id = self.conf.get(CONF_CHLORINATOR_PRODUCTION_ENTITY)
        if not entity_id or not self.conf.get(CONF_CHLORINATOR_CONTROLLABLE):
            return
        domain = entity_id.split(".")[0]
        try:
            if domain in ("number", "input_number"):
                await self.hass.services.async_call(
                    domain, "set_value", {"entity_id": entity_id, "value": value}, blocking=False
                )
            elif domain in ("select", "input_select"):
                state = self.hass.states.get(entity_id)
                options = (state.attributes.get("options") if state else None) or []
                numeric = []
                for option in options:
                    try:
                        numeric.append((abs(float(str(option).rstrip("% ")) - value), option))
                    except ValueError:
                        continue
                if numeric:
                    await self.hass.services.async_call(
                        domain,
                        "select_option",
                        {"entity_id": entity_id, "option": min(numeric)[1]},
                        blocking=False,
                    )
        except Exception:  # noqa: BLE001
            _LOGGER.warning("%s: could not set production on %s", self.pool_name, entity_id)

    async def async_start_cycle(self, minutes: float | None = None) -> None:
        if self.winter_passive:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="cycle_in_winter_passive"
            )
        self._refuse_during_treatment()
        duration = minutes or self.cycle_duration or 60
        self.cycle_until = dt_util.utcnow() + timedelta(minutes=float(duration))
        self.override = None
        self._save()
        await self.async_refresh()

    async def async_stop_cycle(self) -> None:
        """Stop a manual cycle, and stop the pump now if nothing else needs it."""
        self._refuse_during_treatment()
        self.cycle_until = None
        until = dt_util.utcnow() + timedelta(
            minutes=float(self.opt(CONF_MANUAL_OVERRIDE_MINUTES, DEFAULT_MANUAL_OVERRIDE_MINUTES))
        )
        self.override = {"state": False, "until": until.isoformat()}
        self._save()
        await self.async_refresh()

    async def async_set_pump(self, turn_on: bool) -> None:
        """The HomePool pump switch: a manual action that respects the ladder."""
        if turn_on:
            await self.async_start_cycle(self.remaining_minutes or self.cycle_duration)
        else:
            await self.async_stop_cycle()

    async def async_record_reading(self, kind: str, value: float) -> None:
        try:
            validate(kind, value)
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_reading",
                translation_placeholders={"kind": str(kind), "value": str(value)},
            ) from err
        now = dt_util.utcnow()
        self.manual_readings[kind] = {"value": value, "at": now.isoformat()}
        if kind == "free_chlorine":
            self._note_free_chlorine(value)
        self.actions = [
            *self.actions,
            {"type": f"{kind}_reading", "at": now.isoformat(), "value": value, "notes": None},
        ][-ACTIONS_KEPT:]
        if kind == "salt":
            await self._async_maybe_recalculate(now, force=True)
        if kind in WATER_TEST_KINDS:
            # Measuring the pH or the chlorine is the water test.
            await self.async_record_action(ManualAction.WATER_TESTED)
            return
        self._save()
        await self.async_refresh()

    async def async_recalculate(self) -> None:
        self._forecast_at = None
        await self._async_maybe_recalculate(dt_util.utcnow(), force=True)
        self._save()
        await self.async_refresh()

    async def async_force_ph_window(self, minutes: float | None = None) -> None:
        duration = minutes or float(
            self.opt(CONF_PH_CORRECTION_MINUTES, DEFAULT_PH_CORRECTION_MINUTES)
        )
        self.ph_window_until = dt_util.utcnow() + timedelta(minutes=float(duration))
        self.ph_correction_forced = True
        self._save()
        await self.async_refresh()

    async def async_reset_daily(self) -> None:
        self._account(dt_util.utcnow())
        self.elapsed_s = 0.0
        self.chlorine_s = 0.0
        self.ph_correction_s = 0.0
        self.energy_baseline = None
        await self._async_maybe_recalculate(dt_util.utcnow(), force=True)
        self._save()
        await self.async_refresh()
