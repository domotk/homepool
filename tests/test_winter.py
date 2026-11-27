"""What HomePool does out of season and when the owner cannot be reached.

The 0.1.3 fixes: no pH forcing in ``off``, no low-salt alert or chlorine
minutes with the cell out, a freeze alert that says when the pump cannot run,
reminders that reach the phone, and a season change seen from the first day.
"""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util

from custom_components.homepool.texts import text

from .helpers import PUMP, SwitchRouter, setup_pool
from .test_control import local, madrid, set_mode, state, tick  # noqa: F401


def _coordinator(entry):
    return entry.runtime_data


async def test_off_mode_does_not_run_the_pump_for_the_ph(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 6, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.ph", "7.9")
    await setup_pool(hass, ph_sensor="sensor.ph", has_ph_dosing=True)
    await tick(hass, freezer, 5)
    assert state(hass, PUMP) == "off"
    assert state(hass, "binary_sensor.pool_ph_correction") == "off"
    # The alert still shows the reading.
    assert state(hass, "binary_sensor.pool_ph_out_of_range") == "on"


async def test_a_ph_window_asked_for_still_runs_in_off(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 6, 0))
    SwitchRouter(hass)
    await setup_pool(hass, ph_sensor="sensor.ph", has_ph_dosing=True)
    await hass.services.async_call(
        "homepool", "force_ph_correction_window",
        {"entity_id": "sensor.pool_status", "duration": 30}, blocking=True,
    )
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "on"
    assert state(hass, "sensor.pool_pump_control") == "ph_correction"


