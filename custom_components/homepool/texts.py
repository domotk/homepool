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


# Why the pump is as it is, keyed by the decision's ``key``. Shown on the
# control sensor's ``reason`` attribute and on the card.
REASONS: dict[str, dict[str, str]] = {
    "en": {
        "unavailable": "The pump switch is unavailable",
        "hands_off": "Hands off: the pump is being run by hand",
        "maintenance_lock": "Maintenance lock is on",
        "safety": "Safety shutoff: {reason}",
        "freeze_protection": "Freeze protection: water near 0 °C",
        "ph_correction": "pH correction needs water flowing",
        "manual_cycle": "Manual cycle in progress",
        "manual_override_on": "Switched on by hand; respected for now",
        "manual_override_off": "Switched off by hand; respected for now",
        "released_freeze_protection": "No longer needed for freeze protection",
        "released_ph_correction": "No longer needed for pH correction",
        "released_manual_cycle": "The manual cycle has ended",
        "no_mode": "No mode",
        "min_run": "{reason} (waiting {minutes} min: minimum run time)",
        "min_rest": "{reason} (waiting {minutes} min: minimum rest time)",
        "off_mode": "Off mode: the pump is controlled by hand",
        "timer_no_slots": "Timer mode: no time slots configured",
        "timer_in_slot": "Timer mode: inside a scheduled slot",
        "timer_outside_slot": "Timer mode: outside the scheduled slots",
        "smart_target_reached": "Smart mode: today's target is reached",
        "smart_must_run": "Smart mode: only just enough day left to reach the target",
        "smart_in_block": "Smart mode: inside the block centred on solar noon",
        "smart_waiting_block": "Smart mode: waiting for the block centred on solar noon",
        "solar_target_reached": "Solar mode: today's target is reached",
        "solar_no_reading": "Solar mode: no surplus reading",
        "solar_surplus": "Solar mode: there is enough surplus",
        "solar_no_surplus": "Solar mode: not enough surplus",
        "smart_solar_target_reached": "Smart+Solar: today's target is reached",
        "smart_solar_grid": "Smart+Solar: finishing from the grid before the day ends",
        "smart_solar_surplus": "Smart+Solar: running on surplus",
        "smart_solar_waiting": "Smart+Solar: waiting for surplus",
    },
    "es": {
        "unavailable": "El interruptor de la bomba no está disponible",
        "hands_off": "Manos fuera: la bomba se maneja a mano",
        "maintenance_lock": "El bloqueo de mantenimiento está activado",
        "safety": "Parada de seguridad: {reason}",
        "freeze_protection": "Protección antiheladas: agua cerca de 0 °C",
        "ph_correction": "La corrección del pH necesita el agua en movimiento",
        "manual_cycle": "Ciclo manual en marcha",
        "manual_override_on": "Encendida a mano; se respeta por ahora",
        "manual_override_off": "Apagada a mano; se respeta por ahora",
        "released_freeze_protection": "Ya no hace falta para la protección antiheladas",
        "released_ph_correction": "Ya no hace falta para corregir el pH",
        "released_manual_cycle": "El ciclo manual ha terminado",
        "no_mode": "Sin modo",
        "min_run": "{reason} (esperando {minutes} min: tiempo mínimo en marcha)",
        "min_rest": "{reason} (esperando {minutes} min: tiempo mínimo de descanso)",
        "off_mode": "Modo apagado: la bomba se maneja a mano",
        "timer_no_slots": "Modo temporizador: no hay franjas configuradas",
        "timer_in_slot": "Modo temporizador: dentro de una franja",
        "timer_outside_slot": "Modo temporizador: fuera de las franjas",
        "smart_target_reached": "Modo inteligente: objetivo de hoy cumplido",
        "smart_must_run": "Modo inteligente: queda el día justo para cumplir el objetivo",
        "smart_in_block": "Modo inteligente: dentro del bloque centrado en el mediodía solar",
        "smart_waiting_block": "Modo inteligente: esperando al bloque centrado en el mediodía solar",
        "solar_target_reached": "Modo solar: objetivo de hoy cumplido",
        "solar_no_reading": "Modo solar: sin lectura de excedente",
        "solar_surplus": "Modo solar: hay excedente suficiente",
        "solar_no_surplus": "Modo solar: no hay excedente suficiente",
        "smart_solar_target_reached": "Inteligente+Solar: objetivo de hoy cumplido",
        "smart_solar_grid": "Inteligente+Solar: terminando con la red antes de que acabe el día",
        "smart_solar_surplus": "Inteligente+Solar: en marcha con excedente",
        "smart_solar_waiting": "Inteligente+Solar: esperando excedente",
    },
}


def reason_text(
    language: str | None, key: str, args: dict[str, str] | None = None, fallback: str = ""
) -> str:
    """The reason for ``key`` in ``language``; ``fallback`` if it has no text."""
    lang = (language or "en").split("-")[0].lower()
    table = REASONS.get(lang, REASONS["en"])
    template = table.get(key) or REASONS["en"].get(key)
    if template is None:
        return fallback
    values = dict(args or {})
    if "reason_key" in values:
        values["reason"] = reason_text(language, values.pop("reason_key"), None, fallback)
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return fallback or template
