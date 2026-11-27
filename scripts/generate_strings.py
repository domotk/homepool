"""Generate strings.json, translations/en.json and translations/es.json.

The interface text lives here, each leaf as (english, spanish); the three
JSON files are its output and are not edited by hand. Run it from the
repository root after changing any text:

    python scripts/generate_strings.py

It needs PyYAML (installed with Home Assistant) to read the layout names from
data/layouts.yaml. Text composed at runtime (alerts, reasons) is in texts.py.
"""
import json, pathlib, sys

ROOT = (
    pathlib.Path(sys.argv[1])
    if len(sys.argv) > 1
    else pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "homepool"
)

def T(en, es): return (en, es)

# One name per recurring task, in the sentence "<name>: ...".
task_names = {
  "backwash": T("Backwash", "Contralavado"), "filter_cleaning": T("Filter cleaning", "Limpieza del filtro"),
  "ph_calibration": T("pH probe calibration", "Calibración de la sonda de pH"),
  "winter_product": T("Winter product", "Producto de invierno"), "water_test": T("Water test", "Medición del agua"),
  "skimmer_baskets": T("Skimmer baskets", "Cestos del skimmer"), "cell_cleaning": T("Cell cleaning", "Limpieza de la célula"),
  "filter_media_check": T("Filter media check", "Revisión de la arena o el vidrio"),
}
season_states = {"swimming": T("Swimming", "Baño"), "winter_active": T("Active wintering", "Invernaje activo"),
  "winter_passive": T("Passive wintering", "Invernaje pasivo"), "opening": T("Opening", "Puesta en marcha")}

# Chemistry readings taken by hand: one name each, for the ranges, the stale ages and the service.
reading_names = {
  "ph": T("pH", "pH"), "free_chlorine": T("Free chlorine", "Cloro libre"),
  "combined_chlorine": T("Combined chlorine", "Cloro combinado"), "total_alkalinity": T("Total alkalinity", "Alcalinidad total"),
  "calcium_hardness": T("Calcium hardness", "Dureza cálcica"), "cyanuric_acid": T("Cyanuric acid", "Ácido cianúrico"),
  "salt": T("Salt", "Sal"),
}
reading_data = {}
for _k in ("combined_chlorine", "total_alkalinity", "calcium_hardness", "cyanuric_acid"):
  _en, _es = reading_names[_k]
  if _k != "combined_chlorine":
    reading_data[f"{_k}_range_min"] = T(f"{_en}, lowest", f"{_es} mínima")
  reading_data[f"{_k}_range_max"] = T(f"{_en}, highest", f"{_es} máxima")
for _k, (_en, _es) in reading_names.items():
  reading_data[f"{_k}_stale_days"] = T(f"{_en} reading, trusted for (days)", f"Lectura de {_es.lower()}, válida durante (días)")

_pump_hours_tasks = ("backwash", "filter_cleaning")
_optional_tasks = ("water_test", "skimmer_baskets", "filter_media_check")
tasks_data = {}
for _k, (_en, _es) in task_names.items():
  tasks_data[f"{_k}_days"] = T(f"{_en}: every (days)", f"{_es}: cada (días)")
  if _k in _pump_hours_tasks:
    tasks_data[f"{_k}_pump_hours"] = T(f"{_en} in winter: every (pump hours)", f"{_es} en invierno: cada (horas de bomba)")
  if _k in _optional_tasks:
    tasks_data[f"{_k}_enabled"] = T(f"{_en}: remind me", f"{_es}: avisarme")
  tasks_data[f"{_k}_last_done"] = T(f"{_en}: last done", f"{_es}: última vez")
tasks_data["has_ph_probe_outside"] = T("I check the pH with a probe or kit of my own", "Mido el pH con una sonda o un kit propios")

