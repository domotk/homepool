# HomePool — Documento de Diseño v1

> Integración de Home Assistant para la gestión integral de piscinas.
> Este documento consolida las decisiones de diseño tomadas para la v1.
> Fecha: 16 de abril de 2026. **Revisión 3.**

---

## 1. Visión y posicionamiento

HomePool es una integración de Home Assistant tipo **hub/meta-integración** que modela el concepto "piscina" como entidad de primera clase. No representa un dispositivo concreto: orquesta entidades de HA ya existentes (switches, sensores, cámaras) bajo un modelo coherente y añade inteligencia encima.

**Principios rectores:**

- **Agnóstica al hardware.** Funciona con Shelly, Sonoff, Zigbee, ESPHome, o cualquier otro origen, porque consume entidades de HA, no drivers.
- **Capacidades progresivas.** El valor que aporta escala con los sensores que el usuario conecta. Funciona con lo mínimo y se enriquece gradualmente.
- **Parte visual como diferenciador.** Incluye custom card con dibujo SVG dinámico y animado de la piscina y la sala de máquinas.
- **Lógica aislada del framework.** El cálculo del tiempo de filtrado y otros algoritmos viven en módulos Python puros, independientes de HA, para facilitar testing e iteración.
- **Contribución comunitaria.** Catálogos externos (hardware y layouts de piscina) se mantienen como archivos YAML que aceptan PRs de la comunidad.
- **Desacoplamiento de notificaciones.** La integración expone sensores y eventos; las automatizaciones de notificación son responsabilidad del usuario o de un módulo opcional integrado.

**Posicionamiento:** no existe actualmente en HACS una integración genérica y completa para piscinas. HomePool busca cubrir ese hueco con calidad de producto.

---

## 2. Arquitectura general del proyecto

Aunque este documento se centra en la integración de piscina, HomePool se enmarca en un proyecto más amplio de automatización del hogar con las siguientes capas conceptuales:

1. **Dispositivos e integraciones de HA.** Todo lo físico (relés, válvulas, cámaras, sondas). Incluye HomePool y otras integraciones similares previstas para jardín, seguridad, confort, etc.
2. **Datos y contexto.** Estado persistente que no es instantáneo de un sensor: inventarios, historiales, calendarios de tareas.
3. **Agentes especializados (conceptuales).** Lógica de dominio por área funcional.
4. **Coordinador conversacional y canales.** Un LLM conversacional que usa HA como herramienta principal.

**Criterio de separación Home Assistant vs. fuera:** lo que gestiona el estado físico de la casa (piscina, jardín, clima, seguridad, energía) vive como integración de HA. Lo que gestiona información y procesos familiares que usan la casa pero no la controlan (compras, menús, pagos) vive fuera como servicios independientes.

---

## 3. Modelo de dominio de "Piscina"

### 3.1 Identidad y geometría

| Campo | Tipo | Notas |
|---|---|---|
| `name` | texto | Nombre descriptivo, usado como prefijo de entity_ids. |
| `shape` | enum | `square`, `rectangular`, `oval`, `round`, `kidney`, `l_shape`. |
| `dimensions` | según forma | Ver tabla de formas abajo. |
| `depth_min` | number (m) | Profundidad mínima. Si es uniforme, igual a `depth_max`. |
| `depth_max` | number (m) | Profundidad máxima. |
| `layout_variant` | enum | Id de layout del catálogo, filtrado por `shape`. Por defecto `plain`. |
| `layout_orientation` | enum | Solo si la variante lo requiere. Valores dependen del tipo. |
| `volume_override` | number (m³) | Si el usuario conoce el volumen exacto. |

**Dimensiones por forma:**

- `square`: `side` (m)
- `rectangular`: `length`, `width` (m)
- `oval`: `length` (eje mayor), `width` (eje menor) (m)
- `round`: `diameter` (m)
- `kidney`: `length`, `width` (m) — volumen calculado con factor de corrección ~0.85
- `l_shape`: `length_1`, `width_1`, `length_2`, `width_2` (m) — volumen como suma de dos rectángulos

**Cálculo de volumen:**

1. Calcular volumen base a partir de la geometría y profundidades.
2. Aplicar `volume_adjustment` del `layout_variant` seleccionado.
3. Si `volume_override` está presente, se usa ese valor directamente.

Pantalla intermedia de confirmación tras el paso Geometry mostrando el volumen resultante.

### 3.2 Layouts (elementos interiores predefinidos)

Los elementos interiores de la piscina (escaleras de obra, islas, entradas tipo playa) se modelan mediante un **catálogo de layouts predefinidos**. El usuario selecciona el layout que más se parece a su piscina entre los disponibles para su forma.

**Archivo del catálogo:** `custom_components/homepool/data/layouts.yaml`

**Estructura:**

```yaml
<shape>:
  - id: <identificador>
    name: "<nombre descriptivo>"
    requires_orientation: false | corner | short_side | long_side | any_side
    volume_adjustment: <fracción 0.0-1.0>
    svg_template: "<archivo svg precocinado>"  # opcional
```

**Valores de `requires_orientation`:**

- `false` → no necesita orientación.
- `corner` → 4 opciones: `top_left`, `top_right`, `bottom_left`, `bottom_right`.
- `short_side` → 2 opciones: `top`, `bottom`.
- `long_side` → 2 opciones: `left`, `right`.
- `any_side` → 4 opciones: `top`, `right`, `bottom`, `left`.

**Catálogo inicial mínimo (v1):** 5-8 variantes por forma. Contribuible vía PR.

### 3.3 Construcción y entorno

| Campo | Tipo | Notas |
|---|---|---|
| `construction_type` | enum | `built_in`, `prefab`, `above_ground`. |
| `has_cover` | enum | `none`, `manual`, `automatic`. |
| `cover_entity` | entity (`cover`) | Opcional, solo si `automatic`. |
| `has_heating` | boolean | Si tiene climatización. |
| `heating_type` | enum | `heat_pump`, `heat_exchanger`, `solar_thermal`, `electric`, `other`. |
| `heating_entity` | entity | **v1: solo se guarda.** Reservado para v2. |
| `is_covered_by_roof` | boolean | Piscina bajo techo/porche fijo. |
| `orientation` | enum | `north`...`northwest`, `not_specified`. Opcional. |
| `liner_type` | enum | `tile`, `polyester`, `liner`, `painted_concrete`, `natural_stone`, `fiberglass`, `not_specified`. |
| `liner_color` | enum | `white`, `light_blue`, `blue`, `dark_blue`, `green`, `sand`, `grey`, `black`. |

### 3.4 Sistema de filtrado

