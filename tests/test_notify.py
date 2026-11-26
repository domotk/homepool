"""The optional notifier's filters."""

from __future__ import annotations

from datetime import datetime, time

from custom_components.homepool.notify_dispatcher import NotifyDispatcher, in_quiet_hours


def test_quiet_hours_cross_midnight() -> None:
    assert in_quiet_hours(time(23, 30), time(22, 0), time(8, 0))
    assert in_quiet_hours(time(7, 59), time(22, 0), time(8, 0))
    assert not in_quiet_hours(time(8, 0), time(22, 0), time(8, 0))
    assert not in_quiet_hours(time(12, 0), None, None)


def test_severity_floor_and_critical_override() -> None:
    notifier = NotifyDispatcher(None, "notify.phone", "warning", "22:00", "08:00", True)
    noon = datetime(2026, 7, 15, 12, 0)
    night = datetime(2026, 7, 15, 23, 0)
    assert not notifier.should_send("info", noon)
    assert notifier.should_send("warning", noon)
    assert not notifier.should_send("warning", night)
    assert notifier.should_send("critical", night)
    silent = NotifyDispatcher(None, "notify.phone", "warning", "22:00", "08:00", False)
    assert not silent.should_send("critical", night)


def test_a_reminder_passes_the_floor_but_waits_for_the_quiet_hours() -> None:
    notifier = NotifyDispatcher(None, "notify.phone", "warning", "22:00", "08:00", True)
    noon = datetime(2026, 7, 15, 12, 0)
    night = datetime(2026, 7, 15, 23, 0)
    assert notifier.should_send("info", noon, reminder=True)
    assert not notifier.should_send("info", night, reminder=True)
    assert notifier.quiet(night) and not notifier.quiet(noon)