steps_fields = {
  "identity": {
    "title": T("Your pool", "Tu piscina"),
    "description": T("A name, and where the pool is. The location sets the hemisphere and the seasons; it defaults to your home.",
                     "Un nombre y dónde está la piscina. La ubicación decide el hemisferio y las estaciones; por defecto es la de tu casa."),
    "data": {"name": T("Name", "Nombre"), "latitude": T("Latitude", "Latitud"), "longitude": T("Longitude", "Longitud")},
  },
  "shape": {
    "title": T("Shape", "Forma"),
    "data": {"shape": T("Shape of the pool", "Forma de la piscina")},
  },
  "dimensions": {
    "title": T("Dimensions", "Medidas"),
    "description": T("Inside measurements of the water, in metres. If the depth is the same everywhere, give it twice.",
                     "Medidas interiores del vaso, en metros. Si la profundidad es la misma en toda la piscina, pon el mismo valor dos veces."),
    "data": {
      "side": T("Side", "Lado"), "length": T("Length", "Largo"), "width": T("Width", "Ancho"),
      "diameter": T("Diameter", "Diámetro"),
      "length_1": T("Length, first part", "Largo de la primera parte"), "width_1": T("Width, first part", "Ancho de la primera parte"),
      "length_2": T("Length, second part", "Largo de la segunda parte"), "width_2": T("Width, second part", "Ancho de la segunda parte"),
      "depth_min": T("Shallowest depth", "Profundidad mínima"), "depth_max": T("Deepest depth", "Profundidad máxima"),
      "layout_variant": T("Steps, islands and the like", "Escaleras, islas y similares"),
    },
  },
  "layout_orientation": {
    "title": T("Where they are", "Dónde están"),
    "data": {"layout_orientation": T("Position", "Posición")},
  },
  "volume": {
    "title": T("Volume", "Volumen"),
    "description": T("From those measurements the pool holds about **{volume} m³**. If you know the real figure, from the builder or from filling it, enter it here; otherwise leave it empty.",
                     "Con esas medidas, la piscina tiene unos **{volume} m³**. Si sabes la cifra real, por el constructor o por el llenado, escríbela aquí; si no, déjalo vacío."),
    "data": {"volume_override": T("Real volume", "Volumen real")},
  },
  "construction": {
    "title": T("Construction", "Construcción"),
    "data": {
      "construction_type": T("Type", "Tipo"), "has_cover": T("Cover", "Cubierta"),
      "cover_entity": T("Cover entity", "Entidad de la cubierta"),
      "is_covered_by_roof": T("Under a fixed roof or porch", "Bajo techo o porche fijo"),
      "heating_type": T("Heating", "Climatización"), "liner_type": T("Finish", "Revestimiento"),
      "liner_color": T("Colour of the finish", "Color del revestimiento"), "orientation": T("Orientation", "Orientación"),
    },
    "data_description": {
      "cover_entity": T("Only for an automatic cover: closed means covered.", "Solo para cubierta automática: cerrada significa cubierta."),
      "is_covered_by_roof": T("Sun and rain then no longer change the filtration time.", "Así el sol y la lluvia dejan de cambiar el tiempo de filtración."),
    },
  },
  "pump": {
    "title": T("Pump", "Bomba"),
    "description": T("Pick your pump to fill in its figures, or enter them yourself.", "Elige tu bomba para rellenar sus datos, o escríbelos tú."),
    "data": {"pump_model": T("Model", "Modelo")},
  },
  "filtration": {
    "title": T("Filtration", "Filtración"),
    "data": {
      "pump_nominal_flow_rate": T("Pump flow rate", "Caudal de la bomba"),
      "pump_nominal_power": T("Pump power", "Potencia de la bomba"),
      "pump_speed_type": T("Speed", "Velocidad"), "filter_type": T("Filter", "Filtro"),
      "skimmers_count": T("Skimmers", "Skimmers"), "returns_count": T("Returns", "Boquillas de impulsión"),
      "has_autofill_skimmer": T("Has an auto-fill skimmer", "Tiene skimmer de llenado automático"),
      "filter_pressure_normal_min": T("Normal filter pressure, low", "Presión normal del filtro, mínima"),
      "filter_pressure_normal_max": T("Normal filter pressure, high", "Presión normal del filtro, máxima"),
      "backwash_interval_days": T("Backwash or clean every", "Contralavado o limpieza cada"),
    },
    "data_description": {
      "pump_nominal_flow_rate": T("The one figure the daily target cannot do without.", "El único dato sin el que no se puede calcular el objetivo diario."),
      "pump_nominal_power": T("Used to tell a solar surplus from the pump's own draw when there is no power meter on it.", "Sirve para separar el excedente solar del consumo de la bomba cuando no hay medidor en ella."),
    },
  },
  "water": {
    "title": T("Water treatment", "Tratamiento del agua"),
    "data": {
      "chlorination_type": T("Chlorination", "Cloración"), "ph_target": T("pH target", "pH objetivo"),
      "ph_range_min": T("pH, lowest acceptable", "pH mínimo aceptable"), "ph_range_max": T("pH, highest acceptable", "pH máximo aceptable"),
      "has_ph_dosing": T("A pH dosing pump that works only with water flowing", "Bomba dosificadora de pH que solo funciona con circulación"),
      "ph_calibration_interval_days": T("Calibrate the pH probe every", "Calibrar la sonda de pH cada"),
      "free_chlorine_target": T("Free chlorine target", "Cloro libre objetivo"),
      "free_chlorine_range_min": T("Free chlorine, lowest", "Cloro libre mínimo"),
      "free_chlorine_range_max": T("Free chlorine, highest", "Cloro libre máximo"),
      "swimming_months": T("Months the pool is used", "Meses de baño"),
      "winter_product_type": T("Winter product", "Producto de invierno"),
      "winter_product_dose_per_m3": T("Winter product, dose per m³", "Producto de invierno, dosis por m³"),
      "winter_product_interval_days": T("Top up the winter product every", "Reponer el producto de invierno cada"),
      **reading_data,
      "shock_product": T("Shock product", "Producto de choque"),
      "shock_concentration": T("Shock product concentration", "Concentración del producto de choque"),
      "clarifier_dose_per_10m3": T("Clarifier, dose per 10 m³", "Clarificante, dosis por 10 m³"),
      "clarifier_dose_unit": T("Clarifier, unit", "Clarificante, unidad"),
      "flocculant_dose_per_10m3": T("Flocculant, dose per 10 m³", "Floculante, dosis por 10 m³"),
      "flocculant_dose_unit": T("Flocculant, unit", "Floculante, unidad"),
    },
    "data_description": {
      "swimming_months": T("HomePool proposes wintering when they end and opening two weeks before they start.", "HomePool propone invernar cuando terminan y la puesta en marcha dos semanas antes de que empiecen."),
      "winter_product_type": T("What goes in the water while the pool is wintering. HomePool works out the dose and reminds you to top it up.", "Lo que se pone en el agua durante el invernaje. HomePool calcula la dosis y te recuerda reponerlo."),
      "winter_product_dose_per_m3": T("Units per m³ (litres per m³ for a liquid), as on the label. One floater for 50 m³ is 0.02.", "Unidades por m³ (litros por m³ si es líquido), según la etiqueta. Un flotador por cada 50 m³ son 0,02."),
      "winter_product_interval_days": T("Days between top-ups.", "Días entre reposiciones."),
      "has_ph_dosing": T("When the pH is too high, the pump is run for a while so the doser can work.", "Si el pH está alto, la bomba se pone en marcha un rato para que la dosificadora pueda trabajar."),
      "shock_product": T("What you shock green water with. HomePool works out the dose from the pool's volume.", "Con qué haces el choque al agua verde. HomePool calcula la dosis con el volumen de la piscina."),
      "shock_concentration": T("Per cent of chlorine for a granular product, g/L for a liquid one, as on the label. Empty: 65 % calcium hypochlorite, 150 g/L sodium hypochlorite, 56 % dichlor.", "Por ciento de cloro si es granulado, g/L si es líquido, según la etiqueta. Vacío: hipoclorito cálcico al 65 %, hipoclorito sódico a 150 g/L, dicloro al 56 %."),
      "clarifier_dose_per_10m3": T("As on the label. Empty, the dose says to follow the label.", "Según la etiqueta. Vacío, la dosis dice que sigas el envase."),
      "flocculant_dose_per_10m3": T("As on the label. Empty, the dose says to follow the label.", "Según la etiqueta. Vacío, la dosis dice que sigas el envase."),
    },
  },
  "chlorinator_model": {
    "title": T("Salt chlorinator", "Clorador salino"),
    "description": T("Pick your chlorinator to fill in its figures, or enter them yourself.", "Elige tu clorador para rellenar sus datos, o escríbelos tú."),
    "data": {"chlorinator_model": T("Model", "Modelo")},
  },
  "chlorinator": {
    "title": T("Salt chlorinator", "Clorador salino"),
    "data": {
      "chlorinator_nominal_production": T("Production at 100 %", "Producción al 100 %"),
      "chlorinator_production_default": T("Production it is set to", "Producción configurada"),
      "chlorinator_self_regulating": T("Regulates itself (ORP or chlorine probe)", "Se autorregula (sonda ORP o de cloro)"),
      "chlorinator_controllable": T("Its production can be set from Home Assistant", "Su producción se puede ajustar desde Home Assistant"),
      "chlorinator_active_months": T("Months it is used", "Meses en que se usa"),
      "chlorinator_auto_toggle": T("Propose the season change from the calendar", "Proponer el cambio de temporada según el calendario"),
      "chlorinator_min_water_temp": T("Coldest water it may run in", "Agua más fría con la que puede funcionar"),
      "salt_target": T("Salt target", "Sal objetivo"), "salt_range_min": T("Salt, lowest", "Sal mínima"), "salt_range_max": T("Salt, highest", "Sal máxima"),
    },
    "data_description": {
      "chlorinator_active_months": T("The swimming months start from these when you give none, and the chlorinator's season events follow them. Whether the cell works follows the season state: in swimming it works whatever the month, in wintering it does not.", "Los meses de baño parten de estos si no das otros, y los avisos de temporada del clorador los siguen. Si la célula trabaja lo decide el estado de temporada: en baño trabaja sea cual sea el mes, en invernaje no."),
      "chlorinator_auto_toggle": T("When the swimming months end or are about to start, HomePool proposes changing the season state; you confirm it. Otherwise you change it yourself. Either way, finishing the opening checklist while the pool is in the opening state proposes swimming.", "Cuando terminan los meses de baño o están a punto de empezar, HomePool propone cambiar el estado de temporada y tú lo confirmas. Si no, lo cambias tú. En los dos casos, terminar la lista de apertura con la piscina en apertura propone pasar a baño."),
    },
  },
  "connections": {
    "title": T("Your entities", "Tus entidades"),
    "description": T("Only the pump switch is required. Each sensor you add unlocks something; leave the rest empty.",
                     "Solo hace falta el interruptor de la bomba. Cada sensor que añadas activa algo más; deja vacío el resto."),
    "sections": {
      "pump": {"name": T("Pump", "Bomba"), "data": {
          "pump_switch": T("Pump switch", "Interruptor de la bomba"),
          "pump_power_sensor": T("Pump power", "Potencia de la bomba"),
          "pump_energy_sensor": T("Pump energy", "Energía de la bomba"),
          "hands_off_entity": T("Hands-off flag", "Indicador de manos fuera")},
        "data_description": {
          "hands_off_entity": T("While this is on, HomePool never switches the pump, on or off. It keeps counting.", "Mientras esté encendido, HomePool no toca la bomba, ni para encenderla ni para apagarla. Sigue contando.")}},
      "water": {"name": T("Water", "Agua"), "data": {
          "water_temperature_sensor": T("Water temperature", "Temperatura del agua"),
          "air_temperature_sensor": T("Outdoor temperature", "Temperatura exterior"),
          "ph_sensor": T("pH", "pH"), "ph_dosing_entity": T("pH doser asking for flow", "Dosificadora de pH pidiendo circulación"),
          "orp_sensor": T("ORP (redox)", "ORP (redox)"), "salinity_sensor": T("Salinity", "Salinidad"),
          "free_chlorine_sensor": T("Free chlorine", "Cloro libre")},
        "data_description": {
          "air_temperature_sensor": T("Used to estimate the water temperature when there is no probe in the water.", "Se usa para estimar la temperatura del agua cuando no hay sonda en ella.")}},
      "equipment_room": {"name": T("Equipment room", "Caseta de depuración"), "data": {
          "filter_pressure_sensor": T("Filter pressure", "Presión del filtro"),
          "equipment_room_temperature_sensor": T("Room temperature", "Temperatura de la caseta"),
          "equipment_room_humidity_sensor": T("Room humidity", "Humedad de la caseta"),
          "flood_sensor": T("Flood sensor", "Sensor de inundación")}},
      "chlorinator": {"name": T("Salt chlorinator", "Clorador salino"), "data": {
          "chlorinator_switch": T("Chlorinator switch, separate from the pump", "Interruptor del clorador, independiente de la bomba"),
          "chlorinator_production_entity": T("Production setting", "Ajuste de producción")}},
      "solar": {"name": T("Solar", "Solar"), "data": {
          "solar_excess_sensor": T("Grid or surplus power", "Potencia de red o excedente"),
          "solar_excess_sign": T("What that sensor reports", "Qué indica ese sensor"),
          "solar_import_tolerance": T("Import tolerated while running on sun", "Importación tolerada en marcha solar")},
        "data_description": {
          "solar_excess_sensor": T("Enables the two solar modes. A grid meter is best: HomePool adds the pump's own draw back while it runs.", "Activa los dos modos solares. Lo mejor es el contador de red: HomePool le suma el consumo de la bomba mientras funciona."),
          "solar_import_tolerance": T("Short peaks of house consumption up to this much do not stop the pump.", "Los picos breves de consumo de la casa hasta este valor no paran la bomba.")}},
      "weather": {"name": T("Weather", "Meteorología"), "data": {
          "weather_entity": T("Weather forecast", "Previsión meteorológica"),
          "uv_sensor": T("UV index", "Índice UV"),
          "rain_sensor": T("Rain in the last 24 h", "Lluvia en las últimas 24 h")}},
    },
  },
  "control": {
    "title": T("Control", "Control"),
    "data": {
      "timer_slots": T("Timer mode slots", "Franjas del modo temporizador"),
      "manual_override_minutes": T("Respect a hand-switched pump for", "Respetar la bomba encendida o apagada a mano durante"),
      "freeze_protection": T("Run the pump when the water is near freezing", "Encender la bomba si el agua está cerca de congelarse"),
      "freeze_threshold": T("Freezing threshold", "Umbral de helada"),
      "ph_correction_minutes": T("pH correction window", "Ventana de corrección de pH"),
      "ph_correction_max_daily": T("pH correction, most per day", "Corrección de pH, máximo al día"),
      "equipment_room_max_temp": T("Room too hot above", "Caseta demasiado caliente por encima de"),
      "filter_pressure_critical": T("Filter pressure that stops the pump", "Presión del filtro que para la bomba"),
      "energy_price": T("Energy price per kWh", "Precio de la energía por kWh"),
      "energy_price_entity": T("Energy price entity", "Entidad con el precio de la energía"),
      "light_entities": T("Pool lights", "Luces de la piscina"),
      "pool_cleaner_type": T("Pool cleaner", "Limpiafondos"),
      "robot_entity": T("Robot entity", "Entidad del robot"),
    },
    "data_description": {
      "timer_slots": T("For example 08:00-12:00, 18:00-20:00", "Por ejemplo 08:00-12:00, 18:00-20:00"),
      "energy_price_entity": T("Takes precedence over the fixed price.", "Tiene prioridad sobre el precio fijo."),
      "freeze_protection": T("Switches the pump on even in off mode: still water freezes in the pipes, moving water does not. Uses the water temperature, or the air below zero without a water probe.",
                             "Enciende la bomba incluso en modo apagado: el agua quieta se congela en las tuberías, la que circula no. Usa la temperatura del agua o, sin sonda de agua, el aire bajo cero."),
    },
  },
  "notifications": {
    "title": T("Notifications", "Notificaciones"),
    "description": T("HomePool always fires events and keeps alert sensors for your own automations. This is only for a ready-made message.",
                     "HomePool siempre lanza eventos y mantiene sensores de alerta para tus automatizaciones. Esto es solo para un mensaje ya hecho."),
    "data": {
      "enable_builtin_notifications": T("Send notifications", "Enviar notificaciones"),
      "notification_service": T("Notify service", "Servicio de notificación"),
      "notification_severity_min": T("From this severity up (reminders are always sent)", "A partir de esta gravedad (los recordatorios se envían siempre)"),
      "notification_quiet_hours_start": T("Quiet from", "Silencio desde"),
      "notification_quiet_hours_end": T("Quiet until", "Silencio hasta"),
      "critical_ignore_quiet_hours": T("Critical alerts ignore the quiet hours", "Las alertas críticas ignoran el silencio"),
    },
  },
  "tasks": {
    "title": T("Recurring tasks", "Tareas periódicas"),
    "description": T("How often each job comes round, and when you last did it. Only the tasks your pool needs are listed. In winter the filter jobs count hours of pump instead of days.",
                     "Cada cuánto toca cada trabajo y cuándo lo hiciste por última vez. Solo salen las tareas que tu piscina necesita. En invierno los trabajos del filtro cuentan horas de bomba en lugar de días."),
    "data": tasks_data,
    "data_description": {
      "has_ph_probe_outside": T("Turns on the pH calibration reminder when HomePool has no pH sensor. Save, then open this page again to set its interval.",
                                "Activa el recordatorio de calibración del pH cuando HomePool no tiene sensor de pH. Guarda y abre esta página otra vez para fijar su intervalo."),
    },
  },
}