| Campo | Tipo | Notas |
|---|---|---|
| `pump_speed_type` | enum | `fixed`, `variable`. En v1 ambas tratadas igual. |
| `pump_nominal_flow_rate` | number (m³/h) | **Crítico** para el cálculo del target. |
| `pump_nominal_power` | number (W) | Opcional, para estimación energética. |
| `skimmers_count` | number (0-8) | Por defecto 1. |
| `has_autofill_skimmer` | boolean | Por defecto `false`. |
| `returns_count` | number (0-12) | Por defecto 2. |
| `filter_type` | enum | `sand`, `cartridge`, `diatomaceous_earth`, `glass`, `other`. |
| `filter_pressure_normal_min` | number (bar) | Por defecto 0.6. |
| `filter_pressure_normal_max` | number (bar) | Por defecto 1.2. |

**Catálogo opcional de hardware.** Posicionamiento automático de skimmers, retornos y autofill en v1.

### 3.5 Tratamiento del agua

| Campo | Tipo | Notas |
|---|---|---|
| `chlorination_type` | enum | `salt`, `tablets`, `liquid`, `other`. |
| `ph_target` | number | Por defecto 7.4. |
| `ph_range_min` | number | Por defecto 7.2. |
| `ph_range_max` | number | Por defecto 7.6. |
| `free_chlorine_target` | number (ppm) | Opcional, por defecto 1.5. |
| `free_chlorine_range_min` / `_max` | number (ppm) | Por defecto 1.0 / 3.0. |

**Campos adicionales solo si `chlorination_type == salt`:**

| Campo | Tipo | Notas |
|---|---|---|
| `salt_target` | number (g/L) | Por defecto 4.0. |
| `salt_range_min` / `_max` | number (g/L) | Por defecto 3.0 / 5.5. |
| `chlorinator_nominal_production` | number (g/h) | Producción nominal al 100%. Del catálogo o manual. |
| `chlorinator_production_default` | number (%) | Porcentaje de producción configurado. Por defecto 50. |
| `chlorinator_controllable` | boolean | ¿Controlable desde HA? |
| `chlorinator_self_regulating` | boolean | ¿Tiene sonda ORP/cloro integrada y se autorregula? Pre-rellenado por catálogo si aplica. |
| `chlorinator_active_months` | multi-select (meses) | Meses en que el clorador está activo. **Por defecto Junio-Septiembre** en hemisferio norte. |
| `chlorinator_auto_toggle` | boolean | Si true, HomePool apaga/enciende el clorador según calendario. Si false, solo avisa. |

### 3.6 Iluminación

N grupos de luces (0, 1 o varios). Cada grupo:

| Campo | Tipo | Notas |
|---|---|---|
| `name` | texto | Nombre descriptivo del grupo. |
| `entities` | lista de entities (`switch` + `light`) | Entidades del grupo. |
| `location` | enum | `underwater`, `perimeter`. |
| `count` | number | Focos físicos. Por defecto = nº de entidades. |

Color inferido automáticamente para `light`, blanco neutro para `switch`. Posicionamiento automático en v1.

### 3.7 Elementos auxiliares

| Campo | Tipo | Notas |
|---|---|---|
| `pool_cleaner_type` | enum | `none`, `cable_electric`, `battery`, `hydraulic`. |
| `robot_entity` | entity | Opcional, solo para `cable_electric`/`battery`. |
| `robot_cycle_hours` | number | Por defecto 2h. |

---

## 4. Entidades conectables (inputs del usuario)

Símbolos: ⭐ obligatorio, ◆ recomendado, ○ opcional.

### Core equipment
- ⭐ `pump_switch` — `switch` que controla la bomba. **Único campo estrictamente obligatorio.**

### Pump monitoring
- ◆ `pump_power_sensor` — `sensor` device_class `power`.
- ◆ `pump_energy_sensor` — `sensor` device_class `energy`.

### Water chemistry
- ◆ `ph_sensor` — Alertas de pH y sugerencias de corrección.
- ◆ `water_temperature_sensor` — Ajuste fino del target y alertas.
- ○ `salinity_sensor` — Solo si tipo salino y existe sensor.
- ○ `orp_sensor` — Redox, avanzado.
- ○ `free_chlorine_sensor` — Muy raro en residencial.

### Filter monitoring
- ○ `filter_pressure_sensor` — `sensor` device_class `pressure`.

### Equipment room
- ○ `equipment_room_temperature_sensor`
- ○ `equipment_room_humidity_sensor`
- ○ `flood_sensor` — `binary_sensor` device_class `moisture`.

### Salt chlorinator (solo si aplica)
- ○ `chlorinator_switch` — Switch **independiente** del clorador, separado de la bomba. Habilita gestión inteligente de cloración.
- ○ `chlorinator_production_entity` — `number` o `select`, solo si `chlorinator_controllable`.

### Solar integration
- ○ `solar_excess_sensor` — `sensor` de potencia de excedente.
- ○ `solar_forecast_entity` — Previsión solar (Forecast.Solar, Solcast).

### Weather integration
- ○ `weather_entity` — Entidad de previsión meteo.
- ○ `uv_sensor` — Tiene prioridad sobre UV de weather si está presente.

---

## 5. Algoritmo de target diario — concepto central

### 5.1 Visión general

El target diario es la variable central de la integración. **Se compone de dos demandas independientes** que comparten el mismo recurso (horas de bomba encendida):

```
target_minutes = max(target_filtration_minutes, target_chlorine_minutes)
```

En piscinas no salinas o cuando el clorador está fuera de temporada, solo cuenta `target_filtration`.

No es una suma porque filtración y cloración ocurren simultáneamente con la bomba encendida. Es el máximo: la bomba debe funcionar al menos tantas horas como la demanda más exigente.

### 5.2 Propiedades del target

- **Unidad interna:** minutos enteros.
- **Origen agnóstico:** el contador observa el `pump_switch` y suma todo el tiempo ON, sin importar quién lo encendió.
- **Recálculo:** diario (madrugada) + puntual si cambian condiciones relevantes + bajo demanda vía servicio.

### 5.3 Estructura en código

