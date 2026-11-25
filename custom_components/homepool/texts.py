"""Free text HomePool writes while running, in the languages it ships.

Home Assistant's translation files cover the interface — entity names, flow
labels, selector options — but not text composed at runtime, which is what an
alert or a notification is. Picked by ``hass.config.language``, English for
anything else.
"""

from __future__ import annotations

from typing import Any

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "safety_shutoff": "{pool}: pump stopped for safety ({reason}).",
        "pump_not_responding": (
            "{pool}: the pump switch did not follow the last {attempts} commands "
            "(wanted {state})."
        ),
        "chlorinator_not_responding": (
            "{pool}: the chlorinator switch did not follow the last {attempts} commands "
            "(wanted {state}). The pump was stopped anyway; check the cell."
        ),
        "freeze_protection": "{pool}: water near freezing, the pump is kept running.",
        "ph_out_of_range": "{pool}: pH {value:.2f} is outside {low:.1f}–{high:.1f}.",
        "salt_low": "{pool}: salt at {value:.1f} g/L, below {low:.1f} g/L.",
        "chlorinator_cold": (
            "{pool}: water at {value:.0f} °C, too cold for the salt cell; "
            "it stays off until the water warms up."
        ),
        "chlorinator_not_producing": (
            "{pool}: the chlorinator cannot produce chlorine with the current salt "
            "and temperature."
        ),
        "target_missed": (
            "{pool}: yesterday the pump ran {elapsed} min of a {target} min target."
        ),
        "backwash_due": "{pool}: the filter is due a backwash.",
        "filter_cleaning_due": "{pool}: the filter cartridge is due a clean.",
        "ph_calibration_due": "{pool}: the pH probe is due a calibration.",
        "season_start": (
            "{pool}: chlorinator season starts. Check the salt, clean the cell and "
            "calibrate the pH probe."
        ),
        "season_end": (
            "{pool}: chlorinator season ends. Clean the cell, switch to tablets if "
            "you use them, and protect the pH probe."
        ),
        "title": "Pool",
    },
    "es": {
        "safety_shutoff": "{pool}: bomba parada por seguridad ({reason}).",
        "pump_not_responding": (
            "{pool}: el interruptor de la bomba no ha obedecido las últimas "
            "{attempts} órdenes (se quería {state})."
        ),
        "chlorinator_not_responding": (
            "{pool}: el interruptor del clorador no ha obedecido las últimas "
            "{attempts} órdenes (se quería {state}). La bomba se ha parado igualmente; "
            "revisa la célula."
        ),
        "freeze_protection": (
            "{pool}: el agua está cerca de congelarse, la bomba se mantiene en marcha."
        ),
        "ph_out_of_range": "{pool}: el pH {value:.2f} está fuera de {low:.1f}–{high:.1f}.",
        "salt_low": "{pool}: sal en {value:.1f} g/L, por debajo de {low:.1f} g/L.",
        "chlorinator_cold": (
            "{pool}: el agua está a {value:.0f} °C, demasiado fría para la célula; "
            "el clorador no funcionará hasta que se caliente."
        ),
        "chlorinator_not_producing": (
            "{pool}: el clorador no puede producir cloro con la sal y la "
            "temperatura actuales."
        ),
        "target_missed": (
            "{pool}: ayer la bomba funcionó {elapsed} min de un objetivo de {target} min."
        ),
        "backwash_due": "{pool}: toca hacer un contralavado del filtro.",
        "filter_cleaning_due": "{pool}: toca limpiar el cartucho del filtro.",
        "ph_calibration_due": "{pool}: toca calibrar la sonda de pH.",
        "season_start": (
            "{pool}: empieza la temporada del clorador. Revisa la sal, limpia la "
            "célula y calibra la sonda de pH."
        ),
        "season_end": (
            "{pool}: termina la temporada del clorador. Limpia la célula, pasa a "
            "pastillas si las usas y protege la sonda de pH."
        ),
        "title": "Piscina",
    },
}


def text(language: str | None, key: str, **values: Any) -> str:
    """The text for ``key`` in ``language``, English if that is not shipped."""
    lang = (language or "en").split("-")[0].lower()
    table = TEXTS.get(lang, TEXTS["en"])
    template = table.get(key) or TEXTS["en"][key]
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return template