errors = {
  "range_order": T("The lowest value cannot be above the highest.", "El valor mínimo no puede ser mayor que el máximo."),
  "depth_order": T("The deepest depth cannot be less than the shallowest.", "La profundidad máxima no puede ser menor que la mínima."),
  "cover_entity_required": T("An automatic cover needs its entity.", "Una cubierta automática necesita su entidad."),
  "pressure_order": T("The high pressure must be above the low one.", "La presión máxima debe ser mayor que la mínima."),
  "ph_order": T("The target must be inside the acceptable range.", "El objetivo debe estar dentro del rango aceptable."),
  "no_months": T("Pick at least one month.", "Elige al menos un mes."),
  "concentration_range": T("That concentration cannot be right: up to 100 % for a granular product, up to 300 g/L for a liquid one.", "Esa concentración no puede ser: hasta el 100 % si es granulado, hasta 300 g/L si es líquido."),
  "same_switch": T("The chlorinator switch must be a different entity from the pump switch. If the cell is wired with the pump, leave it empty.", "El interruptor del clorador debe ser distinto del de la bomba. Si la célula va conectada con la bomba, déjalo vacío."),
  "bad_slots": T("Write the slots as HH:MM-HH:MM, separated by commas.", "Escribe las franjas como HH:MM-HH:MM, separadas por comas."),
  "date_in_future": T("That date has not happened yet.", "Esa fecha todavía no ha llegado."),
  "service_required": T("Pick a notify service, or switch notifications off.", "Elige un servicio de notificación o desactiva las notificaciones."),
}