```python
# pool/filtration_calculator.py

@dataclass
class FiltrationInputs:
    # Configuración estática
    pool_volume_m3: float
    nominal_flow_rate_m3h: float
    has_cover: Literal["none", "manual", "automatic"]
    is_covered_by_roof: bool
    user_multiplier: float
    latitude: float
    
    # Configuración de cloración
    chlorination_type: str
    chlorinator_nominal_production_g_h: float | None
    chlorinator_production_pct: float | None
    chlorinator_self_regulating: bool
    chlorinator_active_months: list[int]
    salt_level_g_l: float | None
    
    # Datos dinámicos (todos opcionales)
    current_date: date
    water_temperature_c: float | None
    air_temperature_c: float | None
    uv_index: float | None
    rain_last_24h_mm: float | None
    rain_next_24h_mm: float | None
    cover_currently_on: bool | None

@dataclass
class FiltrationResult:
    target_minutes: int
    target_filtration_minutes: int
    target_chlorine_minutes: int | None  # None si no aplica
    base_minutes: int
    factors: dict[str, float]
    sources: dict[str, str]
    recommended_chlorinator_pct: float | None
    warnings: list[str]

def calculate_target(inputs: FiltrationInputs) -> FiltrationResult:
    ...
```

### 5.4 Cálculo de filtración (`target_filtration`)

```
base_minutes = (pool_volume_m3 / nominal_flow_rate_m3h) × 60 × 2    # 2 turnovers

target_filtration = base_minutes 
                    × seasonal_factor
                    × temperature_factor
                    × uv_factor
                    × rain_factor
                    × cover_factor
                    × user_multiplier
```

**Límites duros:**

```python
min_minutes = base_minutes // 2          # nunca menos de 1 turnover
max_minutes = int(base_minutes * 3.5)    # nunca más de 7 turnovers
```

#### Factor seasonal

Input: mes actual + hemisferio (norte si `latitude >= 0`, sur si `latitude < 0`; en sur los meses se invierten 6 posiciones).

Fuente: siempre disponible. No hay fallback.

| Mes (hemisferio norte) | Factor |
|---|---|
| Enero | 0.50 |
| Febrero | 0.55 |
| Marzo | 0.70 |
| Abril | 0.85 |
| Mayo | 1.00 |
| Junio | 1.15 |
| Julio | 1.30 |
| Agosto | 1.30 |
| Septiembre | 1.10 |
| Octubre | 0.85 |
| Noviembre | 0.65 |
| Diciembre | 0.50 |

Punto neutro en Mayo (1.00). Rango 0.50 – 1.30.

#### Factor temperature

Input: temperatura del agua o del aire como proxy.

Fuentes por orden de preferencia:
1. `water_temperature_sensor` (directo).
2. Temperatura actual de `weather_entity` con offset -2°C.
3. Fallback: factor = 1.0 + warning.

| Temp agua (°C) | Factor |
|---|---|
| ≤ 10 | 0.70 |
| 15 | 0.80 |
| 18 | 0.90 |
| 20 | 1.00 |
| 22 | 1.15 |
| 24 | 1.35 |
| 26 | 1.60 |
| 28 | 1.85 |
| 30 | 2.05 |
| ≥ 32 | 2.20 |

Interpolación lineal entre puntos. Punto neutro en 20°C. Calibrado contra tabla del fabricante Astralpool (8h a 24°C, 10h a 26°C, 13h a >28°C).

#### Factor UV

Input: índice UV.

Fuentes por orden de preferencia:
1. `uv_sensor` (OpenUV).
2. UV de `weather_entity`.
3. Fallback: factor = 1.0.

Si `is_covered_by_roof == true`, factor UV se fuerza a 1.0.

| UV index | Factor |
|---|---|
| 0-1 | 0.90 |
| 4 | 1.00 |
| 7 | 1.10 |
| 10 | 1.18 |
| ≥ 11 | 1.20 |

Punto neutro en UV 4. Rango estrecho (0.90 – 1.20) porque está parcialmente correlacionado con seasonal y temperature.

#### Factor rain

Input: lluvia últimas 24h y próximas 24h.

Fuentes: `weather_entity` o sensor específico. Fallback: factor = 1.0.

Si `is_covered_by_roof == true`, factor rain se fuerza a 1.0.

**Curva pasada:**

| Lluvia últimas 24h (mm) | Factor |
|---|---|
| 0 | 1.00 |
| 1-2 | 1.05 |
| 5 | 1.15 |
| 10 | 1.25 |
| 20 | 1.40 |
| ≥ 40 | 1.55 |

**Curva futura (solo reduce, nunca aumenta):**

| Lluvia próximas 24h (mm) | Factor |
|---|---|
| 0 | 1.00 |
| 1-5 | 1.00 |
| 10 | 0.95 |
| 20 | 0.90 |
| ≥ 40 | 0.85 |

`rain_factor = rain_factor_past × rain_factor_future`

#### Factor cover

| Estado cubierta | Factor |
|---|---|
| Sin cubierta o quitada | 1.00 |
| Cubierta puesta (automatic, estado on) | 0.65 |
| Cubierta manual (heurística: puesta de noche, quitada de día) | 0.80 |

#### User multiplier

`number.homepool_user_multiplier`, rango 0.5 – 2.0, paso 0.05, por defecto 1.0. Válvula de escape para calibración manual.

### 5.5 Cálculo de cloración (`target_chlorine`)

**Solo aplica cuando:** `chlorination_type == salt` **Y** mes actual está en `chlorinator_active_months`.

Fuera de temporada del clorador, `target_chlorine = None` y no se considera.

#### Demanda diaria de cloro

```
chlorine_demand_g = pool_volume_m3 × demand_factor_g_m3_day
```

| Condición | demand_factor (g/m³/día) |
|---|---|
| Invierno / agua < 15°C | 1.0 |
| Primavera-otoño / 15-22°C | 2.0 |
| Verano / 22-28°C | 4.0 |
| Verano extremo / >28°C o uso intensivo | 6.0 |

#### Producción efectiva del clorador

```
effective_production_g_h = nominal_production_g_h 
                          × (current_production_pct / 100) 
                          × salinity_factor 
                          × cold_water_factor
```

**Salinity factor:**

| Sal (g/L) | Factor |
|---|---|
| < 2.5 | 0.00 (clorador no produce) |
| 2.5 | 0.50 |
| 3.0 | 0.75 |
| 3.5 | 0.95 |
| 4.0 – 5.0 | 1.00 |
| 5.5 | 0.95 |
| 6.0 | 0.90 |

Fuentes: `salinity_sensor`, último registro manual vía `homepool.record_salt_level`, o `salt_target` configurado como fallback.

**Cold water factor:**

| Temp agua (°C) | Factor |
|---|---|
| < 10 | 0.00 (clorador parado) |
| 12 | 0.30 |
| 15 | 0.60 |
| 18 | 0.85 |
| ≥ 20 | 1.00 |

Nota: fabricantes como Astralpool especifican "no operar bajo 15°C". Si temp < 15°C y clorador activo, se emite alerta.

#### Tiempo necesario de cloración

```
target_chlorine_min = (chlorine_demand_g / effective_production_g_h) × 60
```

