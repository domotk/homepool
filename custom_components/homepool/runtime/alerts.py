"""Raising and clearing alerts, and the reminders sent with them.

A mixin of ``PoolCoordinator``; see coordinator.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import CoreState
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_CHLORINATOR_MIN_WATER_TEMP,
    CONF_FREE_CHLORINE_SENSOR,
    CONF_PH_RANGE_MAX,
    CONF_PH_RANGE_MIN,
    CONF_SALINITY_SENSOR,
    CONF_SALT_RANGE_MIN,
    DEFAULT_CHLORINATOR_MIN_WATER_TEMP,
    DEFAULT_PH_RANGE_MAX,
    DEFAULT_PH_RANGE_MIN,
    DEFAULT_SALT_RANGE_MIN,
    EVENT_ALERT,
    EVENT_MANUAL_ACTION_DUE,
    EVENT_SAFETY_SHUTOFF,
    Severity,
)
from ..pool.readings import KINDS, RANGE_ALERT_KINDS
from ..pool.tasks import TASKS
from ..texts import text


def _range_text(low: float | None, high: float | None) -> str:
    if low is None:
        return f"≤ {high:g}"
    if high is None:
        return f"≥ {low:g}"
    return f"{low:g}–{high:g}"


REMINDERS_KEPT = 20
# Rungs above freeze protection: with one of them deciding, the pump is not
# kept running however cold the water is.
FREEZE_BLOCKERS = ("unavailable", "hands_off", "maintenance_lock", "safety")


class AlertsMixin:
    """Raising and clearing alerts, and the reminders sent with them."""

    async def _async_raise(
        self,
        alert: str,
        severity: str,
        values: dict[str, Any],
        once: bool = False,
        reminder: bool = False,
        text_key: str | None = None,
        notify: bool = True,
    ) -> None:
        """Raise an alert on its rising edge: event, and notification if enabled.

        ``reminder`` marks an alert that asks the owner to do something: it is
        notified whatever the severity floor, after the quiet hours if need be.
        ``text_key`` picks another wording for the same alert; ``notify``
        False raises it without a notification.
        """
        if alert in self.alerts and not once:
            return
        message = text(
            self.hass.config.language, text_key or alert, pool=self.pool_name, **values
        )
        if not once:
            self.alerts[alert] = {
                "severity": severity,
                "message": message,
                "since": dt_util.utcnow().isoformat(),
            }
            self._alert_text_keys[alert] = text_key or alert
        payload = {
            "entry_id": self.entry.entry_id,
            "pool": self.pool_name,
            "type": alert,
            "severity": severity,
            "message": message,
            "context": values,
        }
        self.hass.bus.async_fire(EVENT_ALERT, payload)
        if alert == "safety_shutoff":
            self.hass.bus.async_fire(
                EVENT_SAFETY_SHUTOFF,
                {
                    "entry_id": self.entry.entry_id,
                    "pool": self.pool_name,
                    "reason": values.get("reason"),
                    "conditions": self.safety_reasons,
                },
            )
        title = text(self.hass.config.language, "title") + f" · {self.pool_name}"
        if not notify:
            return
        if reminder:
            await self._async_remind(title, message)
        elif self.notifier:
            await self.notifier.async_send(title, message, severity, dt_util.now())

    async def _async_remind(self, title: str, message: str) -> None:
        """Notify a reminder now, or keep it until the quiet hours end, or
        until Home Assistant runs: while it starts, the notify service may not
        be registered yet."""
        if not self.notifier or not self.notifier.service:
            return
        now = dt_util.now()
        if self.notifier.quiet(now) or self.hass.state is not CoreState.running:
            entry = {"title": title, "message": message}
            if entry not in self.pending_reminders:
                self.pending_reminders.append(entry)
            del self.pending_reminders[:-REMINDERS_KEPT]
            return
        await self.notifier.async_send(title, message, Severity.INFO, now, reminder=True)

    async def _async_flush_reminders(self, now: datetime) -> None:
        if not self.pending_reminders:
            return
        if not self.notifier or not self.notifier.service:
            self.pending_reminders = []
            return
        if self.hass.state is not CoreState.running:
            # Still starting: the notify service may not be registered yet.
            return
        local = dt_util.as_local(now)
        if self.notifier.quiet(local):
            return
        pending, self.pending_reminders = self.pending_reminders, []
        for reminder in pending:
            await self.notifier.async_send(
                reminder["title"], reminder["message"], Severity.INFO, local, reminder=True
            )

    async def _async_clear(self, alert: str) -> None:
        self.alerts.pop(alert, None)
        self._alert_text_keys.pop(alert, None)

    async def _async_set(
        self, alert: str, active: bool, severity: str, values: dict[str, Any] | None = None
    ) -> None:
        if active:
            await self._async_raise(alert, severity, values or {})
        else:
            await self._async_clear(alert)

    async def _async_freeze_alert(self) -> None:
        """Freeze risk, worded by whether HomePool can actually run the pump.

        A rung above freeze protection (lock, safety, hands-off, no pump)
        keeps the pump as it is; the alert then says so instead of claiming
        the pump is running, and is raised again if that changes mid-frost.
        """
        if not self.freeze_active:
            await self._async_clear("freeze_protection")
            return
        values: dict[str, Any] = {}
        if self.winter_passive:
            # The pump is never run in passive wintering: the plugs and the
            # gizmos are what protect the pipes.
            text_key = "freeze_protection_passive"
        elif self.decision_source in FREEZE_BLOCKERS:
            text_key = "freeze_protection_blocked"
            values = {"reason": self.decision_reason or ""}
        else:
            text_key = "freeze_protection"
        current = self.alerts.get("freeze_protection")
        if current and self._alert_text_keys.get("freeze_protection") != text_key:
            if text_key == "freeze_protection":
                # Running again: correct the text without another notification.
                current["message"] = text(
                    self.hass.config.language, text_key, pool=self.pool_name
                )
                self._alert_text_keys["freeze_protection"] = text_key
                return
            # Newly kept off in a frost: worth telling whoever is notified.
            await self._async_clear("freeze_protection")
        await self._async_raise(
            "freeze_protection", Severity.WARNING, values, text_key=text_key
        )

    async def _async_closing_needs_pump(self) -> None:
        """Raised while it holds; notified only the first time, not after
        every restart (alerts are not kept across one)."""
        if not self._closing_needs_pump():
            await self._async_clear("closing_needs_pump")
            if self.closing_needs_pump_notified:
                self.closing_needs_pump_notified = False
                self._save()
            return
        await self._async_raise(
            "closing_needs_pump",
            Severity.WARNING,
            {},
            notify=not self.closing_needs_pump_notified,
        )
        if not self.closing_needs_pump_notified:
            self.closing_needs_pump_notified = True
            self._save()

    async def _async_alerts(self, now: datetime) -> None:
        await self._async_set(
            "safety_shutoff",
            self.safety_active,
            Severity.CRITICAL,
            {"reason": ", ".join(self.safety_reasons)},
        )
        await self._async_freeze_alert()
        await self._async_treatment_alerts()
        await self._async_closing_needs_pump()
        ph = self.ph
        await self._async_set(
            "ph_out_of_range",
            self.ph_out_of_range,
            Severity.WARNING,
            {
                "value": ph or 0,
                "low": float(self.opt(CONF_PH_RANGE_MIN, DEFAULT_PH_RANGE_MIN)),
                "high": float(self.opt(CONF_PH_RANGE_MAX, DEFAULT_PH_RANGE_MAX)),
            },
        )
        if self.is_salt:
            in_season_on = self.cell_in_season and self.chlorinator_enabled
            salt, _ = self.salinity
            low = float(self.opt(CONF_SALT_RANGE_MIN, DEFAULT_SALT_RANGE_MIN))
            # Salt only matters while the cell is working: out of season an old
            # manual reading must not keep the alert on all winter.
            await self._async_set(
                "salt_low",
                in_season_on and salt is not None and salt < low,
                Severity.WARNING,
                {"value": salt or 0, "low": low},
            )
            water = self.water_temperature
            cold = (
                in_season_on
                and water is not None
                and water
                < float(self.opt(CONF_CHLORINATOR_MIN_WATER_TEMP, DEFAULT_CHLORINATOR_MIN_WATER_TEMP))
            )
            await self._async_set("chlorinator_cold", cold, Severity.WARNING, {"value": water or 0})
            not_producing = (
                in_season_on
                and self.target.get("effective_production_g_h") == 0
                and not cold
            )
            await self._async_set("chlorinator_not_producing", bool(not_producing), Severity.WARNING)

        await self._async_reading_alerts()

        today = dt_util.now().date().isoformat()
        self._seed_task_first_seen()
        tasks = self.task_status()
        for task in tasks:
            name = task["task"]
            alert = f"{name}_due"
            if task["overdue"]:
                # Alerts are not kept across restarts: the reminder goes out
                # once a day, not again after every reload.
                first_today = self.due_notified.get(name) != today
                await self._async_raise(
                    alert, Severity.INFO, {}, reminder=True, notify=first_today
                )
                if first_today:
                    self.due_notified[name] = today
                    self.hass.bus.async_fire(
                        EVENT_MANUAL_ACTION_DUE,
                        {
                            "entry_id": self.entry.entry_id,
                            "pool": self.pool_name,
                            "action_type": name,
                            "last_done": task["last_done"],
                        },
                    )
            else:
                await self._async_clear(alert)
        # A task that is gone (switched off in the options, or its equipment
        # removed) takes its reminder with it.
        listed = {t["task"] for t in tasks}
        for defn in TASKS:
            if defn.key not in listed:
                await self._async_clear(f"{defn.key}_due")
                self.due_notified.pop(defn.key, None)
                # Back one day, it counts from then, not from its first time.
                self.task_first_seen.pop(defn.key, None)

    async def _async_reading_alerts(self) -> None:
        """Out of range, from readings that are not stale; and the ones that are."""
        for kind in RANGE_ALERT_KINDS:
            alert = f"{kind}_out_of_range"
            if kind == "free_chlorine":
                value, source = self.free_chlorine
                out = value is not None and self._outside(kind, value)
                if self.winter_passive and source == "free_chlorine_sensor":
                    # Drained pipes: the probe reads air or a dry cup.
                    out = False
                _, high = self.reading_range(kind)
                if (
                    out
                    and self.swimming_not_advised in ("treatment", "after_shock")
                    and high is not None
                    and value > high
                ):
                    # A treatment raises it on purpose; swimming_not_advised
                    # already says the water is not for swimming.
                    out = False
            else:
                status = self.manual_status(kind)
                value, out = status.value, status.out_of_range
            low, high = self.reading_range(kind)
            await self._async_set(
                alert,
                out,
                Severity.WARNING,
                {"value": value or 0, "range": _range_text(low, high)},
            )
        # Nobody measures an emptied pool: no old-reading notice in passive wintering.
        stale = [] if self.winter_passive else [
            kind
            for kind in KINDS
            if kind in self.manual_readings
            and self.manual_status(kind).stale
            and self._manual_is_used(kind)
        ]
        if not stale:
            await self._async_clear("reading_stale")
            self._stale_kinds = []
            return
        values = {"kinds": ", ".join(stale)}
        current = self.alerts.get("reading_stale")
        if current and set(stale) <= set(self._stale_kinds):
            # Fewer than before, one measured again: not news, the text follows.
            current["message"] = text(
                self.hass.config.language, "reading_stale", pool=self.pool_name, **values
            )
        else:
            # Another reading went stale: say so again, with the new list.
            await self._async_clear("reading_stale")
            await self._async_raise("reading_stale", Severity.INFO, values)
        self._stale_kinds = stale

    def _outside(self, kind: str, value: float) -> bool:
        low, high = self.reading_range(kind)
        return (low is not None and value < low) or (high is not None and value > high)

    def _manual_is_used(self, kind: str) -> bool:
        """Is the reading by hand the one in use, rather than a probe or something that is not there?"""
        if kind == "ph":
            return self.ph_probe is None
        if kind == "free_chlorine":
            return self._number(CONF_FREE_CHLORINE_SENSOR) is None
        if kind == "salt":
            # Like salt_low: salt only matters while the cell is working.
            return (
                self.is_salt
                and self._number(CONF_SALINITY_SENSOR) is None
                and self.cell_in_season
                and self.chlorinator_enabled
            )
        return True