menu = {
  "identity": T("Name and location", "Nombre y ubicación"), "shape": T("Shape and size", "Forma y medidas"),
  "construction": T("Construction", "Construcción"), "pump": T("Pump and filter", "Bomba y filtro"),
  "water": T("Water treatment", "Tratamiento del agua"), "chlorinator_model": T("Salt chlorinator", "Clorador salino"),
  "connections": T("Entities", "Entidades"), "control": T("Control", "Control"),
  "notifications": T("Notifications", "Notificaciones"), "tasks": T("Recurring tasks", "Tareas periódicas"),
}

selectors = {
  "shape": {"square": T("Square", "Cuadrada"), "rectangular": T("Rectangular", "Rectangular"), "oval": T("Oval", "Ovalada"),
            "round": T("Round", "Redonda"), "kidney": T("Kidney", "Riñón"), "l_shape": T("L-shaped", "En L")},
  "layout_orientation": {"top_left": T("Top left", "Arriba a la izquierda"), "top_right": T("Top right", "Arriba a la derecha"),
            "bottom_left": T("Bottom left", "Abajo a la izquierda"), "bottom_right": T("Bottom right", "Abajo a la derecha"),
            "top": T("Top", "Arriba"), "bottom": T("Bottom", "Abajo"), "left": T("Left", "Izquierda"), "right": T("Right", "Derecha")},
  "construction_type": {"built_in": T("Built in", "De obra"), "prefab": T("Prefabricated", "Prefabricada"), "above_ground": T("Above ground", "Desmontable")},
  "has_cover": {"none": T("None", "Ninguna"), "manual": T("Manual", "Manual"), "automatic": T("Automatic", "Automática")},
  "heating_type": {"none": T("None", "Ninguna"), "heat_pump": T("Heat pump", "Bomba de calor"), "heat_exchanger": T("Heat exchanger", "Intercambiador"),
            "solar_thermal": T("Solar thermal", "Solar térmica"), "electric": T("Electric", "Eléctrica"), "other": T("Other", "Otra")},
  "liner_type": {"not_specified": T("Not specified", "Sin especificar"), "tile": T("Tile", "Gresite"), "polyester": T("Polyester", "Poliéster"),
            "liner": T("Liner", "Liner"), "painted_concrete": T("Painted concrete", "Hormigón pintado"), "natural_stone": T("Natural stone", "Piedra natural"),
            "fiberglass": T("Fibreglass", "Fibra de vidrio")},
  "liner_color": {"white": T("White", "Blanco"), "light_blue": T("Light blue", "Azul claro"), "blue": T("Blue", "Azul"), "dark_blue": T("Dark blue", "Azul oscuro"),
            "green": T("Green", "Verde"), "sand": T("Sand", "Arena"), "grey": T("Grey", "Gris"), "black": T("Black", "Negro")},
  "orientation": {"not_specified": T("Not specified", "Sin especificar"), "north": T("North", "Norte"), "northeast": T("Northeast", "Noreste"),
            "east": T("East", "Este"), "southeast": T("Southeast", "Sureste"), "south": T("South", "Sur"), "southwest": T("Southwest", "Suroeste"),
            "west": T("West", "Oeste"), "northwest": T("Northwest", "Noroeste")},
  "catalog_model": {"custom": T("Not listed — enter the figures myself", "No está en la lista: escribo yo los datos")},
  "pump_speed_type": {"fixed": T("Single speed", "Velocidad fija"), "variable": T("Variable speed", "Velocidad variable")},
  "filter_type": {"sand": T("Sand", "Arena"), "glass": T("Glass", "Vidrio"), "cartridge": T("Cartridge", "Cartucho"),
            "diatomaceous_earth": T("Diatomaceous earth", "Diatomeas"), "other": T("Other", "Otro")},
  "chlorination_type": {"salt": T("Salt chlorinator", "Clorador salino"), "tablets": T("Tablets", "Pastillas"),
            "liquid": T("Liquid chlorine", "Cloro líquido"), "other": T("Other", "Otro")},
  "winter_product_type": {"none": T("None", "Ninguno"), "floater": T("Floater", "Flotador"),
            "liquid": T("Liquid", "Líquido"), "tablets": T("Tablets", "Pastillas")},
  "shock_product": {"calcium_hypochlorite": T("Calcium hypochlorite (granular)", "Hipoclorito cálcico (granulado)"),
            "sodium_hypochlorite": T("Sodium hypochlorite (liquid)", "Hipoclorito sódico (líquido)"),
            "dichlor": T("Dichlor (granular, raises the cyanuric acid)", "Dicloro (granulado, sube el ácido cianúrico)")},
  "treatment_type": {"shock": T("Shock (green water)", "Choque (agua verde)"),
            "clarifier": T("Clarifier (cloudy water)", "Clarificante (agua turbia)"),
            "flocculant": T("Flocculant (cloudy water)", "Floculante (agua turbia)")},
  "shock_severity": {"light": T("Light green", "Verde claro"), "green": T("Green", "Verde"),
            "dark": T("Dark green or black", "Verde oscuro o negro")},
  "month": {str(i): T(en, es) for i, (en, es) in enumerate([
      ("January","Enero"),("February","Febrero"),("March","Marzo"),("April","Abril"),("May","Mayo"),("June","Junio"),
      ("July","Julio"),("August","Agosto"),("September","Septiembre"),("October","Octubre"),("November","Noviembre"),("December","Diciembre")], start=1)},
  "solar_excess_sign": {"export_positive": T("Grid meter: export positive, import negative", "Contador de red: exportación positiva, importación negativa"),
            "import_positive": T("Grid meter: import positive, export negative", "Contador de red: importación positiva, exportación negativa"),
            "surplus": T("Surplus (production minus consumption)", "Excedente (producción menos consumo)")},
  "pool_cleaner_type": {"none": T("None", "Ninguno"), "cable_electric": T("Robot with cable", "Robot con cable"),
            "battery": T("Robot with battery", "Robot con batería"), "hydraulic": T("Hydraulic", "Hidráulico")},
  "task": {k: v for k, v in task_names.items()},
  "reading_kind": reading_names,
  "season_state": season_states,
  "checklist": {"closing": T("Closing", "Cierre"), "opening": T("Opening", "Apertura"), "treatment": T("Treatment", "Tratamiento")},
  "severity": {"info": T("Information", "Información"), "warning": T("Warning", "Aviso"), "critical": T("Critical", "Crítico")},
  "action_type": {"backwash": T("Backwash", "Contralavado"), "filter_cleaned": T("Filter cleaned", "Filtro limpiado"),
            "salt_added": T("Salt added", "Sal añadida"), "ph_calibrated": T("pH probe calibrated", "Sonda de pH calibrada"),
            "chlorine_added": T("Chlorine added", "Cloro añadido"), "ph_adjusted": T("pH adjusted by hand", "pH ajustado a mano"),
            "water_added": T("Water added", "Agua añadida"), "cell_cleaned": T("Cell cleaned", "Célula limpiada"),
            "winter_product_added": T("Winter product added", "Producto de invierno repuesto"),
            "water_tested": T("Water tested", "Agua medida"),
            "skimmer_baskets_emptied": T("Skimmer baskets emptied", "Cestos del skimmer vaciados"),
            "filter_media_checked": T("Filter media checked", "Arena o vidrio revisado"), "other": T("Other", "Otra")},
}