Si `effective_production_g_h ≈ 0`, target_chlorine = ∞ → se ignora y se emite alerta *"Clorador no operativo"*.

#### Producción óptima recomendada

Para cloradores **no autorregulados**, HomePool calcula qué porcentaje de producción pondría si pudiera, para evitar sobreproducción:

```
target_total_hours = target_minutes / 60  # el target final ya decidido
optimal_pct = (chlorine_demand_g / (nominal_production_g_h × target_total_hours)) × 100
```

Expuesto como `sensor.homepool_recommended_chlorinator_production`. En la card como sugerencia: *"Producción recomendada: 26%. Actualmente configurado al 70%."*

### 5.6 Gestión inteligente del clorador

Tres escenarios según la configuración del usuario:

**Escenario A — `chlorinator_switch` configurado (switch separado de la bomba):**
HomePool gestiona el clorador de forma independiente. Enciende el clorador cuando la bomba está ON y `chlorine_target_reached == false`. Apaga el clorador cuando se alcanza el target de cloro del día, aunque la bomba siga filtrando. **Protege la célula, ahorra sal, evita hipercloración.**

**Escenario B — Sin `chlorinator_switch` (clorador en serie con la bomba), `self_regulating == false`:**
HomePool no puede controlar el clorador directamente. Muestra recomendación de porcentaje de producción óptimo y alerta si hay riesgo de sobreproducción. *"Tu clorador va a producir un 60% más cloro del necesario hoy. Considera bajar la producción al 26%."*

**Escenario C — Clorador autorregulado (`self_regulating == true`):**
HomePool no interviene en la producción. Solo monitoriza y muestra datos. El clorador se cuida solo vía su sonda ORP/cloro integrada.

### 5.7 Calendario del clorador salino

**`chlorinator_active_months`:** configurable, por defecto Junio-Septiembre (hemisferio norte).

**Entidades de calendario:**

| Entidad | Descripción |
|---|---|
| `switch.homepool_salt_chlorinator_enabled` | Maestro del clorador. Sigue calendario si `auto_toggle`, manual si no. |
| `binary_sensor.homepool_chlorinator_in_season` | Según calendario, ¿debería estar activo hoy? |
| `sensor.homepool_chlorination_mode` | `salt` / `tablets` / `off` — modo actual. |

**Eventos de temporada:**
- `homepool_chlorinator_season_start` — con recomendaciones: verificar sal, limpiar célula, calibrar sonda pH.
- `homepool_chlorinator_season_end` — con recomendaciones: limpiar célula, pasar a pastillas, proteger sonda pH.

### 5.8 Corrección de pH — restricción del planificador

El pH **no añade horas al target**. Se gestiona como restricción temporal del planificador.

**Entidades:**

| Entidad | Descripción |
|---|---|
| `binary_sensor.homepool_ph_correction_active` | True cuando la sonda pide dosificación |
| `sensor.homepool_ph_correction_minutes_today` | Minutos de dosificación activa hoy |

**Regla del planificador:** si `ph_correction_active == true` y bomba OFF, forzar encendido mínimo 30 min (configurable) o hasta que `ph_correction_active` vuelva a false. Aplica en todos los modos excepto `off`. El tiempo forzado cuenta como elapsed del día.

**Servicio:** `homepool.force_ph_correction_window(duration_min)`

### 5.9 Tabla de validación — Piscina de referencia

Piscina de 30 m³, bomba Astralpool Sena 12.8 m³/h, clorador SEL-55 35 g/h al 70%, costa mediterránea (~39.6°N). Calendario clorador: Junio-Septiembre.

| Mes | Temp agua | UV | Clorador | Target filtr. | Target cloro | **Target final** |
|---|---|---|---|---|---|---|
| Enero | 12°C | 1 | OFF | 140 min (mín) | N/A | **2h 20min** |
| Febrero | 12°C | 2 | OFF | 140 min (mín) | N/A | **2h 20min** |
| Marzo | 14°C | 3 | OFF | 142 min | N/A | **2h 22min** |
| Abril | 17°C | 4 | OFF | 210 min | N/A | **3h 30min** |
| Mayo | 20°C | 5 | OFF | 289 min | N/A | **4h 49min** |
| **Junio** | 24°C | 7 | **ON** | **480 min** | 187 min | **8h 0min** |
| **Julio** | 28°C | 9 | **ON** | **784 min** | 294 min | **13h 4min** |
| **Agosto** | 28°C | 9 | **ON** | **784 min** | 294 min | **13h 4min** |
| Agosto extremo | 30°C, 20mm lluvia | 10 | ON | 984 min (techo) | 441 min | **16h 24min** |
| **Septiembre** | 23°C | 5 | **ON** | 398 min | 140 min | **6h 38min** |
| Octubre | 18°C | 3 | OFF | 204 min | N/A | **3h 24min** |
| Noviembre | 14°C | 2 | OFF | 140 min (mín) | N/A | **2h 20min** |
| Diciembre | 12°C | 1 | OFF | 140 min (mín) | N/A | **2h 20min** |

Validación cruzada con tabla del fabricante Astralpool: 8h (24°C) ✓, 10h (26°C) ✓, 13h (>28°C) ✓.

### 5.10 Comportamiento ante datos faltantes

| Input | Sin dato |
|---|---|
| Temperatura | factor = 1.0 + warning |
| UV | factor = 1.0 + warning |
| Lluvia | factor = 1.0 + warning |
| Cubierta auto sin estado | tratar como `manual` (0.80) |
| Salinidad | usar `salt_target` configurado |
| Producción clorador % | usar `chlorinator_production_default` |

Con configuración mínima (solo `pump_switch`): `target = base × seasonal × user_multiplier`.

---

## 6. Modos de operación

Cinco modos que responden a: *"¿cuándo encender la bomba para cubrir el target del día?"*

| Modo | Descripción | Garantiza target |
|---|---|---|
| `off` | Sin automatización. Solo monitoriza y alerta. | No |
| `timer` | Horarios fijos rígidos. | No |
| `smart` | Distribución óptima ignorando sol. | Sí |
| `solar` | Solo enciende con excedente solar. Oportunista puro. | **No** |
| `smart_solar` | Prioriza sol, completa con red. | **Sí** |

**Modo por defecto:** `off`.

**Requisitos:** `solar` y `smart_solar` requieren `solar_excess_sensor`. `smart_solar` recomienda `solar_forecast_entity`.

### 6.1 Arquitectura en código

```python
class OperationMode(ABC):
    def evaluate(self, context: PoolContext) -> PumpDecision: ...
    def on_pump_state_change(self, old, new) -> None: ...
    def on_target_change(self, new_target_minutes: int) -> None: ...
    def on_external_signal(self, signal: Signal) -> None: ...
```

