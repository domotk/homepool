"""Optional built-in notification dispatcher.

Only active when enable_builtin_notifications is True.
Sends notifications via the user-configured notify service,
respecting severity filters and quiet hours.
"""
from __future__ import annotations

import logging
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class NotifyDispatcher:
    """Dispatches HomePool alerts to HA notify services."""

    def __init__(
        self,
        hass: HomeAssistant,
        service: str | None,
        severity_min: str = "warning",
        quiet_start: str | None = None,
        quiet_end: str | None = None,
        critical_ignore_quiet: bool = True,
    ) -> None:
        self.hass = hass
        self.service = service
        self.severity_min = severity_min
        self.quiet_start = quiet_start
        self.quiet_end = quiet_end
        self.critical_ignore_quiet = critical_ignore_quiet

    async def async_send(
        self, title: str, message: str, severity: str = "info"
    ) -> None:
        """Send a notification if it passes filters."""
        # TODO: Implement severity filtering, quiet hours, and dispatch
        pass
