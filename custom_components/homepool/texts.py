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
        "freeze_protection_blocked": (
            "{pool}: water near freezing, but HomePool cannot keep the pump running "
            "({reason}). Make sure the pipes are protected."
        ),
        "freeze_protection_passive": (
            "{pool}: frost expected: check that the plugs and gizmos are in."
        ),
        "ph_out_of_range": "{pool}: pH {value:.2f} is outside {low:.1f}–{high:.1f}.",
        "salt_low": "{pool}: salt at {value:.1f} g/L, below {low:.1f} g/L.",
        "free_chlorine_out_of_range": "{pool}: free chlorine {value:g} mg/L, outside {range}.",
        "combined_chlorine_out_of_range": "{pool}: combined chlorine {value:g} mg/L, outside {range}.",
        "total_alkalinity_out_of_range": "{pool}: total alkalinity {value:g} mg/L, outside {range}.",
        "calcium_hardness_out_of_range": "{pool}: calcium hardness {value:g} mg/L, outside {range}.",
        "cyanuric_acid_out_of_range": "{pool}: cyanuric acid {value:g} mg/L, outside {range}.",
        "reading_stale": (
            "{pool}: readings too old to be used: {kinds}. Measure them again."
        ),
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
        "winter_product_due": "{pool}: the winter product needs topping up.",
        "water_test_due": "{pool}: time to measure the pH and the free chlorine.",
        "skimmer_baskets_due": "{pool}: time to empty the skimmer and pump baskets.",
        "cell_cleaning_due": "{pool}: the salt cell is due a check and a clean.",
        "filter_media_check_due": "{pool}: the filter sand or glass is due a check.",
        "season_start": (
            "{pool}: chlorinator season starts. Check the salt, clean the cell and "
            "calibrate the pH probe."
        ),
        "season_end": (
            "{pool}: chlorinator season ends. Clean the cell, switch to tablets if "
            "you use them, and protect the pH probe."
        ),
        "season_proposal_winter": (
            "{pool}: the swimming season is over. Choose active or passive wintering "
            "in the season state when you close the pool."
        ),
        "season_proposal_opening": (
            "{pool}: the swimming season is about to start. Set the season state to "
            "opening when you start getting the pool ready."
        ),
        "season_state_introduced": (
            "{pool}: HomePool now keeps a season state, and it is set to {state}. "
            "Change it if that is not right."
        ),
        "season_proposal_swimming": (
            "{pool}: the pool is ready. Set the season state to swimming to start the season."
        ),
        "closing_needs_pump": (
            "{pool}: passive wintering was confirmed with closing steps that need the "
            "pump still open. The pump will no longer start."
        ),
        "treatment_frost": (
            "{pool}: freeze protection is running the pump, so the flocculant's "
            "settling is interrupted. It carries on counting once the frost has passed."
        ),
        "treatment_vacuuming": (
            "{pool}: the flocculant is waiting for you to vacuum the floor. When you "
            "are done, press \"Next treatment phase (vacuuming done)\": until then "
            "HomePool leaves the pump to you."
        ),
        "step_closing_shock": "Shock the water with the pH at 7.2–7.4.",
        "step_closing_cell": "Clean the salt cell and store it.",
        "step_closing_backwash": "Backwash the filter.",
        "step_closing_lower_level": "Lower the water level below the skimmers.",
        "step_closing_plugs": "Fit the plugs and gizmos and drain the pipes.",
        "step_closing_winter_product": "Add the winter product.",
        "step_opening_remove_winter_product": "Remove the winter product.",
        "step_opening_backwash": "Backwash the filter.",
        "step_opening_measure": "Measure pH, alkalinity, cyanuric acid and salt.",
        "step_opening_salt": "Add salt up to the target.",
        "step_opening_reconnect_cell": "Reconnect the salt cell; this turns the chlorinator on.",
        "step_opening_calibrate_ph": "Calibrate the pH probe.",
        "step_opening_shock": "Shock the water.",
        "step_treatment_brush": "Brush the walls and the floor.",
        "step_treatment_ph_shock": "Adjust the pH to 7.0–7.4.",
        "step_treatment_ph_settle": "Adjust the pH to 7.2–7.6.",
        "step_treatment_dose": "Add the dose.",
        "step_treatment_algaecide": "Add a copper-free algaecide.",
        "step_treatment_measure": "Measure pH and chlorine after 12–24 h.",
        "step_treatment_vacuum": "Vacuum the floor to waste.",
        "step_treatment_backwash": "Backwash when it is done.",
        "step_treatment_refill": "Refill the water.",
        "season_swimming": "swimming",
        "season_winter_active": "active wintering",
        "season_winter_passive": "passive wintering",
        "season_opening": "opening",
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
        "freeze_protection_blocked": (
            "{pool}: el agua está cerca de congelarse, pero HomePool no puede mantener "
            "la bomba en marcha ({reason}). Asegúrate de que las tuberías están protegidas."
        ),
        "freeze_protection_passive": (
            "{pool}: helada prevista: revisa que los tapones y los gizmos estén puestos."
        ),
        "ph_out_of_range": "{pool}: el pH {value:.2f} está fuera de {low:.1f}–{high:.1f}.",
        "salt_low": "{pool}: sal en {value:.1f} g/L, por debajo de {low:.1f} g/L.",
        "free_chlorine_out_of_range": "{pool}: cloro libre {value:g} mg/L, fuera de {range}.",
        "combined_chlorine_out_of_range": "{pool}: cloro combinado {value:g} mg/L, fuera de {range}.",
        "total_alkalinity_out_of_range": "{pool}: alcalinidad {value:g} mg/L, fuera de {range}.",
        "calcium_hardness_out_of_range": "{pool}: dureza cálcica {value:g} mg/L, fuera de {range}.",
        "cyanuric_acid_out_of_range": "{pool}: ácido cianúrico {value:g} mg/L, fuera de {range}.",
        "reading_stale": (
            "{pool}: lecturas demasiado antiguas para usarse: {kinds}. Vuelve a medirlas."
        ),
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
        "winter_product_due": "{pool}: toca reponer el producto de invierno.",
        "water_test_due": "{pool}: toca medir el pH y el cloro libre.",
        "skimmer_baskets_due": "{pool}: toca vaciar los cestos del skimmer y del prefiltro.",
        "cell_cleaning_due": "{pool}: toca revisar y limpiar la célula del clorador.",
        "filter_media_check_due": "{pool}: toca revisar la arena o el vidrio del filtro.",
        "season_start": (
            "{pool}: empieza la temporada del clorador. Revisa la sal, limpia la "
            "célula y calibra la sonda de pH."
        ),
        "season_end": (
            "{pool}: termina la temporada del clorador. Limpia la célula, pasa a "
            "pastillas si las usas y protege la sonda de pH."
        ),
        "season_proposal_winter": (
            "{pool}: ha terminado la temporada de baño. Elige invernaje activo o pasivo "
            "en el estado de temporada cuando cierres la piscina."
        ),
        "season_proposal_opening": (
            "{pool}: la temporada de baño está a punto de empezar. Pon el estado "
            "de temporada en puesta en marcha cuando empieces a prepararla."
        ),
        "season_state_introduced": (
            "{pool}: HomePool tiene ahora estado de temporada: está en {state}; "
            "cámbialo si no es así."
        ),
        "season_proposal_swimming": (
            "{pool}: la piscina está lista. Cambia el estado de temporada a baño para "
            "empezar la temporada."
        ),
        "closing_needs_pump": (
            "{pool}: se ha confirmado el invernaje pasivo con pasos de cierre que "
            "necesitan la bomba sin hacer. La bomba ya no arrancará."
        ),
        "treatment_frost": (
            "{pool}: la antiheladas tiene la bomba en marcha, así que el reposo del "
            "floculante se ha interrumpido. Sigue contando cuando pase la helada."
        ),
        "treatment_vacuuming": (
            "{pool}: el floculante está esperando a que aspires el fondo. Cuando "
            "termines, pulsa «Siguiente fase del tratamiento (aspirado terminado)»: "
            "hasta entonces la bomba la manejas tú."
        ),
        "step_closing_shock": "Choque con el pH en 7,2–7,4.",
        "step_closing_cell": "Limpia la célula y guárdala.",
        "step_closing_backwash": "Haz un contralavado.",
        "step_closing_lower_level": "Baja el nivel del agua bajo los skimmers.",
        "step_closing_plugs": "Pon los tapones y gizmos y vacía las tuberías.",
        "step_closing_winter_product": "Echa el producto de invierno.",
        "step_opening_remove_winter_product": "Retira el producto de invierno.",
        "step_opening_backwash": "Haz un contralavado.",
        "step_opening_measure": "Mide pH, alcalinidad, ácido cianúrico y sal.",
        "step_opening_salt": "Añade sal hasta el objetivo.",
        "step_opening_reconnect_cell": "Reconecta la célula; esto enciende el clorador.",
        "step_opening_calibrate_ph": "Calibra la sonda de pH.",
        "step_opening_shock": "Haz el choque.",
        "step_treatment_brush": "Cepilla paredes y fondo.",
        "step_treatment_ph_shock": "Ajusta el pH a 7,0–7,4.",
        "step_treatment_ph_settle": "Ajusta el pH a 7,2–7,6.",
        "step_treatment_dose": "Echa la dosis.",
        "step_treatment_algaecide": "Echa un alguicida sin cobre.",
        "step_treatment_measure": "Mide pH y cloro a las 12–24 h.",
        "step_treatment_vacuum": "Aspira el fondo a desagüe.",
        "step_treatment_backwash": "Haz un contralavado al terminar.",
        "step_treatment_refill": "Rellena el agua.",
        "season_swimming": "baño",
        "season_winter_active": "invernaje activo",
        "season_winter_passive": "invernaje pasivo",
        "season_opening": "puesta en marcha",
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
        "winter_passive": "Passive wintering: the pump stays off",
        "safety": "Safety shutoff: {reason}",
        "freeze_protection": "Freeze protection: water near 0 °C",
        "ph_correction": "pH correction needs water flowing",
        "manual_cycle": "Manual cycle in progress",
        "treatment_filtering": "Water treatment: filtering without a break",
        "treatment_mixing": "Flocculant: mixing it in with the pump on",
        "treatment_settling": "Flocculant: settling, the pump stays off",
        "treatment_vacuuming": "Flocculant: vacuuming, the pump is yours to run",
        "manual_override_on": "Switched on by hand; respected for now",
        "manual_override_off": "Switched off by hand; respected for now",
        "automation_override_on": "Switched on by the automation «{name}»; respected for now",
        "automation_override_off": "Switched off by the automation «{name}»; respected for now",
        "script_override_on": "Switched on by the script «{name}»; respected for now",
        "script_override_off": "Switched off by the script «{name}»; respected for now",
        "external_override_on": "Switched on outside HomePool; respected for now",
        "external_override_off": "Switched off outside HomePool; respected for now",
        "released_freeze_protection": "No longer needed for freeze protection",
        "released_ph_correction": "No longer needed for pH correction",
        "released_manual_cycle": "The manual cycle has ended",
        "released_treatment": "The water treatment has ended",
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
        "winter_passive": "Invernaje pasivo: la bomba se queda parada",
        "safety": "Parada de seguridad: {reason}",
        "freeze_protection": "Protección antiheladas: agua cerca de 0 °C",
        "ph_correction": "La corrección del pH necesita el agua en movimiento",
        "manual_cycle": "Ciclo manual en marcha",
        "treatment_filtering": "Tratamiento del agua: filtrando sin parar",
        "treatment_mixing": "Floculante: mezclándolo con la bomba en marcha",
        "treatment_settling": "Floculante: en reposo, la bomba se queda parada",
        "treatment_vacuuming": "Floculante: aspirando, la bomba la manejas tú",
        "manual_override_on": "Encendida a mano; se respeta por ahora",
        "manual_override_off": "Apagada a mano; se respeta por ahora",
        "automation_override_on": "Encendida por la automatización «{name}»; se respeta por ahora",
        "automation_override_off": "Apagada por la automatización «{name}»; se respeta por ahora",
        "script_override_on": "Encendida por el script «{name}»; se respeta por ahora",
        "script_override_off": "Apagada por el script «{name}»; se respeta por ahora",
        "external_override_on": "Encendida fuera de HomePool; se respeta por ahora",
        "external_override_off": "Apagada fuera de HomePool; se respeta por ahora",
        "released_freeze_protection": "Ya no hace falta para la protección antiheladas",
        "released_ph_correction": "Ya no hace falta para corregir el pH",
        "released_manual_cycle": "El ciclo manual ha terminado",
        "released_treatment": "El tratamiento del agua ha terminado",
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
