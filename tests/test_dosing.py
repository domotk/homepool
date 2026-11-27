"""The winter product's dose."""

from __future__ import annotations

from custom_components.homepool.pool.dosing import Dose, winter_product_dose


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
