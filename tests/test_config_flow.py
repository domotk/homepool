"""The setup wizard and the options menu, walked end to end."""

from __future__ import annotations

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.homepool.const import DOMAIN

from .helpers import CHLORINATOR, PUMP, form_fields, form_input, setup_helpers, setup_pool


async def _walk_to_connections(hass: HomeAssistant, chlorination: str = "salt") -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "identity"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Back garden", "latitude": 39.6, "longitude": -0.5}
    )
    assert result["step_id"] == "shape"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"shape": "rectangular"}
    )
    assert result["step_id"] == "dimensions"
    # Depths the wrong way round are refused.
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"length": 6.5, "width": 2.5, "depth_min": 2.0, "depth_max": 1.0, "layout_variant": "plain"},
    )
    assert bad["errors"] == {"depth_max": "depth_order"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"length": 6.5, "width": 2.5, "depth_min": 1.2, "depth_max": 2.2, "layout_variant": "corner_steps"},
    )
    assert result["step_id"] == "layout_orientation"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"layout_orientation": "top_left"}
    )
    assert result["step_id"] == "volume"
    assert float(result["description_placeholders"]["volume"]) > 25
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "construction"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "construction_type": "built_in",
            "has_cover": "none",
            "is_covered_by_roof": False,
            "heating_type": "none",
            "liner_type": "tile",
            "liner_color": "light_blue",
            "orientation": "south",
        },
    )
    assert result["step_id"] == "pump"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"pump_model": "Astralpool Sena 25465"}
    )
    assert result["step_id"] == "filtration"
    # The catalogue filled in the pump's figures.
    schema_defaults = {
        str(k): k.description.get("suggested_value")
        for k in result["data_schema"].schema
        if getattr(k, "description", None)
    }
    assert schema_defaults["pump_nominal_flow_rate"] == 12.8
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "pump_nominal_flow_rate": 12.8,
            "pump_nominal_power": 890,
            "pump_speed_type": "fixed",
            "filter_type": "sand",
            "skimmers_count": 1,
            "returns_count": 2,
            "has_autofill_skimmer": False,
            "filter_pressure_normal_min": 0.6,
            "filter_pressure_normal_max": 1.2,
        },
    )
    assert result["step_id"] == "water"
    # The pH kit question is with the rest of the pH; the intervals are tasks.
    assert "has_ph_probe_outside" in form_fields(result)
    assert "ph_calibration_interval_days" not in form_fields(result)
    assert "winter_product_interval_days" not in form_fields(result)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        form_input(
            result,
            {
                "chlorination_type": chlorination,
                "ph_target": 7.4,
                "ph_range_min": 7.2,
                "ph_range_max": 7.6,
                "has_ph_dosing": True,
                "free_chlorine_target": 1.5,
                "free_chlorine_range_min": 1.0,
                "free_chlorine_range_max": 3.0,
            },
        ),
    )
    if chlorination == "salt":
        assert result["step_id"] == "chlorinator_model"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"chlorinator_model": "Astralpool SEL-E4 55"}
        )
        assert result["step_id"] == "chlorinator"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "chlorinator_nominal_production": 35,
                "chlorinator_production_default": 70,
                "chlorinator_self_regulating": False,
                "chlorinator_controllable": False,
                "chlorinator_active_months": ["6", "7", "8", "9"],
                "chlorinator_auto_toggle": True,
                "chlorinator_min_water_temp": 15,
                "salt_target": 4.0,
                "salt_range_min": 3.0,
                "salt_range_max": 5.5,
            },
        )
    assert result["step_id"] == "connections"
    return result