Cada modo en su propio archivo en `homepool/modes/`.

---

## 7. Jerarquía de prioridades sobre la bomba

De mayor a menor autoridad:

1. **Maintenance lock** (`switch.homepool_maintenance_lock`) — Manual, fuerza OFF.
2. **Safety shutoff** (automático) — Fuerza OFF por seguridad.
3. **Corrección de pH** — Fuerza ON temporal cuando la sonda lo pide.
4. **Acción manual del usuario** — Respetada temporalmente.
5. **Modo de operación automática.**

### 7.1 Safety shutoff

Condiciones configurables (solo activas si sensor conectado):

- Inundación (`flood_sensor` ON).
- Temperatura sala máquinas sobre umbral.
- Presión filtro sobre umbral crítico.
- Consumo bomba fuera de rango durante X minutos.
- Temperatura agua bajo umbral de congelación.

**Entidad:** `binary_sensor.homepool_safety_shutoff_active`.
**Al activarse:** apaga bomba, evento `homepool_safety_shutoff` con severidad `critical`.

---

## 8. Capacidades progresivas

### Nivel 0 — Básico (solo `pump_switch`)
- Target diario (fórmula simple).
- Modos de operación.
- Registro de horas. Recordatorios manuales.

### Nivel 1 — Con sensores adicionales
- `ph_sensor` → alertas pH, sugerencias, tendencias, detección sonda descalibrada.
- `pump_power_sensor` → anomalías, coste energético.
- `solar_excess_sensor` → modos solar disponibles.
- `filter_pressure_sensor` → detección contralavado.
- `flood_sensor` / temp sala → safety shutoff, alertas fuga.
- `chlorinator_switch` → gestión inteligente cloración independiente.

### Nivel 2 — Roadmap
- Cámara manómetro, cámara superficie, algoritmos finos, velocidad variable, climatización, bromo, editor visual posiciones.

---

## 9. Entidades expuestas (outputs de HomePool)

Columna **Depende de** indica requisitos para existencia/valor.

### 9.1 Sensores de target y filtrado

| Entidad | Unidad | Depende de |
|---|---|---|
| `sensor.homepool_daily_filtration_target` | min | Siempre |
| `sensor.homepool_target_filtration_component` | min | Siempre |
| `sensor.homepool_target_chlorine_component` | min | `chlorination_type == salt` + en temporada |
| `sensor.homepool_filtration_elapsed_today` | min | Siempre |
| `sensor.homepool_filtration_remaining_today` | min | Siempre |
| `sensor.homepool_cycle_duration` | min | Siempre |

### 9.2 Sensores de cloración

| Entidad | Unidad | Depende de |
|---|---|---|
| `sensor.homepool_chlorine_production_elapsed_today` | min | `chlorinator_switch` |
| `sensor.homepool_chlorine_production_remaining_today` | min | `chlorinator_switch` |
| `sensor.homepool_recommended_chlorinator_production` | % | `salt` + `self_regulating == false` |
| `sensor.homepool_chlorination_mode` | enum | `chlorination_type == salt` |

### 9.3 Sensores de estado

| Entidad | Unidad | Depende de |
|---|---|---|
| `sensor.homepool_days_since_last_backwash` | days | Siempre |
| `sensor.homepool_days_since_ph_calibration` | days | `ph_sensor` |
| `sensor.homepool_next_manual_task` | texto | Siempre |
| `sensor.homepool_overall_status` | enum | Siempre |

### 9.4 Sensores de salud del agua

| Entidad | Unidad | Depende de |
|---|---|---|
| `sensor.homepool_ph_current` | pH | `ph_sensor` |
| `sensor.homepool_ph_trend` | enum | `ph_sensor` |
| `sensor.homepool_water_temperature` | °C | `water_temperature_sensor` |
| `sensor.homepool_free_chlorine` | ppm | `free_chlorine_sensor` |
| `sensor.homepool_salinity` | g/L | `salinity_sensor` O registro manual |
| `sensor.homepool_orp` | mV | `orp_sensor` |

### 9.5 Sensores energéticos

| Entidad | Unidad | Depende de |
|---|---|---|
| `sensor.homepool_pump_power` | W | `pump_power_sensor` |
| `sensor.homepool_pump_energy_today` | kWh | `pump_energy_sensor` |
| `sensor.homepool_pump_cost_today` | €/$ | `pump_power/energy_sensor` + tarifa |

### 9.6 Sensores de sistema

| Entidad | Unidad | Depende de |
|---|---|---|
| `sensor.homepool_filter_pressure` | bar | `filter_pressure_sensor` |
| `sensor.homepool_equipment_room_temperature` | °C | `equipment_room_temperature_sensor` |
| `sensor.homepool_equipment_room_humidity` | % | `equipment_room_humidity_sensor` |

### 9.7 Sensores del algoritmo (transparencia)

Atributos del sensor `homepool_daily_filtration_target`:

```json
{
  "base_minutes": 281,
  "seasonal_factor": 1.30,
  "temperature_factor": 1.85,
  "uv_factor": 1.16,
  "rain_factor": 1.00,
  "cover_factor": 1.00,
  "user_multiplier": 1.00,
  "target_filtration_minutes": 784,
  "target_chlorine_minutes": 294,
  "dominant_component": "filtration",
  "sources": {
    "temperature": "water_temperature_sensor",
    "uv": "uv_sensor",
    "rain": "weather_entity",
    "salinity": "manual_record"
  },
  "warnings": []
}
```

### 9.8 Binary sensors

| Entidad | Depende de |
|---|---|
| `binary_sensor.homepool_daily_target_reached` | Siempre |
| `binary_sensor.homepool_pump_running` | Siempre |
| `binary_sensor.homepool_chlorine_target_reached` | `chlorinator_switch` |
| `binary_sensor.homepool_backwash_needed` | `filter_pressure_sensor` O por tiempo |
| `binary_sensor.homepool_ph_out_of_range` | `ph_sensor` |
| `binary_sensor.homepool_ph_correction_active` | `ph_sensor` + dosificadora |
| `binary_sensor.homepool_critical_water_temperature` | `water_temperature_sensor` |
| `binary_sensor.homepool_pump_anomaly` | `pump_power_sensor` |
| `binary_sensor.homepool_equipment_room_flood` | `flood_sensor` |
| `binary_sensor.homepool_equipment_room_overheat` | `equipment_room_temperature_sensor` |
| `binary_sensor.homepool_manual_action_pending` | Siempre |
| `binary_sensor.homepool_safety_shutoff_active` | Siempre |
| `binary_sensor.homepool_chlorinator_in_season` | `chlorination_type == salt` |