async def test_switching_to_off_releases_a_ph_window(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 6, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.ph", "7.9")
    await setup_pool(hass, ph_sensor="sensor.ph", has_ph_dosing=True)
    await set_mode(hass, "smart")
    await tick(hass, freezer, 1)
    assert state(hass, "sensor.pool_pump_control") == "ph_correction"
    await set_mode(hass, "off")
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "off"


async def test_a_probe_reading_that_cannot_be_right_does_not_run_the_pump(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 6, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.ph", "11.2")  # a probe out of the water
    await setup_pool(hass, ph_sensor="sensor.ph", has_ph_dosing=True)
    await set_mode(hass, "smart")
    await tick(hass, freezer, 5)
    assert state(hass, PUMP) == "off"


async def test_a_ph_reading_frozen_for_a_day_is_not_trusted(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 6, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.ph", "7.9")
    entry = await setup_pool(hass, ph_sensor="sensor.ph", has_ph_dosing=True)
    coordinator = _coordinator(entry)
    now = dt_util.utcnow()
    assert coordinator._ph_plausible(now)
    assert coordinator._ph_plausible(now + timedelta(hours=23))
    assert not coordinator._ph_plausible(now + timedelta(hours=25))
    # A new reading is trusted again.
    hass.states.async_set("sensor.ph", "7.85")
    assert coordinator._ph_plausible(now + timedelta(hours=25))


async def test_the_cell_switched_off_adds_no_chlorine_minutes_or_salt_alert(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, water_temperature_sensor="sensor.water")
    hass.states.async_set("sensor.water", "27")
    coordinator = _coordinator(entry)
    await coordinator.async_record_reading("salt", 2.8)
    await tick(hass, freezer, 1)
    assert "salt_low" in coordinator.alerts
    assert (coordinator.target.get("target_chlorine_minutes") or 0) > 0

    await coordinator.async_set_setting("chlorinator_enabled", False)
    await tick(hass, freezer, 1)
    assert "salt_low" not in coordinator.alerts
    assert not coordinator.target.get("target_chlorine_minutes")
    # The calendar still says it is the season; the cell just did not count.
    assert coordinator.target["chlorinator_in_season"] is True
    assert coordinator.target["target_minutes"] == coordinator.target["target_filtration_minutes"]


async def test_the_freeze_alert_says_when_the_lock_keeps_the_pump_off(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 1, 15, 4, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.water", "1")
    entry = await setup_pool(hass, water_temperature_sensor="sensor.water")
    coordinator = _coordinator(entry)
    events = []
    hass.bus.async_listen("homepool_alert", events.append)
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "on"
    assert "kept running" in coordinator.alerts["freeze_protection"]["message"]

    events.clear()
    await coordinator.async_set_setting("maintenance_lock", True)
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "off"
    message = coordinator.alerts["freeze_protection"]["message"]
    assert "cannot keep the pump running" in message
    assert "Maintenance lock" in message
    # Raised again, so whoever is notified hears of the change.
    assert [e.data["type"] for e in events].count("freeze_protection") == 1

    # Lock off: the pump runs again and the text is corrected, quietly.
    await coordinator.async_set_setting("maintenance_lock", False)
    await tick(hass, freezer, 1)
    assert state(hass, PUMP) == "on"
    assert "kept running" in coordinator.alerts["freeze_protection"]["message"]
    assert [e.data["type"] for e in events].count("freeze_protection") == 1


async def _notified(hass: HomeAssistant) -> list[ServiceCall]:
    calls: list[ServiceCall] = []

    async def handler(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("notify", "phone", handler)
    return calls


NOTIFY = {
    "enable_builtin_notifications": True,
    "notification_service": "notify.phone",
    "notification_severity_min": "warning",
    "notification_quiet_hours_start": "22:00",
    "notification_quiet_hours_end": "08:00",
}


async def test_the_season_change_reaches_the_phone_after_the_quiet_hours(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    # Installed on the season's last evening: the change at midnight is seen.
    freezer.move_to(local(2026, 9, 30, 21, 0))
    SwitchRouter(hass)
    calls = await _notified(hass)
    events = []
    hass.bus.async_listen("homepool_chlorinator_season_end", events.append)
    await setup_pool(hass, **NOTIFY)
    await tick(hass, freezer, 4 * 60)  # past midnight, inside the quiet hours
    # The event is still fired, as before.
    assert len(events) == 1
    proposal = text("en", "season_proposal_winter", pool="Pool")
    assert proposal not in [c.data["message"] for c in calls]
    await tick(hass, freezer, 7 * 60)  # 08:00 passed
    messages = [c.data["message"] for c in calls]
    # With proposals on, the season proposal's reminder replaces the old one.
    assert proposal in messages
    assert events[0].data["message"] not in messages


async def test_a_task_falling_due_is_notified_with_the_default_threshold(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    calls = await _notified(hass)
    entry = await setup_pool(hass, **NOTIFY, backwash_interval_days=1)
    coordinator = _coordinator(entry)
    await coordinator.async_record_action("backwash")
    await tick(hass, freezer, 2 * 24 * 60)
    assert "backwash_due" in coordinator.alerts
    assert coordinator.alerts["backwash_due"]["severity"] == "info"
    assert any("backwash" in c.data["message"] for c in calls)


async def test_a_reload_does_not_repeat_a_reminder(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    calls = await _notified(hass)
    entry = await setup_pool(hass, **NOTIFY, backwash_interval_days=1)
    await entry.runtime_data.async_record_action("backwash")
    await tick(hass, freezer, 2 * 24 * 60)
    sent = len([c for c in calls if "backwash" in c.data["message"]])
    assert sent == 1
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await tick(hass, freezer, 5)
    assert "backwash_due" in entry.runtime_data.alerts
    assert len([c for c in calls if "backwash" in c.data["message"]]) == sent


async def test_a_reminder_composed_while_starting_waits_for_home_assistant(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    from homeassistant.core import CoreState

    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    calls = await _notified(hass)
    entry = await setup_pool(hass, **{**NOTIFY, "notification_quiet_hours_start": None,
                                      "notification_quiet_hours_end": None})
    coordinator = entry.runtime_data
    hass.set_state(CoreState.starting)
    await coordinator._async_remind("Pool", "do the thing")
    assert not calls
    assert coordinator.pending_reminders == [{"title": "Pool", "message": "do the thing"}]
    hass.set_state(CoreState.running)
    await tick(hass, freezer, 1)
    assert [c.data["message"] for c in calls] == ["do the thing"]