async def test_full_wizard_creates_entry(hass: HomeAssistant) -> None:
    await setup_helpers(hass)
    result = await _walk_to_connections(hass)
    same = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "pump": {"pump_switch": PUMP},
            "water": {},
            "equipment_room": {},
            "chlorinator": {"chlorinator_switch": PUMP},
            "solar": {"solar_excess_sign": "export_positive", "solar_import_tolerance": 400},
            "weather": {},
        },
    )
    assert same["errors"] == {"base": "same_switch"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "pump": {"pump_switch": PUMP},
            "water": {},
            "equipment_room": {},
            "chlorinator": {"chlorinator_switch": CHLORINATOR},
            "solar": {"solar_excess_sign": "export_positive", "solar_import_tolerance": 400},
            "weather": {},
        },
    )
    assert result["step_id"] == "control"
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        form_input(
            result,
            {
                "timer_slots": "whenever",
                "manual_override_minutes": 120,
                "freeze_protection": True,
                "freeze_threshold": 2,
                "ph_correction_minutes": 30,
                "ph_correction_max_daily": 120,
                "equipment_room_max_temp": 50,
                "filter_pressure_critical": 2,
                "pool_cleaner_type": "none",
            },
        ),
    )
    assert bad["errors"] == {"schedule": "bad_slots"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        form_input(
            result,
            {
                "timer_slots": "09:00-13:00",
                "manual_override_minutes": 120,
                "freeze_protection": True,
                "freeze_threshold": 2,
                "ph_correction_minutes": 30,
                "ph_correction_max_daily": 120,
                "equipment_room_max_temp": 50,
                "filter_pressure_critical": 2,
                "pool_cleaner_type": "none",
            },
        ),
    )
    assert result["step_id"] == "notifications"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "enable_builtin_notifications": False,
            "notification_severity_min": "warning",
            "critical_ignore_quiet_hours": True,
        },
    )
    assert result["step_id"] == "tasks"
    shown = [str(k) for k in result["data_schema"].schema]
    assert "backwash_days" in shown
    assert "cell_cleaning_days" in shown  # salt
    assert "filter_cleaning_days" not in shown  # sand filter
    assert "skimmer_baskets_enabled" in shown
    assert "water_test_enabled" in shown  # optional since ruling 27
    assert "has_ph_probe_outside" not in shown
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["tasks"] == {}
    assert data["has_ph_probe_outside"] is False
    assert data["name"] == "Back garden"
    assert data["pump_switch"] == PUMP
    assert data["chlorinator_switch"] == CHLORINATOR
    assert data["chlorinator_active_months"] == [6, 7, 8, 9]
    # Asked in the water step, before the chlorinator: summer by default.
    assert data["swimming_months"] == [6, 7, 8, 9]
    assert data["pump_model"] == "Astralpool Sena 25465"
    assert 25 < data["volume"] < 35
    assert data["water_temperature_sensor"] is None
    await hass.async_block_till_done()
    assert hass.states.get("sensor.back_garden_daily_filtration_target") is not None


async def test_tablets_skip_the_chlorinator(hass: HomeAssistant) -> None:
    await setup_helpers(hass)
    result = await _walk_to_connections(hass, chlorination="tablets")
    assert "chlorinator" not in [str(k) for k in result["data_schema"].schema]


async def test_options_menu_edits_one_group(hass: HomeAssistant) -> None:
    entry = await setup_pool(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert "chlorinator_model" in result["menu_options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "identity"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"name": "Renamed", "latitude": 39.6, "longitude": -0.5}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["name"] == "Renamed"
    # Everything else is kept.
    assert entry.options["pump_switch"] == PUMP
    assert entry.options["volume"] == 30.0


@pytest.mark.parametrize("language", ["en", "es"])
def test_every_layout_has_a_label_in_each_language(language: str) -> None:
    import json
    import pathlib

    import yaml

    root = pathlib.Path(__file__).parent.parent / "custom_components" / "homepool"
    layouts = yaml.safe_load((root / "data" / "layouts.yaml").read_text(encoding="utf-8"))
    selectors = json.loads(
        (root / "translations" / f"{language}.json").read_text(encoding="utf-8")
    )["selector"]
    for shape, variants in layouts.items():
        if not isinstance(variants, list):
            continue
        options = selectors[f"layout_variant_{shape}"]["options"]
        assert {v["id"] for v in variants} == set(options), shape


async def _open_water(hass: HomeAssistant, entry) -> dict:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "water"}
    )


