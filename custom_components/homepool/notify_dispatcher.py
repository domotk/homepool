"""Optional built-in notifications.

HomePool always fires events and keeps alert binary sensors, so automations
work whether or not this is on. This is for people who just want a message on
their phone without writing an automation: it forwards alerts to one
``notify.*`` service, filtered by severity and quiet hours.
"""

from __future__ import annotations

from datetime import datetime, time
import logging

from homeassistant.core import HomeAssistant

from .const import SEVERITY_ORDER, Severity

_LOGGER = logging.getLogger(__name__)


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def in_quiet_hours(now: time, start: time | None, end: time | None) -> bool:
    """Is ``now`` inside the quiet window? The window may cross midnight."""
    if start is None or end is None or start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


class NotifyDispatcher:
    """Sends HomePool alerts to a Home Assistant notify service."""

    def __init__(
        self,
        hass: HomeAssistant,
        service: str | None,
        severity_min: str = Severity.WARNING,
        quiet_start: str | None = None,
        quiet_end: str | None = None,
        critical_ignore_quiet: bool = True,
    ) -> None:
        self.hass = hass
        self.service = service
        self.severity_min = severity_min
        self.quiet_start = _parse_time(quiet_start)
        self.quiet_end = _parse_time(quiet_end)
        self.critical_ignore_quiet = critical_ignore_quiet

    def should_send(self, severity: str, now: datetime, reminder: bool = False) -> bool:
        """Apply the severity floor and the quiet hours.

        A reminder (a task falling due, the chlorinator season changing) asks
        the owner to do something, so it passes the severity floor whatever its
        severity; it still waits for the quiet hours to end.
        """
        if not self.service:
            return False
        level = SEVERITY_ORDER.get(Severity(severity), 0)
        floor = SEVERITY_ORDER.get(Severity(self.severity_min), 1)
        if level < floor and not reminder:
            return False
        if self.quiet(now):
            return severity == Severity.CRITICAL and self.critical_ignore_quiet
        return True

    def quiet(self, now: datetime) -> bool:
        """Is ``now`` inside the quiet hours?"""
        return in_quiet_hours(now.time(), self.quiet_start, self.quiet_end)

    async def async_send(
        self,
        title: str,
        message: str,
        severity: str,
        now: datetime,
        reminder: bool = False,
    ) -> None:
        """Send a notification if it passes the filters. Never raises."""
        if not self.should_send(severity, now, reminder):
            return
        domain, _, name = (self.service or "").partition(".")
        if not name:
            domain, name = "notify", domain
        try:
            await self.hass.services.async_call(
                domain, name, {"title": title, "message": message}, blocking=False
            )
        except Exception:  # noqa: BLE001 - a broken notifier must not break the pool
            _LOGGER.warning("Could not send a notification through %s", self.service)