### 9.9 Switches

| Entidad | Depende de |
|---|---|
| `switch.homepool_pump` | Siempre (wrapper con jerarquía) |
| `switch.homepool_maintenance_lock` | Siempre |
| `switch.homepool_salt_chlorinator_enabled` | `chlorination_type == salt` |

### 9.10 Select

| Entidad | Valores | Depende de |
|---|---|---|
| `select.homepool_operation_mode` | `off`, `timer`, `smart`, `solar`, `smart_solar` | Siempre |

### 9.11 Numbers

| Entidad | Rango | Depende de |
|---|---|---|
| `number.homepool_user_multiplier` | 0.5-2.0 | Siempre |
| `number.homepool_ph_target` | 6.8-8.0 | `ph_sensor` |
| `number.homepool_chlorinator_production` | 0-100% | `salt` + `self_regulating == false` |
| `number.homepool_solar_excess_threshold` | 0-5000 W | `solar_excess_sensor` |

### 9.12 Buttons

| Entidad | Depende de |
|---|---|
| `button.homepool_start_cycle` | Siempre |
| `button.homepool_stop_cycle` | Siempre |
| `button.homepool_mark_backwash_done` | Siempre |
| `button.homepool_mark_salt_added` | `salt` |
| `button.homepool_mark_ph_calibrated` | `ph_sensor` |
| `button.homepool_mark_filter_cleaned` | Siempre |

### 9.13 Servicios

| Servicio | Descripción |
|---|---|
| `homepool.start_cycle(duration)` | Ciclo manual de X minutos |
| `homepool.record_manual_action(action_type, value)` | Registra acción manual |
| `homepool.record_salt_level(g_per_liter)` | Lectura manual de sal |
| `homepool.record_free_chlorine(ppm)` | Lectura manual de cloro |
| `homepool.recalculate_schedule` | Fuerza recálculo del target |
| `homepool.force_ph_correction_window(duration_min)` | Fuerza ventana de corrección pH |
| `homepool.reset_daily_counters` | Reset manual |

### 9.14 Eventos del bus de HA

| Evento | Cuándo | Payload |
|---|---|---|
| `homepool_alert` | Cualquier alerta | `type`, `severity`, `message`, `context` |
| `homepool_safety_shutoff` | Safety activado | `reason`, `sensor`, `value` |
| `homepool_target_recalculated` | Recálculo del target | `old`, `new`, `factors` |
| `homepool_manual_action_due` | Tarea manual pendiente | `action_type`, `last_done` |
| `homepool_chlorinator_season_start` | Inicio temporada salino | recomendaciones |
| `homepool_chlorinator_season_end` | Fin temporada salino | recomendaciones |

---

## 10. Sistema de notificaciones

### 10.1 Base desacoplada (siempre)

Binary sensors de alerta + eventos de bus HA. El usuario crea automatizaciones propias.

### 10.2 Módulo integrado opcional

Config flow → Paso 10 — Notifications:

| Campo | Tipo | Notas |
|---|---|---|
| `enable_builtin_notifications` | boolean | Por defecto `false`. |
| `notification_service` | service picker | Servicios `notify.*` de HA. |
| `notification_severity_min` | enum | `info`, `warning`, `critical`. Por defecto `warning`. |
| `notification_quiet_hours_start/end` | time | Opcional. |
| `critical_ignore_quiet_hours` | boolean | Por defecto `true`. |

---

## 11. Representación visual — Custom Card

**Incluida en v1.**

### 11.1 Configuración

- `display_mode`: `pool`, `pump`, `pool_and_pump`.
- `card_size`: `small`, `medium`, `full`.

### 11.2 Animaciones (v1, CSS + SVG)

- Ondulación agua con bomba ON.
- Burbujas en retornos con bomba ON.
- Halo pulsante en luces encendidas.
- Rotación bomba en sala máquinas.
- Partícula de flujo filtro → retorno.

### 11.3 Datos destacados

pH, temperatura agua, filtrado hecho/recomendado hoy, tiempo restante, modo operación, producción clorador recomendada (si aplica), próxima tarea manual.

---

## 12. Catálogos externos

### 12.1 Hardware (`catalog.yaml`)

Bombas, filtros, cloradores salinos. 5-10 modelos por categoría. Contribuible vía PR.

**Catálogo inicial de cloradores incluye:**

```yaml
salt_chlorinators:
  - brand: "Astralpool"
    model: "SEL-E4 30"
    max_pool_volume_m3: 30
    nominal_production_g_h: 18
    recommended_current_a: 4
    self_regulating: false
    min_water_temp_c: 15
    salt_ideal_g_l: 4.0
    ph_range: [7.0, 7.4]
    power_max_w: 70
    manual_url: "https://..."
    
  - brand: "Astralpool"
    model: "SEL-E4 55"
    max_pool_volume_m3: 55
    nominal_production_g_h: 35
    recommended_current_a: 7
    self_regulating: false
    min_water_temp_c: 15
    salt_ideal_g_l: 4.0
    ph_range: [7.0, 7.4]
    power_max_w: 70
    
  - brand: "Astralpool"
    model: "SEL-E4 95"
    max_pool_volume_m3: 95
    nominal_production_g_h: 55
    recommended_current_a: 10
    self_regulating: false
    min_water_temp_c: 15
    salt_ideal_g_l: 4.0
    ph_range: [7.0, 7.4]
    power_max_w: 70
```

### 12.2 Layouts (`layouts.yaml`)

5-8 variantes por forma. Contribuible vía PR.

### 12.3 Política de mantenimiento

PRs comunitarios, merge ágil, degradación elegante.

---

## 13. Estructura del repositorio

```
homepool/
├── custom_components/
│   └── homepool/
│       ├── __init__.py
│       ├── manifest.json
│       ├── config_flow.py
│       ├── const.py
│       ├── coordinator.py
│       ├── sensor.py
│       ├── binary_sensor.py
│       ├── switch.py
│       ├── select.py
│       ├── number.py
│       ├── button.py
│       ├── notify_dispatcher.py
│       ├── translations/
│       │   ├── en.json
│       │   └── es.json
│       ├── data/
│       │   ├── catalog.yaml
│       │   ├── layouts.yaml
│       │   └── layout_svgs/
│       ├── modes/
│       │   ├── base.py
│       │   ├── off_mode.py
│       │   ├── timer_mode.py
│       │   ├── smart_mode.py
│       │   ├── solar_mode.py
│       │   └── smart_solar_mode.py
│       └── pool/
│           ├── __init__.py
│           ├── geometry.py
│           ├── layouts.py
│           ├── filtration_calculator.py
│           ├── chlorine_calculator.py
│           ├── capabilities.py
│           └── safety.py
├── frontend/
│   ├── package.json
│   ├── src/
│   └── dist/
├── docs/
│   ├── design-v1.md
│   ├── contributing-catalog.md
│   ├── contributing-layouts.md
│   ├── user-guide.md
│   └── development.md
├── tests/
├── hacs.json
├── README.md
└── LICENSE
```