async def test_a_custom_shock_concentration_does_not_carry_to_another_product(
    hass: HomeAssistant,
) -> None:
    entry = await setup_pool(hass)
    result = await _open_water(hass, entry)
    done = await hass.config_entries.options.async_configure(
        result["flow_id"], form_input(result, {"shock_concentration": 70})
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["shock_concentration"] == 70

    # Switched to a liquid with the 70 % still in the box: it is not 70 g/L.
    result = await _open_water(hass, entry)
    done = await hass.config_entries.options.async_configure(
        result["flow_id"],
        form_input(result, {"shock_product": "sodium_hypochlorite", "shock_concentration": 70}),
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options.get("shock_concentration") is None
    dose = entry.runtime_data._treatment_dose("shock", "green")  # noqa: SLF001
    assert (dose.concentration, dose.unit) == (150, "L")

    # A figure typed for the new product along with it is kept.
    result = await _open_water(hass, entry)
    done = await hass.config_entries.options.async_configure(
        result["flow_id"],
        form_input(result, {"shock_product": "dichlor", "shock_concentration": 60}),
    )
    await hass.async_block_till_done()
    assert entry.options["shock_concentration"] == 60


@pytest.mark.parametrize(
    ("product", "value", "ok"),
    [
        ("calcium_hypochlorite", 120, False),
        ("dichlor", 101, False),
        ("calcium_hypochlorite", 70, True),
        ("sodium_hypochlorite", 120, True),
        ("sodium_hypochlorite", 301, False),
    ],
)
async def test_the_shock_concentration_must_be_possible_for_its_product(
    hass: HomeAssistant, product: str, value: float, ok: bool
) -> None:
    entry = await setup_pool(hass, shock_product=product)
    result = await _open_water(hass, entry)
    done = await hass.config_entries.options.async_configure(
        result["flow_id"], form_input(result, {"shock_concentration": value})
    )
    if ok:
        assert done["type"] is FlowResultType.CREATE_ENTRY
    else:
        assert done["errors"] == {"treatments": "concentration_range"}


async def test_the_depths_come_empty(hass: HomeAssistant) -> None:
    """A depth that looks real gets accepted unread: none is offered."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Pool", "latitude": 39.6, "longitude": -0.5}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"shape": "rectangular"}
    )
    assert result["step_id"] == "dimensions"
    suggested = {
        str(k): (k.description or {}).get("suggested_value")
        for k in result["data_schema"].schema
    }
    assert suggested["depth_min"] is None
    assert suggested["depth_max"] is None


async def test_an_older_install_keeps_its_backwash_interval(hass: HomeAssistant) -> None:
    """The interval asked in the filtration step up to 0.2 still counts, and
    saving that step no longer touches it."""
    entry = await setup_pool(hass, backwash_interval_days=10)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "pump"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"pump_model": "custom"}
    )
    assert result["step_id"] == "filtration"
    assert "backwash_interval_days" not in form_fields(result)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"pump_nominal_flow_rate": entry.data["pump_nominal_flow_rate"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["backwash_interval_days"] == 10

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "tasks"}
    )
    defaults = {
        str(k): k.default()
        for k in result["data_schema"].schema
        if callable(getattr(k, "default", None))
    }
    assert defaults["backwash_days"] == 10


async def test_an_error_shows_on_its_section(hass: HomeAssistant) -> None:
    """Home Assistant draws errors on a section, not on a field inside one."""
    entry = await setup_pool(hass)
    result = await _open_water(hass, entry)
    bad = await hass.config_entries.options.async_configure(
        result["flow_id"], form_input(result, {"ph_target": 7.9, "ph_range_max": 7.6})
    )
    assert bad["errors"] == {"ph": "ph_order"}
    # The pH kit question is answered here now.
    done = await hass.config_entries.options.async_configure(
        result["flow_id"], form_input(result, {"has_ph_probe_outside": True})
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["has_ph_probe_outside"] is True


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("step", ["filtration", "water", "control"])
async def test_every_field_and_section_has_a_label(
    hass: HomeAssistant, step: str, language: str
) -> None:
    import json
    import pathlib

    from homeassistant.data_entry_flow import section

    root = pathlib.Path(__file__).parent.parent / "custom_components" / "homepool"
    texts = json.loads((root / "translations" / f"{language}.json").read_text(encoding="utf-8"))
    entry = await setup_pool(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    first = "pump" if step == "filtration" else step
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": first}
    )
    if step == "filtration":
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"pump_model": "custom"}
        )
    assert result["step_id"] == step
    labels = texts["options"]["step"][step]
    for marker, value in result["data_schema"].schema.items():
        name = str(marker)
        if isinstance(value, section):
            sec = labels["sections"][name]
            assert sec["name"]
            for key in value.schema.schema:
                assert sec["data"].get(str(key)), (name, str(key))
        else:
            assert labels["data"].get(name), name
