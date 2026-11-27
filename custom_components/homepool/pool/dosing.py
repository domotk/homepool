"""Doses of what the owner adds to the water.

Pure logic, no Home Assistant imports: the winter product and the water
treatments. Every dose carries the figures it was worked out from, and the
product's label has the last word.
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
    # Dichlor is stabilised chlorine: it raises the cyanuric acid as well.
    cya_rise_mg_l: float | None = None


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


# How much a shock raises the free chlorine, in mg/L, by how green the water
# is. Figures from general pool guides, not from a product's label.
SHOCK_RISE: dict[str, float] = {"light": 10, "green": 15, "dark": 20}

# Per cent of available chlorine for the granular products, g/L for the liquid.
SHOCK_DEFAULT_CONCENTRATION: dict[str, float] = {
    "calcium_hypochlorite": 65.0,
    "sodium_hypochlorite": 150.0,
    "dichlor": 56.0,
}
SHOCK_LIQUIDS = ("sodium_hypochlorite",)
# mg/L of cyanuric acid per mg/L of chlorine from dichlor.
DICHLOR_CYA_PER_CHLORINE = 0.9


def shock_dose(product: str, concentration: float, volume_m3: float, severity: str) -> Dose:
    """``volume × rise`` grams of chlorine, in grams of a granular product
    (to the nearest 10 g) or litres of a liquid (to 0.1 L)."""
    rise = SHOCK_RISE[severity]
    chlorine_g = volume_m3 * rise
    working = f"{volume_m3:g} m³ × {rise:g} mg/L = {chlorine_g:g} g of chlorine"
    if product in SHOCK_LIQUIDS:
        amount = round(chlorine_g / concentration, 1)
        unit = "L"
        working += f" ÷ {concentration:g} g/L"
    else:
        amount = float(round(chlorine_g / (concentration / 100) / 10) * 10)
        unit = "g"
        working += f" ÷ {concentration:g} %"
    return Dose(
        amount=amount,
        unit=unit,
        product=product,
        concentration=concentration,
        volume_m3=volume_m3,
        basis=working,
        follow_label=True,
        cya_rise_mg_l=(
            round(DICHLOR_CYA_PER_CHLORINE * rise, 1) if product == "dichlor" else None
        ),
    )


def label_dose(product: str, per_10m3: float | None, unit: str, volume_m3: float) -> Dose:
    """A clarifier or a flocculant, by the label's dose per 10 m³. HomePool has
    no figure of its own: without one the dose is "follow the label"."""
    if per_10m3 is None:
        amount, basis = None, ""
    else:
        amount = round(per_10m3 * volume_m3 / 10, 1)
        basis = f"{volume_m3:g} m³ × {per_10m3:g} {unit}/10 m³"
    return Dose(
        amount=amount,
        unit=unit,
        product=product,
        concentration=None,
        volume_m3=volume_m3,
        basis=basis,
        follow_label=True,
    )