---

## 14. Alcance v1 vs v2

### v1 incluye

- Config flow completo con ramificación, sub-pasos, options flow completo.
- Múltiples instancias. Catálogos hardware + layouts.
- Algoritmo de target con doble componente (filtración + cloración) y factores de seasonal, temperature, UV, rain, cover.
- Gestión inteligente del clorador salino: calendario por meses, switch independiente, producción recomendada, detección de autorregulación.
- Corrección de pH como restricción del planificador.
- 5 modos de operación. Maintenance lock + safety shutoff.
- Capacidades progresivas con indicadores en tiempo real.
- Notificaciones desacopladas + módulo opcional.
- Custom card SVG con animaciones. `card_size` + `display_mode`.
- Transparencia del algoritmo (factores expuestos como atributos).
- Traducciones en/es. Documentación.

### v2 (roadmap)

- Algoritmo fino con histórico, previsión solar, bañistas.
- Velocidad variable (target en volumen m³).
- Visión por cámara (manómetro, superficie).
- Climatización coordinada. Bromo.
- `liner_type` en lógica química.
- Editor visual de posiciones.
- Recomendación inteligente de cuándo pasar a cloro alternativo según coste energético.

---

## 15. Decisiones de diseño clave (registro histórico)

1. Hub/meta-integración, no driver.
2. Lógica en módulos Python puros.
3. Configuración estática vs entidades conectadas, separadas.
4. Capacidades progresivas con indicadores.
5. Target diario como variable central, unidad minutos enteros.
6. Cinco modos: `solar` ≠ `smart_solar`.
7. Jerarquía de prioridades explícita.
8. Maintenance lock separado del modo.
9. Modo por defecto `off`.
10. Múltiples instancias.
11. LocationSelector + coordenadas manuales.
12. Pantalla intermedia confirmación volumen.
13. Forma cuadrada como opción propia.
14. Profundidad siempre min/max.
15. Catálogo YAML contribuible.
16. `has_lights` / `has_robot` eliminados.
17. Luces: N grupos, color por inferencia.
18. `timer` rígido.
19. Custom card en v1.
20. Climatización y bromo en v2.
21. Layouts predefinidos por catálogo.
22. Posicionamiento automático en v1.
23. Skimmer autollenado como entidad distinta.
24. Notificaciones desacopladas + opcional.
25. Animaciones en v1.
26. `card_size` + `display_mode`.
27. **Target = max(filtración, cloración).** No suma; comparten recurso (bomba). Modelo empíricamente validado contra tabla fabricante.
28. **Curva temperature calibrada con tabla fabricante Astralpool** (8h/24°C, 10h/26°C, 13h/>28°C).
29. **Calendario clorador salino.** Meses activos configurables, default Jun-Sep. Apagado automático o manual.
30. **Gestión independiente del clorador.** Switch separado → control directo; sin switch → recomendación %; autorregulado → solo monitoriza.
31. **`chlorinator_self_regulating`** como campo del modelo. Pre-rellenado por catálogo si aplica. Determina si HomePool interviene en producción.
32. **Corrección pH como restricción del planificador**, no factor del target. Fuerza encendido temporal.
33. **Producción recomendada del clorador** expuesta como sensor. Evita sobreproducción en cloradores no autorregulados.
34. **Transparencia del algoritmo.** Todos los factores y fuentes expuestos como atributos del sensor target.

---

## 16. Hardware de referencia validado

Instalación de referencia usada para calibración y validación:

| Componente | Modelo | Datos clave |
|---|---|---|
| Bomba | Astralpool Sena ref 25465 | 12.8 m³/h, 0.89 kW, velocidad fija, 230V |
| Clorador salino | Astralpool SEL-E4 modelo 55 | 35 g/h, 70W, sal ideal 4g/L, no operar <15°C, no autorregulado |
| Dosificadora pH | Astralpool BASIC OPK PH cod 66162 | 1.1 l/h, 1.5 bar, 9W, peristáltica |
| Piscina | Obra, rectangular, 6.5×2.5×1.7m | ~30 m³, isla con escaleras en extremo |
| Ubicación | Costa mediterránea española | Lat ~39.6°N, clima mediterráneo |

---

## 17. Siguientes pasos de desarrollo

1. **Definir `PoolContext` y `PumpDecision`** con detalle de tipos para la interfaz de modos.
2. **Implementar `filtration_calculator.py` y `chlorine_calculator.py`** con las curvas y tablas definidas. Tests unitarios con datos de la tabla de validación.
3. **Schemas de catálogos YAML** con validación. Poblar catálogos iniciales (Astralpool Sena, SEL-E4 30/55/95, BASIC OPK PH).
4. **Scaffolding del repositorio** con estructura completa y archivos mínimos.
5. **Plan de testing.**
6. **Diseño custom card:** componentes, temas, animaciones, binding a entidades.

---

*Fin del documento de diseño v1 — revisión 3.*

---

## 18. Cambios en la implementación v0.1 (noviembre de 2026)

Decisiones tomadas al implementar, con datos reales de una instalación y de su
historial de cinco días soleados de noviembre:

1. **Protección antiheladas en lugar de parada.** El agua cerca de 0 °C ya no es
   una condición de parada de seguridad: fuerza la bomba **encendida**, como hacen
   los controladores comerciales, porque el agua en movimiento no se congela en
   las tuberías. Sin sonda en el agua se usa el aire por debajo de 0 °C.
2. **"Manos fuera"** (`hands_off_entity`): una entidad externa que, mientras está
   encendida, impide que HomePool toque la bomba en ningún sentido. Va por encima
   del bloqueo de mantenimiento. Responde a instalaciones con un indicador manual
   propio y automatizaciones que no se deben tocar.
3. **Excedente, no producción.** El modo solar mira la exportación a red y le suma
   el consumo de la propia bomba mientras funciona. Arranca tras 5 min por encima
   del umbral, tolera picos de consumo de la casa hasta 400 W y para tras 10 min
   por debajo. La bomba funciona al menos 20 min y descansa al menos 10.