control_states = {"hands_off": T("Hands off", "Manos fuera"), "maintenance_lock": T("Maintenance lock", "Bloqueo de mantenimiento"),
  "safety": T("Safety shutoff", "Parada de seguridad"), "freeze_protection": T("Freeze protection", "Protección antiheladas"),
  "ph_correction": T("pH correction", "Corrección de pH"), "manual_cycle": T("Manual cycle", "Ciclo manual"),
  "manual_override": T("Switched by hand", "Accionada a mano"), "mode": T("Operation mode", "Modo de funcionamiento"),
  "unavailable": T("Pump unavailable", "Bomba no disponible"),
  "winter_passive": T("Passive wintering", "Invernaje pasivo"),
  "treatment": T("Water treatment", "Tratamiento del agua")}

entity = {
 "sensor": {
  "daily_filtration_target": T("Daily filtration target", "Objetivo de filtración diario"),
  "target_filtration_component": T("Target, filtration part", "Objetivo, parte de filtración"),
  "target_chlorine_component": T("Target, chlorine part", "Objetivo, parte de cloración"),
  "filtration_elapsed_today": T("Filtration today", "Filtración hoy"),
  "filtration_remaining_today": T("Filtration left today", "Filtración pendiente hoy"),
  "cycle_duration": T("One turnover", "Una renovación completa"),
  "pool_volume": T("Volume", "Volumen"),
  "pump_control": (T("Pump control", "Control de la bomba"), control_states),
  "chlorine_production_elapsed_today": T("Chlorine production today", "Producción de cloro hoy"),
  "chlorine_production_remaining_today": T("Chlorine production left today", "Producción de cloro pendiente hoy"),
  "recommended_chlorinator_production": T("Recommended chlorinator production", "Producción recomendada del clorador"),
  "chlorination_mode": (T("Chlorination", "Cloración"), {"salt": T("Salt", "Salina"), "tablets": T("Tablets", "Pastillas"), "off": T("Off", "Apagada"),
        "winter_product": T("Winter product", "Producto de invierno")}),
  "days_since_last_backwash": T("Days since the filter was cleaned", "Días desde la limpieza del filtro"),
  "days_since_ph_calibration": T("Days since pH calibration", "Días desde la calibración del pH"),
  "next_manual_task": (T("Next manual task", "Próxima tarea manual"), {"none": T("None", "Ninguna"), "backwash": T("Backwash", "Contralavado"),
        "filter_cleaning": T("Clean the filter", "Limpiar el filtro"), "ph_calibration": T("Calibrate the pH probe", "Calibrar la sonda de pH"),
        "winter_product": T("Top up the winter product", "Reponer el producto de invierno"),
        "water_test": T("Test the water", "Medir el agua"),
        "skimmer_baskets": T("Empty the baskets", "Vaciar los cestos"),
        "cell_cleaning": T("Clean the cell", "Limpiar la célula"),
        "filter_media_check": T("Check the filter media", "Revisar la arena o el vidrio")}),
  "overall_status": (T("Status", "Estado"), {"ok": T("OK", "Correcto"), "attention": T("Needs attention", "Requiere atención"),
        "action_required": T("Action required", "Acción necesaria")}),
  "water_treatment": (T("Water treatment", "Tratamiento del agua"), {"none": T("None", "Ninguno"),
        "shock": T("Shock", "Choque"), "clarifier": T("Clarifier", "Clarificante"), "flocculant": T("Flocculant", "Floculante")}),
  "ph_trend": (T("pH trend", "Tendencia del pH"), {"rising": T("Rising", "Subiendo"), "stable": T("Stable", "Estable"), "falling": T("Falling", "Bajando")}),
  "salinity": T("Salinity", "Salinidad"),
  "free_chlorine": T("Free chlorine", "Cloro libre"),
  "ph_manual": T("Manual pH", "pH manual"),
  "combined_chlorine": T("Combined chlorine", "Cloro combinado"),
  "total_alkalinity": T("Total alkalinity", "Alcalinidad total"),
  "calcium_hardness": T("Calcium hardness", "Dureza cálcica"),
  "cyanuric_acid": T("Cyanuric acid", "Ácido cianúrico"),
  "pump_energy_today": T("Pump energy today", "Energía de la bomba hoy"),
  "pump_cost_today": T("Pump cost today", "Coste de la bomba hoy"),
 },
 "binary_sensor": {
  "daily_target_reached": T("Daily target reached", "Objetivo diario cumplido"),
  "pump_running": T("Pump running", "Bomba en marcha"),
  "chlorine_target_reached": T("Chlorine target reached", "Objetivo de cloro cumplido"),
  "backwash_needed": T("Filter needs cleaning", "El filtro necesita limpieza"),
  "ph_out_of_range": T("pH out of range", "pH fuera de rango"),
  "ph_correction_active": T("pH correction", "Corrección de pH"),
  "critical_water_temperature": T("Critical water temperature", "Temperatura del agua crítica"),
  "pump_anomaly": T("Pump power anomaly", "Consumo anómalo de la bomba"),
  "equipment_room_flood": T("Equipment room flood", "Inundación en la caseta"),
  "equipment_room_overheat": T("Equipment room overheat", "Caseta sobrecalentada"),
  "manual_action_pending": T("Manual task due", "Tarea manual pendiente"),
  "safety_shutoff_active": T("Safety shutoff", "Parada de seguridad"),
  "freeze_protection_active": T("Freeze protection", "Protección antiheladas"),
  "chlorinator_in_season": T("Chlorinator in season", "Clorador en temporada"),
  "swimming_not_advised": T("Swimming not advised", "Baño no recomendado"),
 },
 "switch": {
  "pump": T("Pump", "Bomba"),
  "maintenance_lock": T("Maintenance lock", "Bloqueo de mantenimiento"),
  "salt_chlorinator_enabled": T("Chlorinator in use", "Clorador en uso"),
 },
 "select": {
  "operation_mode": (T("Operation mode", "Modo de funcionamiento"), {"off": T("Off", "Apagado"), "timer": T("Timer", "Temporizador"),
        "smart": T("Smart", "Inteligente"), "solar": T("Solar", "Solar"), "smart_solar": T("Smart + solar", "Inteligente + solar")}),
  "season_state": (T("Season state", "Estado de temporada"), season_states),
 },
 "number": {
  "user_multiplier": T("Filtration multiplier", "Multiplicador de filtración"),
  "ph_target": T("pH target", "pH objetivo"),
  "chlorinator_production": T("Chlorinator production", "Producción del clorador"),
  "solar_excess_threshold": T("Solar surplus threshold", "Umbral de excedente solar"),
 },
 "button": {
  "start_cycle": T("Start cycle", "Iniciar ciclo"),
  "stop_cycle": T("Stop cycle", "Detener ciclo"),
  "mark_backwash_done": T("Backwash done", "Contralavado hecho"),
  "mark_filter_cleaned": T("Filter cleaned", "Filtro limpiado"),
  "mark_salt_added": T("Salt added", "Sal añadida"),
  "mark_ph_calibrated": T("pH probe calibrated", "Sonda de pH calibrada"),
  "mark_winter_product_added": T("Winter product added", "Producto de invierno repuesto"),
  "mark_water_tested": T("Water tested", "Agua medida"),
  "mark_skimmer_baskets_emptied": T("Skimmer baskets emptied", "Cestos del skimmer vaciados"),
  "start_shock": T("Start a shock", "Empezar un choque"),
  "start_clarifier": T("Start a clarifier", "Empezar un clarificante"),
  "start_flocculant": T("Start a flocculant", "Empezar un floculante"),
  "advance_treatment": T("Next treatment phase (vacuuming done)", "Siguiente fase del tratamiento (aspirado terminado)"),
  "end_treatment": T("End the treatment", "Terminar el tratamiento"),
  "recalculate_target": T("Recalculate target", "Recalcular objetivo"),
 },
}

