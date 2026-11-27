"""What the second real install showed: the 0.1.4 fixes."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from freezegun.api import FrozenDateTimeFactory

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.util import dt as dt_util

from custom_components.homepool.coordinator import _todays_forecast

from .helpers import SwitchRouter, setup_pool
from .test_control import local, madrid, state, tick  # noqa: F401

# How Open-Meteo dates its days: midnight UTC.
OPEN_METEO = [
    {"datetime": "2026-11-25T00:00:00+00:00", "temperature": 18.0},
    {"datetime": "2026-11-26T00:00:00+00:00", "temperature": 18.5},
]


def test_the_forecast_for_today_is_picked_by_its_date() -> None:
    assert _todays_forecast(OPEN_METEO, date(2026, 11, 26))["temperature"] == 18.5
    assert _todays_forecast(OPEN_METEO, date(2026, 11, 25))["temperature"] == 18.0
    # A provider writing local midnight, or a datetime object.
    local_days = [{"datetime": datetime(2026, 11, 26, tzinfo=timezone(timedelta(hours=1)))}]
    assert _todays_forecast(local_days, date(2026, 11, 26)) is local_days[0]
    # Nothing names today: the first entry, as before.
    assert _todays_forecast(OPEN_METEO, date(2026, 12, 1))["temperature"] == 18.0


async def test_just_after_midnight_the_target_uses_todays_forecast(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 11, 26, 0, 30))
    hass.states.async_set("weather.home", "clear-night")

    async def forecasts(call):
        return {"weather.home": {"forecast": OPEN_METEO}}

    hass.services.async_register(
        "weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY
    )
    SwitchRouter(hass)
    await setup_pool(hass, weather_entity="weather.home")
    attrs = hass.states.get("sensor.pool_daily_filtration_target").attributes
    assert attrs["inputs"]["air_temperature"] == 18.5


async def test_an_override_saved_without_who_reads_as_a_person(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 11, 26, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass)
    coordinator = entry.runtime_data
    attrs = hass.states.get("sensor.pool_pump_control").attributes
    assert attrs["manual_override_by"] is None
    # As 0.1.1 stored it.
    coordinator.override = {
        "state": False,
        "until": (dt_util.utcnow() + timedelta(hours=1)).isoformat(),
    }
    await tick(hass, freezer, 1)
    attrs = hass.states.get("sensor.pool_pump_control").attributes
    assert attrs["manual_override_by"] == "user"
    assert attrs["reason_key"] == "manual_override_off"


async def test_a_held_target_shows_what_was_calculated(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.water", "28")
    await setup_pool(hass, water_temperature_sensor="sensor.water")
    attrs = hass.states.get("sensor.pool_daily_filtration_target").attributes
    first = attrs["calculated_minutes"]
    assert first == int(state(hass, "sensor.pool_daily_filtration_target"))
    hass.states.async_set("sensor.water", "24")
    await tick(hass, freezer, 61)
    attrs = hass.states.get("sensor.pool_daily_filtration_target").attributes
    assert attrs["held_at_previous"] is True
    assert int(state(hass, "sensor.pool_daily_filtration_target")) == first
    assert attrs["calculated_minutes"] < first


async def test_a_task_never_marked_done_still_falls_due(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 11, 26, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, backwash_interval_days=14)
    coordinator = entry.runtime_data
    # A November install starts in active wintering, where the backwash counts
    # pump hours; this is about the days it counts while swimming.
    coordinator.settings["season_state"] = "swimming"
    task = coordinator.task_status()[0]
    assert task["last_done"] is None
    assert task["due"] == "2026-12-10"
    assert not task["overdue"]
    freezer.move_to(local(2026, 12, 10, 10, 0))
    await tick(hass, freezer, 1)
    assert coordinator.task_status()[0]["overdue"]
    assert "backwash_due" in coordinator.alerts
    # Marking it done counts from then, as before.
    await coordinator.async_record_action("backwash")
    assert coordinator.task_status()[0]["due"] == "2026-12-24"


async def test_the_surplus_attribute_moves_in_steps_of_100_w(
    hass: HomeAssistant, madrid, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(local(2026, 7, 15, 12, 0))
    SwitchRouter(hass)
    hass.states.async_set("sensor.grid", "1234", {"unit_of_measurement": "W"})
    await setup_pool(hass, solar_excess_sensor="sensor.grid")
    await tick(hass, freezer, 1)
    surplus = hass.states.get("sensor.pool_pump_control").attributes["surplus_w"]
    assert surplus is not None and surplus % 100 == 0