4. **El objetivo solo sube durante el día.** Se recalcula cada hora, pero no baja
   hasta el día siguiente o hasta que se pide con el servicio. Un objetivo que
   baja a media tarde es lo que paraba la bomba a medio camino.
5. **Sin dependencia de un servicio meteorológico.** La temperatura sale, por este
   orden, de la sonda del agua, de la máxima prevista para el día o de la máxima
   observada por un sensor exterior.
6. **El día termina a medianoche.** Los modos que garantizan el objetivo terminan
   antes de las 00:00; el relleno con red empieza lo más tarde posible.
7. **Reintentos de órdenes.** Un relé que ignora una orden la recibe de nuevo a
   los 20 s, hasta tres veces, y después se emite una alerta.
8. **Lo que HomePool enciende, HomePool lo apaga.** Si la bomba se encendió por
   pH, heladas o un ciclo manual y ese motivo termina sin que el modo la quiera
   en marcha, se apaga.
9. **Sin sensores espejo.** pH, temperaturas, presión y potencia no se copian en
   entidades nuevas: sus ids están en los atributos del sensor de objetivo para
   la tarjeta. Sí hay sensores para salinidad y cloro libre, porque admiten
   lecturas manuales.
10. **La tarjeta vive en su propio repositorio** (`domotk/homepool-card`): HACS
    admite una sola categoría por repositorio.
11. **El mediodía solar se calcula con la longitud de la piscina**, no con la
    ubicación de Home Assistant.

## 19. Cambios en la v0.1.1 (noviembre de 2026), tras la primera instalación real

1. **El sensor de aire de la piscina manda sobre la previsión.** Orden: sonda de
   agua → máxima de aire medida hoy o ayer → máxima prevista. La previsión es
   de una celda de kilómetros; el sensor está en la piscina.
2. **Curva de temperatura más baja en agua fría.** Por debajo de 15 °C:
   0,45 a 8 °C, 0,48 a 10 °C, 0,52 a 12 °C y 0,70 a 15 °C (antes 0,70 a 10 °C y
   0,80 a 15 °C). Desde 18 °C no cambia. Con la curva anterior, una piscina de
   45 m³ pedía 3 h 05 en noviembre con 14 °C de aire; ahora, 2 h 11.
3. **Suelo invernal.** El mínimo baja de una renovación a 15 °C a media a 12 °C
   o menos. Sin ninguna temperatura se queda en una.
4. **Motivos en el idioma de Home Assistant**, con un `reason_key` que el
   historial sí guarda.
5. **Minutos redondeados**, no truncados.
6. **«Clorador en uso»** como nombre del interruptor maestro del clorador, que
   nunca acciona la célula por sí mismo.

## 20. Cambios en la v0.1.2 (noviembre de 2026), tras la segunda prueba real

1. **Tope a la temperatura medida.** La máxima es el estadístico que más
   altera un sensor al sol o en la unidad exterior de una aerotermia (23 °C
   medidos con 17,7 previstos dieron 268 min en vez de unos 187). Con previsión
   disponible, la medida cuenta como mucho 3 °C por encima de la máxima
   prevista, y la fuente es `air_temperature_max_capped`.
2. **Quién movió la bomba.** HomePool anota los contextos de los eventos
   `automation_triggered` y `script_started`; un cambio bajo uno de ellos (o
   un hijo suyo) se atribuye a esa automatización o script, con su nombre. Con
   `user_id` es una persona; sin nada, «fuera de HomePool» (un pulsador, el
   botón del aparato o un relé que confirma tarde). Claves nuevas:
   `automation_override_*`, `script_override_*` y `external_override_*`;
   atributo `manual_override_by` en el sensor de control. La autoridad sigue
   siendo la misma: se respeta igual.
3. **Etiquetas del dibujo de la piscina traducidas**, un juego por forma
   (`layout_variant_<forma>`), porque el mismo id se lee distinto en una L.
4. **`min_minutes` y `max_minutes`** como atributos del sensor de objetivo.
5. **Destino de los servicios.** `services.yaml` no declara un filtro de
   dispositivo (hassfest no lo admite en `target`), pero el filtro de entidad
   ya deja elegir el dispositivo de la piscina en el selector, y la llamada
   con `device_id` funciona.

## 21. Cambios en la v0.1.3 (noviembre de 2026), tras revisar el mantenimiento

Una revisión de lo que necesita una piscina particular a lo largo del año
encontró seis fallos pequeños, corregidos aquí. Lo nuevo (estado de temporada,
invernaje, producto de invierno, más lecturas) queda para la 0.2.

1. **El pH no fuerza la bomba en `off`**, como ya decía §5.8 y el código no
   hacía. Una ventana pedida con el servicio `force_ph_correction_window` sí se
   cumple en `off`, igual que un ciclo manual: la pide una persona.
2. **Lecturas de pH imposibles.** Una lectura de la sonda fuera de 5-9, o
   exactamente igual durante 24 h (sonda en su vaso o fuera del agua), no
   fuerza la bomba. El aviso de pH fuera de rango sigue mostrándola. La
   cuenta de 24 h no se guarda: tras reiniciar, la sonda tiene otro día.
3. **Recordatorios que llegan.** Los avisos de tareas (`*_due`) y el cambio
   de temporada son INFO, y con el umbral por defecto (`warning`) no llegaban
   al móvil. Ahora son recordatorios: pasan el umbral sin cambiar su
   severidad (que va en el evento y en el aviso), y si caen en las horas de
   silencio (el cambio de temporada es a medianoche) se guardan y se mandan
   al terminar. Una tarea vencida se notifica una vez al día, no otra vez
   tras cada reinicio. El texto del umbral en las opciones lo dice.
4. **«Clorador en uso» manda.** Apagado, la célula no suma minutos al
   objetivo (se trata como fuera de temporada) y cambiarlo recalcula el
   objetivo, que puede bajar. `salt_low` solo salta en temporada y con el
   clorador en uso: una lectura manual vieja ya no lo deja encendido todo el
   invierno.
5. **El aviso de heladas dice la verdad.** Si un escalón por encima de la
   antiheladas (bloqueo, seguridad, manos fuera, bomba no disponible) tiene
   la bomba parada, el aviso lo dice y nombra el motivo; si eso cambia en
   plena helada, el aviso se vuelve a lanzar.
6. **La temporada se conoce desde el primer día.** `in_season_last` se fijaba
   en la primera medianoche, así que instalar el último día de temporada
   perdía el aviso de fin. Ahora se fija al cargar, sin lanzar nada; las
   instalaciones que ya lo tienen guardado no cambian. Instalar en noviembre
   sigue sin avisar de nada hasta junio: decir qué toca en cada momento del
   año es el estado de temporada de la 0.2.