# The layouts' English names live in data/layouts.yaml; Spanish here, per shape.
import yaml
LAYOUT_ES = {
  "square": {"plain": "Sin elementos interiores", "corner_steps": "Escalera de obra en una esquina",
             "full_side_steps": "Escalera de obra a lo ancho de un lado"},
  "rectangular": {"plain": "Sin elementos interiores", "corner_steps": "Escalera de obra en una esquina",
             "roman_steps_short_side": "Escalera romana en el lado corto", "roman_steps_long_side": "Escalera romana en el lado largo",
             "full_side_island": "Isla a lo ancho del lado corto", "full_side_island_with_steps": "Isla con escalera en el lado corto",
             "beach_entry": "Entrada de playa", "small_ladder_only": "Solo escalerilla metálica (sin elementos de obra)"},
  "oval": {"plain": "Sin elementos interiores", "roman_steps": "Escalera romana en un extremo", "beach_entry": "Entrada de playa"},
  "round": {"plain": "Sin elementos interiores", "steps_segment": "Escalera de obra en un tramo"},
  "kidney": {"plain": "Sin elementos interiores", "steps_concave": "Escalera en el lado cóncavo",
             "beach_entry": "Entrada de playa en la zona poco profunda"},
  "l_shape": {"plain": "Sin elementos interiores", "corner_steps": "Escalera de obra en la unión", "roman_steps": "Escalera romana en un brazo"},
}
_layouts = yaml.safe_load((ROOT / "data" / "layouts.yaml").read_text(encoding="utf-8"))
for _shape, _variants in _layouts.items():
  if not isinstance(_variants, list):
    continue
  selectors[f"layout_variant_{_shape}"] = {v["id"]: T(v["name"], LAYOUT_ES[_shape][v["id"]]) for v in _variants}

