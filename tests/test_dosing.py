"""The winter product's dose."""

from __future__ import annotations

from custom_components.homepool.pool.dosing import (
    SHOCK_DEFAULT_CONCENTRATION,
    SHOCK_RISE,
    Dose,
    label_dose,
    shock_dose,
    winter_product_dose,
)

from .test_control import local, madrid  # noqa: F401


def test_one_floater_for_45_m3() -> None:
    dose = winter_product_dose("floater", 0.02, 45)
    assert dose.amount == 1
    assert dose.unit == "units"
    assert dose.product == "floater"
    assert dose.volume_m3 == 45
    assert dose.basis == "45 m³ × 0.02/m³"
    assert dose.follow_label


def test_floaters_round_up() -> None:
    assert winter_product_dose("floater", 0.02, 51).amount == 2
    assert winter_product_dose("tablets", 0.02, 51).amount == 2


def test_liquid_litres() -> None:
    dose = winter_product_dose("liquid", 0.01, 45)
    assert dose.amount == 0.45
    assert dose.unit == "L"


def test_dose_is_a_plain_record() -> None:
    assert Dose(None, "units", "floater", None, 45, "", True).amount is None


# ── water treatment ──


def test_shock_dose_granular() -> None:
    dose = shock_dose("calcium_hypochlorite", 65, 45, "green")
    assert dose.amount == 1040
    assert dose.unit == "g"
    assert dose.product == "calcium_hypochlorite"
    assert dose.concentration == 65
    assert dose.volume_m3 == 45
    assert "45 m³" in dose.basis and "15 mg/L" in dose.basis
    assert dose.follow_label
    assert dose.cya_rise_mg_l is None


def test_shock_dose_liquid() -> None:
    dose = shock_dose("sodium_hypochlorite", 150, 45, "green")
    assert dose.amount == 4.5
    assert dose.unit == "L"


def test_shock_severity_sets_the_rise() -> None:
    assert SHOCK_RISE == {"light": 10, "green": 15, "dark": 20}
    # 45 m³ × 20 mg/L = 900 g of chlorine; at 65 % that is 1384.6 g.
    assert shock_dose("calcium_hypochlorite", 65, 45, "dark").amount == 1380
    assert shock_dose("sodium_hypochlorite", 150, 45, "light").amount == 3.0


def test_dichlor_warns_of_cya() -> None:
    dose = shock_dose("dichlor", SHOCK_DEFAULT_CONCENTRATION["dichlor"], 45, "green")
    assert dose.cya_rise_mg_l == 13.5
    assert dose.unit == "g"


def test_label_dose_without_setting_says_follow_label() -> None:
    dose = label_dose("clarifier", None, "mL", 45)
    assert dose.amount is None and dose.follow_label
    assert dose.unit == "mL"
    assert dose.volume_m3 == 45


def test_label_dose_per_10_m3() -> None:
    dose = label_dose("flocculant", 40, "mL", 45)
    assert dose.amount == 180
    assert dose.follow_label
    assert "45 m³" in dose.basis


def test_without_a_volume_the_dose_is_the_label_s() -> None:
    """M11: no volume, no figure: "follow the label", not 0 g."""
    for product in SHOCK_DEFAULT_CONCENTRATION:
        dose = shock_dose(product, SHOCK_DEFAULT_CONCENTRATION[product], 0, "green")
        assert dose.amount is None
        assert dose.follow_label
        assert dose.basis == ""
    dose = label_dose("flocculant", 2.0, "L", 0)
    assert dose.amount is None and dose.follow_label and dose.basis == ""


async def test_a_shock_without_a_volume_follows_the_label(hass, madrid, freezer) -> None:
    from .helpers import SwitchRouter, setup_pool
    from .test_treatment import start

    freezer.move_to(local(2026, 7, 15, 10, 0))
    SwitchRouter(hass)
    entry = await setup_pool(hass, volume=0)
    await start(hass, entry, "shock")
    dose = entry.runtime_data.treatment["dose"]
    assert dose["amount"] is None and dose["follow_label"] is True
