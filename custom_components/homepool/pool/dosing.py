"""Doses of what the owner adds to the water.

Pure logic, no Home Assistant imports. Only the winter product so far.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass
class Dose:
    amount: float | None
    unit: str  # "units", "g", "L", "mL"
    product: str
    concentration: float | None
    volume_m3: float
    basis: str  # the working, such as "45 m³ × 0.02/m³"
    follow_label: bool  # the product's label has the last word


def winter_product_dose(product_type: str, per_m3: float, volume_m3: float) -> Dose:
    """``volume × dose``: whole floaters or tablets rounded up, litres of
    liquid to two decimals."""
    raw = volume_m3 * per_m3
    if product_type == "liquid":
        amount: float = round(raw, 2)
        unit = "L"
    else:
        amount = ceil(round(raw, 6))
        unit = "units"
    return Dose(
        amount=amount,
        unit=unit,
        product=product_type,
        concentration=None,
        volume_m3=volume_m3,
        basis=f"{volume_m3:g} m³ × {per_m3:g}/m³",
        follow_label=True,
    )