services = {
  "start_cycle": (T("Start cycle", "Iniciar ciclo"), T("Runs the pump for a while, above the operation mode. Lock and safety still win. Refused while a water treatment runs.", "Pone la bomba en marcha un rato, por encima del modo. El bloqueo y la seguridad siguen mandando. No se admite con un tratamiento del agua en marcha."),
      {"duration": (T("Duration", "Duración"), T("Minutes. One full turnover if left out.", "Minutos. Una renovación completa si se omite."))}),
  "stop_cycle": (T("Stop cycle", "Detener ciclo"), T("Stops a manual cycle and holds the pump off for the override time. Refused while a water treatment runs.", "Detiene un ciclo manual y mantiene la bomba apagada durante el tiempo de respeto. No se admite con un tratamiento del agua en marcha."), {}),
  "record_manual_action": (T("Record manual action", "Registrar acción manual"), T("Logs a job done by hand, and resets its reminder where there is one.", "Anota un trabajo hecho a mano y reinicia su recordatorio, si lo tiene."),
      {"action_type": (T("Action", "Acción"), T("What was done.", "Qué se ha hecho.")),
       "value": (T("Value", "Valor"), T("An amount, if it has one.", "Una cantidad, si la tiene.")),
       "notes": (T("Notes", "Notas"), T("Anything worth remembering.", "Lo que valga la pena recordar."))}),
  "complete_task": (T("Complete task", "Completar tarea"), T("Marks a recurring task as done, today or on a past date, and counts its next one from then.", "Marca una tarea periódica como hecha, hoy o en una fecha pasada, y cuenta la siguiente desde entonces."),
      {"task": (T("Task", "Tarea"), T("Which one was done.", "Cuál se ha hecho.")),
       "date": (T("Date", "Fecha"), T("The day it was done. Today if left out.", "El día en que se hizo. Hoy si se omite."))}),
  "record_salt_level": (T("Record salt level", "Registrar nivel de sal"), T("A salt reading taken by hand. Used until a newer one, or a salinity sensor.", "Una lectura de sal tomada a mano. Se usa hasta que haya otra o un sensor de salinidad."),
      {"value": (T("Salt", "Sal"), T("Grams per litre.", "Gramos por litro."))}),
  "record_free_chlorine": (T("Record free chlorine", "Registrar cloro libre"), T("A free chlorine reading taken by hand.", "Una lectura de cloro libre tomada a mano."),
      {"value": (T("Free chlorine", "Cloro libre"), T("Parts per million.", "Partes por millón."))}),
  "record_reading": (T("Record reading", "Registrar lectura"), T("A chemistry reading taken by hand. Measuring the pH or the free chlorine also counts as the water test.", "Una lectura química tomada a mano. Medir el pH o el cloro libre cuenta también como la medición del agua."),
      {"kind": (T("Reading", "Lectura"), T("What was measured.", "Qué se ha medido.")),
       "value": (T("Value", "Valor"), T("pH has no unit, salt is in g/L and the rest in mg/L.", "El pH no tiene unidad, la sal va en g/L y el resto en mg/L."))}),
  "recalculate_schedule": (T("Recalculate target", "Recalcular objetivo"), T("Works out today's target again now. Unlike the hourly update, it may also lower it.", "Vuelve a calcular el objetivo de hoy ahora. A diferencia de la actualización horaria, también puede bajarlo."), {}),
  "force_ph_correction_window": (T("Force pH correction window", "Forzar ventana de corrección de pH"), T("Runs the pump so the pH doser can work.", "Pone la bomba en marcha para que la dosificadora de pH pueda trabajar."),
      {"duration": (T("Duration", "Duración"), T("Minutes. The configured window if left out.", "Minutos. La ventana configurada si se omite."))}),
  "set_season_state": (T("Set season state", "Cambiar estado de temporada"), T("Confirms the pool's season state. Wintering turns the chlorinator off and swimming turns it on; passive wintering keeps the pump off.", "Confirma el estado de temporada de la piscina. Invernar apaga el clorador y el baño lo enciende; el invernaje pasivo mantiene la bomba parada."),
      {"state": (T("State", "Estado"), T("The season state to set.", "El estado de temporada que poner."))}),
  "dismiss_season_proposal": (T("Dismiss season proposal", "Descartar propuesta de temporada"), T("Stops reminding about the season change the calendar proposed, until it proposes another.", "Deja de recordar el cambio de temporada propuesto por el calendario, hasta que proponga otro."), {}),
  "complete_step": (T("Complete step", "Completar paso"), T("Ticks a step of an open checklist, by its id (for example closing.backwash), and marks the matching recurring task as done.", "Marca un paso de una lista abierta, por su id (por ejemplo closing.backwash), y marca como hecha la tarea periódica que le corresponda."),
      {"step": (T("Step", "Paso"), T("The step id: the list, a dot and the step.", "El id del paso: la lista, un punto y el paso."))}),
  "dismiss_checklist": (T("Dismiss checklist", "Descartar lista"), T("Closes a checklist without finishing it.", "Cierra una lista sin terminarla."),
      {"checklist": (T("Checklist", "Lista"), T("Which list to close.", "Qué lista cerrar."))}),
  "start_treatment": (T("Start water treatment", "Empezar tratamiento del agua"), T("Starts a shock, a clarifier or a flocculant. The pump follows it above pH, manual cycles and the mode; safety and freeze protection still win.", "Empieza un choque, un clarificante o un floculante. La bomba lo sigue por encima del pH, del ciclo manual y del modo; la seguridad y la antiheladas siguen mandando."),
      {"type": (T("Treatment", "Tratamiento"), T("Shock for green water, clarifier or flocculant for cloudy water.", "Choque para el agua verde, clarificante o floculante para el agua turbia.")),
       "severity": (T("How green", "Cuánto de verde"), T("For a shock: how much the free chlorine is raised (10, 15 or 20 mg/L).", "Para un choque: cuánto se sube el cloro libre (10, 15 o 20 mg/L).")),
       "hours": (T("Hours", "Horas"), T("Hours of filtering, or of settling for a flocculant. The default if left out: 24 h shock, 48 h clarifier, 12 h settling.", "Horas de filtrado, o de reposo en el floculante. Si se omite, las de siempre: choque 24 h, clarificante 48 h, reposo 12 h."))}),
  "advance_treatment": (T("Next treatment phase", "Siguiente fase del tratamiento"), T("Moves the treatment to its next phase now. For a flocculant that is vacuuming, it means the vacuuming is done.", "Pasa el tratamiento a su fase siguiente ahora. En un floculante que está aspirando, quiere decir que el aspirado ha terminado."), {}),
  "end_treatment": (T("End water treatment", "Terminar tratamiento del agua"), T("Ends the treatment now. The filter is left due a backwash, unless one was recorded during the treatment.", "Termina el tratamiento ahora. El filtro queda pendiente de contralavado, salvo que se haya hecho uno durante el tratamiento."), {}),
  "reset_daily_counters": (T("Reset today's counters", "Reiniciar contadores de hoy"), T("Starts today's filtration count from zero.", "Vuelve a poner a cero la filtración de hoy."), {}),
}

