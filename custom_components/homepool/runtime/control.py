"""Deciding and switching: safety, pH, the pump, the cell and the commands.

A mixin of ``PoolCoordinator``; see coordinator.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.core import Context, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from ..const import (
    CHLORINATOR_FLOW_DELAY_S,
    COMMAND_MAX_ATTEMPTS,
    COMMAND_RETRY_S,
    CONF_AIR_TEMPERATURE_SENSOR,
    CONF_CHLORINATOR_MIN_WATER_TEMP,
    CONF_CHLORINATOR_SWITCH,
    CONF_EQUIPMENT_ROOM_MAX_TEMP,
    CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR,
    CONF_FILTER_PRESSURE_CRITICAL,
    CONF_FILTER_PRESSURE_NORMAL_MAX,
    CONF_FLOOD_SENSOR,
    CONF_FREEZE_PROTECTION,
    CONF_FREEZE_THRESHOLD,
    CONF_HANDS_OFF_ENTITY,
    CONF_HAS_PH_DOSING,
    CONF_LONGITUDE,
    CONF_PH_CORRECTION_MAX_DAILY,
    CONF_PH_CORRECTION_MINUTES,
    CONF_PH_DOSING_ENTITY,
    CONF_PH_RANGE_MAX,
    CONF_PUMP_NOMINAL_POWER,
    CONF_PUMP_POWER_SENSOR,
    CONF_PUMP_SWITCH,
    CONF_SOLAR_EXCESS_SENSOR,
    CONF_SOLAR_EXCESS_SIGN,
    CONF_SOLAR_IMPORT_TOLERANCE,
    DEFAULT_CHLORINATOR_MIN_WATER_TEMP,
    DEFAULT_EQUIPMENT_ROOM_MAX_TEMP,
    DEFAULT_FILTER_PRESSURE_CRITICAL,
    DEFAULT_FILTER_PRESSURE_NORMAL_MAX,
    DEFAULT_FREEZE_THRESHOLD,
    DEFAULT_PH_CORRECTION_MAX_DAILY,
    DEFAULT_PH_CORRECTION_MINUTES,
    DEFAULT_PH_RANGE_MAX,
    DEFAULT_SOLAR_IMPORT_TOLERANCE_W,
    END_OF_DAY_MARGIN_MIN,
    MIN_OFF_MINUTES,
    MIN_ON_MINUTES,
    ExcessSign,
    Severity,
)
from ..modes import MODE_REGISTRY, PoolContext
from ..pool.safety import evaluate_safety
from ..pool.scheduler import (
    ChlorinatorInputs,
    ControlInputs,
    arbitrate,
    chlorinator_wanted,
    solar_noon_utc,
    surplus_watts,
)
from ..pool.treatment import PUMP as TREATMENT_PUMP, Phase, TreatmentType
from ..texts import reason_text
from .common import _parse_dt

_LOGGER = logging.getLogger("custom_components.homepool.coordinator")


# A power reading has to stay out of range this long to count as an anomaly.
ANOMALY_MINUTES = 5
# A pH probe outside this range, or reading exactly the same for this long,
# is not trusted to run the pump.
PH_PLAUSIBLE_MIN = 5.0
PH_PLAUSIBLE_MAX = 9.0
PH_FROZEN_HOURS = 24


class ControlMixin:
    """Deciding and switching: safety, pH, the pump, the cell and the commands."""

    def _solar_noon_minute(self) -> int:
        longitude = float(self.opt(CONF_LONGITUDE, self.hass.config.longitude) or 0)
        noon = dt_util.as_local(solar_noon_utc(dt_util.now().date(), longitude))
        return noon.hour * 60 + noon.minute

    def _minutes_until_day_end(self, now: datetime) -> int:
        local = dt_util.as_local(now)
        tomorrow = dt_util.start_of_local_day(local.date() + timedelta(days=1))
        return max(0, int((tomorrow - now).total_seconds() // 60))

    def _evaluate_safety(self, now: datetime) -> None:
        power = self._watts(CONF_PUMP_POWER_SENSOR)
        nominal = self.opt(CONF_PUMP_NOMINAL_POWER)
        anomaly = False
        if power is not None and nominal:
            nominal = float(nominal)
            if self._pump_was_on and self.pump_on_since and (
                now - self.pump_on_since >= timedelta(minutes=2)
            ):
                anomaly = power > nominal * 1.5 or power < nominal * 0.3
            elif not self._pump_was_on:
                anomaly = power > max(50.0, nominal * 0.2)
        if anomaly:
            self._anomaly_since = self._anomaly_since or now
        else:
            self._anomaly_since = None
        self.pump_anomaly = self._anomaly_since is not None and (
            now - self._anomaly_since >= timedelta(minutes=ANOMALY_MINUTES)
        )

        pressure = self.filter_pressure
        normal_max = float(self.opt(CONF_FILTER_PRESSURE_NORMAL_MAX, DEFAULT_FILTER_PRESSURE_NORMAL_MAX))
        if pressure is not None and self._pump_was_on and pressure > normal_max:
            self._pressure_high_since = self._pressure_high_since or now
        elif pressure is not None and self._pump_was_on:
            self._pressure_high_since = None
        self.pressure_high = self._pressure_high_since is not None and (
            now - self._pressure_high_since >= timedelta(minutes=10)
        )

        evaluation = evaluate_safety(
            flood_detected=self._is_on(CONF_FLOOD_SENSOR),
            equipment_room_temp_c=self._number(CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR),
            equipment_room_temp_threshold_c=float(
                self.opt(CONF_EQUIPMENT_ROOM_MAX_TEMP, DEFAULT_EQUIPMENT_ROOM_MAX_TEMP)
            ),
            filter_pressure_bar=pressure,
            filter_pressure_critical_bar=float(
                self.opt(CONF_FILTER_PRESSURE_CRITICAL, DEFAULT_FILTER_PRESSURE_CRITICAL)
            ),
        )
        reasons = [c.id for c in evaluation.active_conditions]
        if self.pump_anomaly and self._pump_was_on:
            reasons.append("pump_power_anomaly")
        self.safety_reasons = reasons
        self.safety_active = bool(reasons)

        freeze = False
        if self.conf.get(CONF_FREEZE_PROTECTION, True):
            threshold = float(self.opt(CONF_FREEZE_THRESHOLD, DEFAULT_FREEZE_THRESHOLD))
            water = self.water_temperature
            air = self._number(CONF_AIR_TEMPERATURE_SENSOR)
            if water is not None:
                freeze = water < threshold
            elif air is not None:
                freeze = air < 0
        self.freeze_active = freeze

    def _evaluate_ph(self, now: datetime) -> bool:
        """Should the pump run so the pH doser can work? Keeps the window open.

        A window opens for the configured time when the doser needs flow and
        the pump is not already running for another reason; it is extended
        while the need lasts, up to the daily cap, so the pump is not stopped
        and restarted every half hour.

        In ``off`` mode HomePool does not start the pump for the pH: only a
        window asked for through the service does. In passive wintering not
        even that: the pipes are drained. A probe reading that cannot be right
        (outside 5-9, or unchanged for a day: a probe in its cup or out of the
        water) does not start it either.
        """
        if self.winter_passive:
            self.ph_correction_active = False
            self.ph_correction_forced = False
            self.ph_window_until = None
            return False
        if self.ph_correction_forced:
            if self.ph_window_until and now < self.ph_window_until:
                # A window forced from the service runs its course regardless.
                return True
            self.ph_correction_forced = False
            self.ph_window_until = None
        if self.mode == "off":
            self.ph_correction_active = False
            self.ph_window_until = None
            return False
        needed = False
        if self._is_on(CONF_PH_DOSING_ENTITY):
            needed = True
        elif self.conf.get(CONF_HAS_PH_DOSING) and self._ph_plausible(now):
            high = float(self.opt(CONF_PH_RANGE_MAX, DEFAULT_PH_RANGE_MAX))
            # Hysteresis: start above the range, stop once back at the target.
            ph = self.ph_probe
            needed = ph > high or (self.ph_correction_active and ph > self.ph_target)
        self.ph_correction_active = needed
        cap = float(self.opt(CONF_PH_CORRECTION_MAX_DAILY, DEFAULT_PH_CORRECTION_MAX_DAILY))
        if not needed or self.ph_correction_minutes >= cap:
            self.ph_window_until = None
            return False
        if self._pump_was_on and self.started_by != "ph_correction":
            # Water is already flowing for another reason; nothing to force.
            return False
        if self.ph_window_until is None or now >= self.ph_window_until:
            minutes = float(self.opt(CONF_PH_CORRECTION_MINUTES, DEFAULT_PH_CORRECTION_MINUTES))
            self.ph_window_until = now + timedelta(minutes=minutes)
        return True

    def _ph_plausible(self, now: datetime) -> bool:
        """Is the probe's reading believable enough to run the pump for?"""
        ph = self.ph_probe
        if ph is None:
            self._ph_seen = None
            return False
        if self._ph_seen is None or self._ph_seen[0] != ph:
            # Not kept across restarts: after one, the probe gets a fresh day.
            self._ph_seen = (ph, now)
        if not PH_PLAUSIBLE_MIN <= ph <= PH_PLAUSIBLE_MAX:
            return False
        return now - self._ph_seen[1] < timedelta(hours=PH_FROZEN_HOURS)

    async def _async_control(self, now: datetime) -> None:
        self._evaluate_safety(now)
        ph_force = self._evaluate_ph(now)

        if self.override:
            until = _parse_dt(self.override.get("until"))
            if until is None or now >= until:
                self.override = None
        if self.cycle_until and now >= self.cycle_until:
            self.cycle_until = None

        pump_power = self._watts(CONF_PUMP_POWER_SENSOR)
        if pump_power is None and self._pump_was_on and self.opt(CONF_PUMP_NOMINAL_POWER):
            pump_power = float(self.opt(CONF_PUMP_NOMINAL_POWER))
        self.surplus_w = surplus_watts(
            self._watts(CONF_SOLAR_EXCESS_SENSOR),
            self.conf.get(CONF_SOLAR_EXCESS_SIGN) or ExcessSign.EXPORT_POSITIVE,
            self._pump_was_on,
            pump_power,
        )
        solar_available = self._solar.update(
            now,
            self.surplus_w,
            self.solar_threshold,
            float(self.opt(CONF_SOLAR_IMPORT_TOLERANCE, DEFAULT_SOLAR_IMPORT_TOLERANCE_W)),
        )

        local = dt_util.as_local(now)
        mode_cls = MODE_REGISTRY.get(self.mode) or MODE_REGISTRY["off"]
        mode_decision = mode_cls().evaluate(
            PoolContext(
                target_minutes=self.target_minutes,
                elapsed_minutes=self.elapsed_minutes,
                pump_is_on=self._pump_was_on,
                minute_of_day=local.hour * 60 + local.minute,
                minutes_until_day_end=self._minutes_until_day_end(now),
                solar_noon_minute=self._solar_noon_minute(),
                solar_available=solar_available,
                timer_slots=self.timer_slots,
                end_of_day_margin=END_OF_DAY_MARGIN_MIN,
            )
        )
        minutes_in_state = (
            (now - self.pump_changed_at).total_seconds() / 60 if self.pump_changed_at else None
        )
        await self._async_treatment_clock(now)
        phase = self.treatment_phase
        hands_off = self._is_on(CONF_HANDS_OFF_ENTITY) is True
        decision = arbitrate(
            ControlInputs(
                pump_available=self.pump_available,
                pump_is_on=self._pump_was_on,
                minutes_in_state=minutes_in_state,
                hands_off=hands_off,
                maintenance_lock=self.maintenance_lock,
                winter_passive=self.winter_passive,
                safety_shutoff=self.safety_active,
                safety_reason=", ".join(self.safety_reasons) or None,
                # The alert still tells of the frost; the pump is not run.
                freeze_risk=self.freeze_active and not self.winter_passive,
                treatment=TREATMENT_PUMP[phase] if phase else None,
                treatment_key=f"treatment_{phase}" if phase else "",
                ph_correction=ph_force,
                manual_cycle=self.cycle_until is not None,
                manual_override=self.override.get("state") if self.override else None,
                manual_override_by=(self.override or {}).get("by") or "user",
                manual_override_name=(self.override or {}).get("name"),
                mode_decision=mode_decision,
                started_by=self.started_by,
                min_on_minutes=MIN_ON_MINUTES,
                min_off_minutes=MIN_OFF_MINUTES,
            )
        )
        self.decision_source = decision.source
        self.decision_key = decision.key
        if decision.source == "treatment" and decision.pump and self._pump_was_on:
            # Already running when the treatment wanted it: the treatment
            # adopts it, so it is let go when the treatment ends, like one it
            # started. A mode that wants it on keeps it on.
            self.started_by = "treatment"
        self.decision_reason = reason_text(
            self.hass.config.language, decision.key, decision.args, decision.reason
        )

        # The cell first: it must already be off when the pump stops.
        pump_will_be_on = self._pump_was_on if decision.pump is None else decision.pump
        await self._async_control_chlorinator(now, pump_will_be_on)

        if decision.pump is not None and decision.pump != self._pump_was_on:
            if not decision.pump and self._is_on(CONF_CHLORINATOR_SWITCH) is True:
                # Do not stop the pump while the cell is still on: it has just
                # been told to stop, and its state change brings us back here.
                # A cell that ignores every retry must not keep the pump
                # running for ever, through a flood included: once its retries
                # are spent the pump stops anyway, and an alert says why.
                cell = self._pending.get(CONF_CHLORINATOR_SWITCH)
                cell_gave_up = (
                    cell is not None
                    and cell["attempts"] >= COMMAND_MAX_ATTEMPTS
                    and cell["sent"] is not None
                    and now - cell["sent"] >= timedelta(seconds=COMMAND_RETRY_S)
                )
                if not cell_gave_up:
                    await self._async_retry(now)
                    return
            if decision.pump:
                self.started_by = decision.source
            await self._async_command(CONF_PUMP_SWITCH, decision.pump)
        elif decision.pump is None or decision.pump == self._pump_was_on:
            pending = self._pending.get(CONF_PUMP_SWITCH)
            if pending and (decision.pump is None or pending["state"] != decision.pump):
                self._pending.pop(CONF_PUMP_SWITCH, None)
        await self._async_retry(now)

    async def _async_control_chlorinator(self, now: datetime, pump_will_be_on: bool) -> None:
        if not self.conf.get(CONF_CHLORINATOR_SWITCH):
            self.chlorinator_reason = ""
            return
        on_seconds = (
            (now - self.pump_on_since).total_seconds()
            if self._pump_was_on and self.pump_on_since
            else None
        )
        phase = self.treatment_phase
        shock_filtering = (
            phase == Phase.FILTERING and self.treatment["type"] == TreatmentType.SHOCK
        )
        wanted, reason = chlorinator_wanted(
            ChlorinatorInputs(
                has_switch=True,
                pump_is_on=self._pump_was_on and pump_will_be_on,
                pump_on_seconds=on_seconds,
                enabled=self.chlorinator_enabled,
                in_season=self.cell_in_season,
                # A shock runs the cell all the time the water flows.
                target_reached=self.chlorine_target_reached and not shock_filtering,
                # Vacuuming to waste sends no water through the cell.
                blocked=self.maintenance_lock
                or self.safety_active
                or self.winter_passive
                or phase in (Phase.SETTLING, Phase.VACUUMING),
                water_temperature_c=self.water_temperature,
                min_water_temperature_c=float(
                    self.opt(CONF_CHLORINATOR_MIN_WATER_TEMP, DEFAULT_CHLORINATOR_MIN_WATER_TEMP)
                ),
                flow_delay_s=CHLORINATOR_FLOW_DELAY_S,
            )
        )
        self.chlorinator_reason = reason
        if self._is_on(CONF_CHLORINATOR_SWITCH) is None:
            return
        if wanted != self._chlor_was_on:
            await self._async_command(CONF_CHLORINATOR_SWITCH, wanted)

    async def _async_command(self, key: str, turn_on: bool) -> None:
        entity_id = self.conf.get(key)
        if not entity_id:
            return
        pending = self._pending.get(key)
        if pending and pending["state"] == turn_on:
            return  # already asked; the retry loop takes it from here
        self._pending[key] = {
            "state": turn_on,
            "attempts": 0,
            "sent": None,
            "first_sent": dt_util.utcnow(),
        }
        await self._async_send(key)

    async def _async_send(self, key: str) -> None:
        pending = self._pending[key]
        context = Context()
        self._own_contexts.append(context.id)
        pending["attempts"] += 1
        pending["sent"] = dt_util.utcnow()
        service = "turn_on" if pending["state"] else "turn_off"
        _LOGGER.debug(
            "%s: %s %s (attempt %d)", self.pool_name, service, self.conf[key], pending["attempts"]
        )
        self._unsubs.append(
            async_call_later(self.hass, COMMAND_RETRY_S + 1, self._retry_due)
        )
        try:
            await self.hass.services.async_call(
                "homeassistant",
                service,
                {"entity_id": self.conf[key]},
                blocking=False,
                context=context,
            )
        except Exception as err:  # noqa: BLE001 - retried below, and alerted if it persists
            _LOGGER.warning("%s: %s %s failed: %s", self.pool_name, service, self.conf[key], err)

    @callback
    def _retry_due(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_retry(self, now: datetime) -> None:
        """Send a command again if the switch has not followed it."""
        for key, pending in list(self._pending.items()):
            actual = self._is_on(key)
            if actual is None:
                continue  # unavailable: wait, do not keep firing
            if actual == pending["state"]:
                self._pending.pop(key, None)
                await self._async_clear(
                    "pump_not_responding" if key == CONF_PUMP_SWITCH else "chlorinator_not_responding"
                )
                continue
            if pending["sent"] and now - pending["sent"] < timedelta(seconds=COMMAND_RETRY_S):
                continue
            if pending["attempts"] >= COMMAND_MAX_ATTEMPTS:
                alert = (
                    "pump_not_responding" if key == CONF_PUMP_SWITCH else "chlorinator_not_responding"
                )
                await self._async_raise(
                    alert,
                    Severity.CRITICAL,
                    {
                        "attempts": pending["attempts"],
                        "state": "on" if pending["state"] else "off",
                    },
                )
                continue
            await self._async_send(key)