exceptions = {"invalid_reading": T("{value} is not a possible {kind} reading.", "{value} no es una lectura posible de {kind}."),
  "no_pool_targeted": T("That target matches no HomePool pool.", "Ese destino no corresponde a ninguna piscina de HomePool."),
  "date_in_future": T("That date has not happened yet.", "Esa fecha todavía no ha llegado."),
  "task_not_in_pool": T("{pool} has no {task} task.", "{pool} no tiene la tarea {task}."),
  "step_not_open": T("{pool} has no open step {step}.", "{pool} no tiene abierto el paso {step}."),
  "cycle_in_winter_passive": T("The pump does not start in passive wintering. Change the season state first.", "La bomba no arranca en el invernaje pasivo. Cambia antes el estado de temporada."),
  "treatment_not_allowed": T("{pool} cannot start a treatment now: it is in passive wintering, or another treatment is running.", "{pool} no puede empezar un tratamiento ahora: está en invernaje pasivo o ya hay otro en marcha."),
  "pump_in_owner_hands": T("{pool} is vacuuming: the pump is yours to run at its own switch. Press \"vacuuming done\" first to hand it back to HomePool.", "{pool} está aspirando: la bomba la manejas tú con su propio interruptor. Pulsa antes «aspirado terminado» para devolvérsela a HomePool."),
  "pump_in_treatment": T("{pool} is running a water treatment, which decides the pump until it ends. Press \"End the treatment\" first to hand the pump back.", "{pool} está con un tratamiento del agua, que decide la bomba hasta que termina. Pulsa antes «Terminar el tratamiento» para recuperarla."),
  "no_treatment": T("{pool} has no treatment running.", "{pool} no tiene ningún tratamiento en marcha.")}

def build(i):
    pick = lambda t: t[i]
    def walk(obj):
        if isinstance(obj, tuple): return pick(obj)
        return {k: walk(v) for k, v in obj.items()}
    cfg_steps = {}
    opt_steps = {}
    for step, body in steps_fields.items():
        s = {}
        for k in ("title", "description"):
            if k in body: s[k] = pick(body[k])
        if "data" in body: s["data"] = walk(body["data"])
        if "data_description" in body: s["data_description"] = walk(body["data_description"])
        if "sections" in body:
            s["sections"] = {}
            for sk, sv in body["sections"].items():
                sec = {"name": pick(sv["name"]), "data": walk(sv["data"])}
                if "data_description" in sv: sec["data_description"] = walk(sv["data_description"])
                s["sections"][sk] = sec
        cfg_steps[step] = s
        opt_steps[step] = s
    opt_steps["init"] = {"title": pick(T("Change the pool", "Cambiar la piscina")),
                         "description": pick(T("Pick what to change.", "Elige qué cambiar.")),
                         "menu_options": walk(menu)}
    ent = {}
    for platform, items in entity.items():
        ent[platform] = {}
        for key, val in items.items():
            if isinstance(val, tuple) and isinstance(val[1], dict):
                ent[platform][key] = {"name": pick(val[0]), "state": walk(val[1])}
            else:
                ent[platform][key] = {"name": pick(val)}
    svc = {}
    for name, (title, desc, fields) in services.items():
        svc[name] = {"name": pick(title), "description": pick(desc),
                     "fields": {f: {"name": pick(a), "description": pick(b)} for f, (a, b) in fields.items()}}
    return {
      "config": {
        "step": cfg_steps,
        "error": walk(errors),
        "abort": {"already_configured": pick(T("This pool is already set up.", "Esta piscina ya está configurada."))},
      },
      "options": {"step": opt_steps, "error": walk(errors)},
      "selector": {k: {"options": walk(v)} for k, v in selectors.items()},
      "entity": ent,
      "services": svc,
      "exceptions": {k: {"message": pick(v)} for k, v in exceptions.items()},
    }

en = build(0); es = build(1)
dump = lambda d: json.dumps(d, ensure_ascii=False, indent=2) + "\n"
(ROOT / "strings.json").write_text(dump(en), encoding="utf-8")
(ROOT / "translations").mkdir(exist_ok=True)
(ROOT / "translations" / "en.json").write_text(dump(en), encoding="utf-8")
(ROOT / "translations" / "es.json").write_text(dump(es), encoding="utf-8")
print("written", len(dump(en)))
