"""Config and options flow for HomePool.

The same steps serve both. Setting a pool up walks them in order; the options
flow opens a menu and lets each group be edited on its own, so changing the
pump does not mean answering the geometry again.

Only the pump switch is required. Everything else has a default or can be left
empty, and the integration does what it can with what it gets: that is the
"progressive capabilities" idea from the design document.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector as sel
from homeassistant.util import dt as dt_util

from .const import (
    CONFIG_VERSION,
    CONF_AIR_TEMPERATURE_SENSOR,
    CONF_BACKWASH_INTERVAL_DAYS,
    CONF_CHLORINATION_TYPE,
    CONF_CHLORINATOR_ACTIVE_MONTHS,
    CONF_CHLORINATOR_AUTO_TOGGLE,
    CONF_CHLORINATOR_CONTROLLABLE,
    CONF_CHLORINATOR_MIN_WATER_TEMP,
    CONF_CHLORINATOR_MODEL,
    CONF_CHLORINATOR_NOMINAL_PRODUCTION,
    CONF_CHLORINATOR_PRODUCTION_DEFAULT,
    CONF_CHLORINATOR_PRODUCTION_ENTITY,
    CONF_CHLORINATOR_SELF_REGULATING,
    CONF_CHLORINATOR_SWITCH,
    CONF_CLARIFIER_DOSE_PER_10M3,
    CONF_CLARIFIER_DOSE_UNIT,
    CONF_CONSTRUCTION_TYPE,
    CONF_COVER_ENTITY,
    CONF_CRITICAL_IGNORE_QUIET_HOURS,
    CONF_DEPTH_MAX,
    CONF_DEPTH_MIN,
    CONF_ENABLE_BUILTIN_NOTIFICATIONS,
    CONF_ENERGY_PRICE,
    CONF_ENERGY_PRICE_ENTITY,
    CONF_EQUIPMENT_ROOM_HUMIDITY_SENSOR,
    CONF_EQUIPMENT_ROOM_MAX_TEMP,
    CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR,
    CONF_FILTER_PRESSURE_CRITICAL,
    CONF_FILTER_PRESSURE_NORMAL_MAX,
    CONF_FILTER_PRESSURE_NORMAL_MIN,
    CONF_FILTER_PRESSURE_SENSOR,
    CONF_FILTER_TYPE,
    CONF_FLOCCULANT_DOSE_PER_10M3,
    CONF_FLOCCULANT_DOSE_UNIT,
    CONF_FLOOD_SENSOR,
    CONF_FREEZE_PROTECTION,
    CONF_FREEZE_THRESHOLD,
    CONF_FREE_CHLORINE_RANGE_MAX,
    CONF_FREE_CHLORINE_RANGE_MIN,
    CONF_FREE_CHLORINE_SENSOR,
    CONF_FREE_CHLORINE_TARGET,
    CONF_HANDS_OFF_ENTITY,
    CONF_HAS_AUTOFILL_SKIMMER,
    CONF_HAS_COVER,
    CONF_HAS_PH_DOSING,
    CONF_HAS_PH_PROBE_OUTSIDE,
    CONF_HEATING_TYPE,
    CONF_IS_COVERED_BY_ROOF,
    CONF_LATITUDE,
    CONF_LAYOUT_ORIENTATION,
    CONF_LAYOUT_VARIANT,
    CONF_LIGHT_ENTITIES,
    CONF_LINER_COLOR,
    CONF_LINER_TYPE,
    CONF_LONGITUDE,
    CONF_MANUAL_OVERRIDE_MINUTES,
    CONF_NOTIFICATION_QUIET_HOURS_END,
    CONF_NOTIFICATION_QUIET_HOURS_START,
    CONF_NOTIFICATION_SERVICE,
    CONF_NOTIFICATION_SEVERITY_MIN,
    CONF_ORIENTATION,
    CONF_ORP_SENSOR,
    CONF_PH_CALIBRATION_INTERVAL_DAYS,
    CONF_PH_CORRECTION_MAX_DAILY,
    CONF_PH_CORRECTION_MINUTES,
    CONF_PH_DOSING_ENTITY,
    CONF_PH_RANGE_MAX,
    CONF_PH_RANGE_MIN,
    CONF_PH_SENSOR,
    CONF_PH_TARGET,
    CONF_POOL_CLEANER_TYPE,
    CONF_POOL_NAME,
    CONF_PUMP_ENERGY_SENSOR,
    CONF_PUMP_MODEL,
    CONF_PUMP_NOMINAL_FLOW_RATE,
    CONF_PUMP_NOMINAL_POWER,
    CONF_PUMP_POWER_SENSOR,
    CONF_PUMP_SPEED_TYPE,
    CONF_PUMP_SWITCH,
    CONF_RAIN_SENSOR,
    CONF_RETURNS_COUNT,
    CONF_ROBOT_ENTITY,
    CONF_SALINITY_SENSOR,
    CONF_SALT_RANGE_MAX,
    CONF_SALT_RANGE_MIN,
    CONF_SALT_TARGET,
    CONF_SHAPE,
    CONF_SHOCK_CONCENTRATION,
    CONF_SHOCK_PRODUCT,
    CONF_SKIMMERS_COUNT,
    CONF_SOLAR_EXCESS_SENSOR,
    CONF_SOLAR_EXCESS_SIGN,
    CONF_SOLAR_IMPORT_TOLERANCE,
    CONF_SWIMMING_MONTHS,
    CONF_TIMER_SLOTS,
    CONF_UV_SENSOR,
    CONF_VOLUME,
    CONF_VOLUME_OVERRIDE,
    CONF_WATER_TEMPERATURE_SENSOR,
    CONF_WEATHER_ENTITY,
    CONF_WINTER_PRODUCT_DOSE_PER_M3,
    CONF_WINTER_PRODUCT_INTERVAL_DAYS,
    CONF_WINTER_PRODUCT_TYPE,
    DEFAULT_BACKWASH_INTERVAL_DAYS,
    DEFAULT_CHLORINATOR_ACTIVE_MONTHS_NORTH,
    DEFAULT_CHLORINATOR_ACTIVE_MONTHS_SOUTH,
    DEFAULT_CHLORINATOR_MIN_WATER_TEMP,
    DEFAULT_CHLORINATOR_PRODUCTION_PCT,
    DEFAULT_DOSE_UNIT,
    DEFAULT_EQUIPMENT_ROOM_MAX_TEMP,
    DEFAULT_FILTER_PRESSURE_CRITICAL,
    DEFAULT_FILTER_PRESSURE_NORMAL_MAX,
    DEFAULT_FILTER_PRESSURE_NORMAL_MIN,
    DEFAULT_FREEZE_THRESHOLD,
    DEFAULT_FREE_CHLORINE_RANGE_MAX,
    DEFAULT_FREE_CHLORINE_RANGE_MIN,
    DEFAULT_FREE_CHLORINE_TARGET,
    DEFAULT_MANUAL_OVERRIDE_MINUTES,
    DEFAULT_NAME,
    DEFAULT_NOTIFICATION_SEVERITY,
    DEFAULT_PH_CALIBRATION_INTERVAL_DAYS,
    DEFAULT_PH_CORRECTION_MAX_DAILY,
    DEFAULT_PH_CORRECTION_MINUTES,
    DEFAULT_PH_RANGE_MAX,
    DEFAULT_PH_RANGE_MIN,
    DEFAULT_PH_TARGET,
    DEFAULT_RETURNS_COUNT,
    DEFAULT_SALT_RANGE_MAX,
    DEFAULT_SALT_RANGE_MIN,
    DEFAULT_SALT_TARGET,
    DEFAULT_SHOCK_PRODUCT,
    DEFAULT_SKIMMERS_COUNT,
    DEFAULT_SOLAR_IMPORT_TOLERANCE_W,
    DEFAULT_WINTER_PRODUCT_DOSE_PER_M3,
    DEFAULT_WINTER_PRODUCT_INTERVAL_DAYS,
    DIMENSION_KEYS,
    DOMAIN,
    ChlorinationType,
    ConstructionType,
    CoverType,
    ExcessSign,
    FilterType,
    HeatingType,
    LinerColor,
    LinerType,
    Orientation,
    PoolCleanerType,
    PoolShape,
    PumpSpeedType,
    Severity,
)
from .pool.dosing import SHOCK_DEFAULT_CONCENTRATION, SHOCK_LIQUIDS
from .pool.geometry import PoolDimensions, calculate_volume
from .pool.hardware import find, load_hardware
from .pool.tasks import TASKS, TASKS_BY_KEY, configured_days, task_applies
from .pool.readings import DEFAULT_STALE_DAYS, KINDS, NEW_SENSOR_KINDS, default_range
from .pool.layouts import LayoutCatalog, get_orientation_options, load_catalog
from .pool.season import default_swimming_months

CUSTOM = "custom"
CATALOG_CACHE = f"{DOMAIN}_catalogs"


async def _catalogs(hass: HomeAssistant) -> tuple[LayoutCatalog, dict[str, Any]]:
    """Both catalogues, read once and off the event loop."""
    cached = hass.data.get(CATALOG_CACHE)
    if cached is None:
        layouts = await hass.async_add_executor_job(load_catalog)
        hardware = await hass.async_add_executor_job(load_hardware)
        cached = hass.data[CATALOG_CACHE] = (layouts, hardware)
    return cached


# ── selector helpers ──


def _select(options: list[str], key: str, multiple: bool = False) -> sel.SelectSelector:
    return sel.SelectSelector(
        sel.SelectSelectorConfig(
            options=options,
            translation_key=key,
            mode=sel.SelectSelectorMode.DROPDOWN,
            multiple=multiple,
        )
    )


def _number(
    minimum: float, maximum: float, step: float | str, unit: str | None = None, box: bool = True
) -> sel.NumberSelector:
    config: dict[str, Any] = {
        "min": minimum,
        "max": maximum,
        "step": step,
        "mode": sel.NumberSelectorMode.BOX if box else sel.NumberSelectorMode.SLIDER,
    }
    if unit:
        config["unit_of_measurement"] = unit
    return sel.NumberSelector(sel.NumberSelectorConfig(**config))


def _entity(
    domains: list[str], device_class: str | list[str] | None = None, multiple: bool = False
) -> sel.EntitySelector:
    config: dict[str, Any] = {"domain": domains, "multiple": multiple}
    if device_class:
        config["device_class"] = device_class
    return sel.EntitySelector(sel.EntitySelectorConfig(**config))


def _values(enum) -> list[str]:
    return [e.value for e in enum]


MONTHS = [str(m) for m in range(1, 13)]
WINTER_PRODUCT_TYPES = ["none", "floater", "liquid", "tablets"]
SHOCK_PRODUCTS = list(SHOCK_DEFAULT_CONCENTRATION)
# The highest concentration that can be real: per cent of chlorine for a
# granular product, g/L for a liquid one.
SHOCK_MAX_GRANULAR = 100
SHOCK_MAX_LIQUID = 300
# The units read the same in every language, and "mL" could not be a
# translation key (they are lower case).
_DOSE_UNIT_SELECTOR = sel.SelectSelector(
    sel.SelectSelectorConfig(options=["mL", "g"], mode=sel.SelectSelectorMode.DROPDOWN)
)


def _or(value: Any, default: Any) -> Any:
    """``value``, or ``default`` when it is unset: a stored None means "the default"."""
    return default if value is None else value


def _shock_concentration(
    user_input: dict[str, Any], shown_product: str, shown: float
) -> float | None | bool:
    """The shock concentration to store: None to follow the product, or
    False when it cannot be right for the product chosen.

    A figure is per cent for one product and g/L for another, so one left as
    shown when the product changes is dropped rather than carried over: a
    custom 70 % read as 70 g/L would double the litres.
    """
    product = user_input.get(CONF_SHOCK_PRODUCT, shown_product)
    value = user_input.get(CONF_SHOCK_CONCENTRATION)
    if value is not None and product != shown_product and value == shown:
        value = None
    if value is None or value == SHOCK_DEFAULT_CONCENTRATION[product]:
        return None
    highest = SHOCK_MAX_LIQUID if product in SHOCK_LIQUIDS else SHOCK_MAX_GRANULAR
    if not 1 <= value <= highest:
        return False
    return float(value)


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    """Sections arrive nested, one dict per section. Store them flat."""
    flat: dict[str, Any] = {}
    for key, value in user_input.items():
        if isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return flat


def _schema_keys(schema: vol.Schema) -> list[str]:
    keys: list[str] = []
    for marker, value in schema.schema.items():
        if isinstance(value, section):
            keys.extend(_schema_keys(value.schema))
        else:
            keys.append(str(marker))
    return keys


class _Wizard:
    """Steps shared by the config flow and the options flow.

    ``self._data`` holds the values so far. Each step shows them as suggested
    values, so an optional field left empty really is empty: Home Assistant
    drops it from the input, and ``_store`` writes that back as None.
    """

    _data: dict[str, Any]
    hass: HomeAssistant

    def _sv(self, key: str, default: Any = None) -> dict[str, Any]:
        value = self._data.get(key, default)
        return {"suggested_value": value} if value is not None else {}

    def _store(self, schema: vol.Schema, user_input: dict[str, Any]) -> None:
        flat = _flatten(user_input)
        for key in _schema_keys(schema):
            value = flat.get(key)
            if isinstance(value, str) and value.strip() == "":
                value = None
            self._data[key] = value

    async def _after(self, step: str) -> ConfigFlowResult:
        """Where to go once ``step`` is done. Overridden by each flow."""
        raise NotImplementedError

    def _form(
        self, step_id: str, schema: vol.Schema, errors: dict[str, str] | None = None, **placeholders
    ) -> ConfigFlowResult:
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id=step_id,
            data_schema=schema,
            errors=errors or {},
            description_placeholders={k: str(v) for k, v in placeholders.items()} or None,
        )

    # ── identity ──

    def _identity_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_POOL_NAME, default=self._data.get(CONF_POOL_NAME, DEFAULT_NAME)): str,
                vol.Required(
                    CONF_LATITUDE, default=self._data.get(CONF_LATITUDE, self.hass.config.latitude)
                ): _number(-90, 90, "any"),
                vol.Required(
                    CONF_LONGITUDE,
                    default=self._data.get(CONF_LONGITUDE, self.hass.config.longitude),
                ): _number(-180, 180, "any"),
            }
        )

    async def async_step_identity(self, user_input: dict[str, Any] | None = None):
        schema = self._identity_schema()
        if user_input is not None:
            self._store(schema, user_input)
            return await self._after("identity")
        return self._form("identity", schema)

    # ── geometry ──

    async def async_step_shape(self, user_input: dict[str, Any] | None = None):
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SHAPE, default=self._data.get(CONF_SHAPE, PoolShape.RECTANGULAR)
                ): _select(_values(PoolShape), "shape"),
            }
        )
        if user_input is not None:
            if user_input[CONF_SHAPE] != self._data.get(CONF_SHAPE):
                self._data[CONF_LAYOUT_VARIANT] = "plain"
                self._data[CONF_LAYOUT_ORIENTATION] = None
            self._store(schema, user_input)
            return await self.async_step_dimensions()
        return self._form("shape", schema)

    async def async_step_dimensions(self, user_input: dict[str, Any] | None = None):
        layouts, _ = await _catalogs(self.hass)
        shape = self._data.get(CONF_SHAPE, PoolShape.RECTANGULAR)
        fields: dict[Any, Any] = {}
        for key in DIMENSION_KEYS[shape]:
            fields[vol.Required(key, description=self._sv(key))] = _number(0.5, 50, 0.05, "m")
        fields[vol.Required(CONF_DEPTH_MIN, description=self._sv(CONF_DEPTH_MIN, 1.0))] = _number(
            0.3, 5, 0.05, "m"
        )
        fields[vol.Required(CONF_DEPTH_MAX, description=self._sv(CONF_DEPTH_MAX, 1.8))] = _number(
            0.3, 5, 0.05, "m"
        )
        variants = layouts.get_variants_for_shape(shape)
        fields[
            vol.Required(
                CONF_LAYOUT_VARIANT,
                default=self._data.get(CONF_LAYOUT_VARIANT) or "plain",
            )
        ] = sel.SelectSelector(
            sel.SelectSelectorConfig(
                options=[sel.SelectOptionDict(value=v.id, label=v.name) for v in variants],
                mode=sel.SelectSelectorMode.DROPDOWN,
                # One set per shape: the same id reads differently on an L
                # (steps at the junction) than on a rectangle (in a corner).
                translation_key=f"layout_variant_{shape}",
            )
        )
        schema = vol.Schema(fields)
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_DEPTH_MAX] < user_input[CONF_DEPTH_MIN]:
                errors[CONF_DEPTH_MAX] = "depth_order"
            else:
                self._store(schema, user_input)
                variant = layouts.get_variant(shape, self._data[CONF_LAYOUT_VARIANT])
                if get_orientation_options(variant.requires_orientation):
                    return await self.async_step_layout_orientation()
                self._data[CONF_LAYOUT_ORIENTATION] = None
                return await self.async_step_volume()
        return self._form("dimensions", schema, errors)

    async def async_step_layout_orientation(self, user_input: dict[str, Any] | None = None):
        layouts, _ = await _catalogs(self.hass)
        variant = layouts.get_variant(self._data[CONF_SHAPE], self._data[CONF_LAYOUT_VARIANT])
        options = get_orientation_options(variant.requires_orientation)
        current = self._data.get(CONF_LAYOUT_ORIENTATION)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LAYOUT_ORIENTATION, default=current if current in options else options[0]
                ): _select(options, "layout_orientation"),
            }
        )
        if user_input is not None:
            self._store(schema, user_input)
            return await self.async_step_volume()
        return self._form("layout_orientation", schema)

    def _computed_volume(self, layouts: LayoutCatalog) -> float:
        shape = self._data[CONF_SHAPE]
        variant = layouts.get_variant(shape, self._data.get(CONF_LAYOUT_VARIANT) or "plain")
        dims = PoolDimensions(
            shape=shape,
            depth_min=float(self._data[CONF_DEPTH_MIN]),
            depth_max=float(self._data[CONF_DEPTH_MAX]),
            volume_adjustment=variant.volume_adjustment,
            **{k: float(self._data[k]) for k in DIMENSION_KEYS[shape]},
        )
        return calculate_volume(dims)

    async def async_step_volume(self, user_input: dict[str, Any] | None = None):
        """Show the computed volume and let it be corrected."""
        layouts, _ = await _catalogs(self.hass)
        computed = self._computed_volume(layouts)
        override = self._data.get(CONF_VOLUME_OVERRIDE)
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_VOLUME_OVERRIDE, description={"suggested_value": override}
                    if override else {}
                ): _number(1, 2000, 0.1, "m³"),
            }
        )
        if user_input is not None:
            self._store(schema, user_input)
            override = self._data.get(CONF_VOLUME_OVERRIDE)
            self._data[CONF_VOLUME] = round(float(override), 1) if override else computed
            return await self._after("geometry")
        return self._form("volume", schema, volume=computed)

    # ── construction ──

    async def async_step_construction(self, user_input: dict[str, Any] | None = None):
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CONSTRUCTION_TYPE,
                    default=self._data.get(CONF_CONSTRUCTION_TYPE, ConstructionType.BUILT_IN),
                ): _select(_values(ConstructionType), "construction_type"),
                vol.Required(
                    CONF_HAS_COVER, default=self._data.get(CONF_HAS_COVER, CoverType.NONE)
                ): _select(_values(CoverType), "has_cover"),
                vol.Optional(CONF_COVER_ENTITY, description=self._sv(CONF_COVER_ENTITY)): _entity(
                    ["cover", "binary_sensor", "input_boolean"]
                ),
                vol.Required(
                    CONF_IS_COVERED_BY_ROOF, default=self._data.get(CONF_IS_COVERED_BY_ROOF, False)
                ): bool,
                vol.Required(
                    CONF_HEATING_TYPE, default=self._data.get(CONF_HEATING_TYPE, HeatingType.NONE)
                ): _select(_values(HeatingType), "heating_type"),
                vol.Required(
                    CONF_LINER_TYPE, default=self._data.get(CONF_LINER_TYPE, LinerType.NOT_SPECIFIED)
                ): _select(_values(LinerType), "liner_type"),
                vol.Required(
                    CONF_LINER_COLOR, default=self._data.get(CONF_LINER_COLOR, LinerColor.LIGHT_BLUE)
                ): _select(_values(LinerColor), "liner_color"),
                vol.Required(
                    CONF_ORIENTATION,
                    default=self._data.get(CONF_ORIENTATION, Orientation.NOT_SPECIFIED),
                ): _select(_values(Orientation), "orientation"),
            }
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_HAS_COVER] == CoverType.AUTOMATIC and not user_input.get(
                CONF_COVER_ENTITY
            ):
                errors[CONF_COVER_ENTITY] = "cover_entity_required"
            else:
                self._store(schema, user_input)
                return await self._after("construction")
        return self._form("construction", schema, errors)

    # ── filtration ──

    async def async_step_pump(self, user_input: dict[str, Any] | None = None):
        _, hardware = await _catalogs(self.hass)
        options = [CUSTOM, *[p["key"] for p in hardware["pumps"]]]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PUMP_MODEL, default=self._data.get(CONF_PUMP_MODEL) or CUSTOM
                ): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=options,
                        translation_key="catalog_model",
                        mode=sel.SelectSelectorMode.DROPDOWN,
                        custom_value=False,
                    )
                ),
            }
        )
        if user_input is not None:
            model = user_input[CONF_PUMP_MODEL]
            item = find(hardware, "pumps", model)
            if item and model != self._data.get(CONF_PUMP_MODEL):
                self._data[CONF_PUMP_NOMINAL_FLOW_RATE] = item.get("nominal_flow_rate")
                self._data[CONF_PUMP_NOMINAL_POWER] = item.get("nominal_power")
                self._data[CONF_PUMP_SPEED_TYPE] = item.get("type", PumpSpeedType.FIXED)
            self._data[CONF_PUMP_MODEL] = None if model == CUSTOM else model
            return await self.async_step_filtration()
        return self._form("pump", schema)

    async def async_step_filtration(self, user_input: dict[str, Any] | None = None):
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PUMP_NOMINAL_FLOW_RATE, description=self._sv(CONF_PUMP_NOMINAL_FLOW_RATE)
                ): _number(1, 100, 0.1, "m³/h"),
                vol.Optional(
                    CONF_PUMP_NOMINAL_POWER, description=self._sv(CONF_PUMP_NOMINAL_POWER)
                ): _number(50, 5000, 10, "W"),
                vol.Required(
                    CONF_PUMP_SPEED_TYPE,
                    default=self._data.get(CONF_PUMP_SPEED_TYPE) or PumpSpeedType.FIXED,
                ): _select(_values(PumpSpeedType), "pump_speed_type"),
                vol.Required(
                    CONF_FILTER_TYPE, default=self._data.get(CONF_FILTER_TYPE, FilterType.SAND)
                ): _select(_values(FilterType), "filter_type"),
                vol.Required(
                    CONF_SKIMMERS_COUNT,
                    default=self._data.get(CONF_SKIMMERS_COUNT, DEFAULT_SKIMMERS_COUNT),
                ): _number(0, 8, 1),
                vol.Required(
                    CONF_RETURNS_COUNT,
                    default=self._data.get(CONF_RETURNS_COUNT, DEFAULT_RETURNS_COUNT),
                ): _number(0, 12, 1),
                vol.Required(
                    CONF_HAS_AUTOFILL_SKIMMER,
                    default=self._data.get(CONF_HAS_AUTOFILL_SKIMMER, False),
                ): bool,
                vol.Required(
                    CONF_FILTER_PRESSURE_NORMAL_MIN,
                    default=self._data.get(
                        CONF_FILTER_PRESSURE_NORMAL_MIN, DEFAULT_FILTER_PRESSURE_NORMAL_MIN
                    ),
                ): _number(0, 5, 0.05, "bar"),
                vol.Required(
                    CONF_FILTER_PRESSURE_NORMAL_MAX,
                    default=self._data.get(
                        CONF_FILTER_PRESSURE_NORMAL_MAX, DEFAULT_FILTER_PRESSURE_NORMAL_MAX
                    ),
                ): _number(0, 5, 0.05, "bar"),
                vol.Required(
                    CONF_BACKWASH_INTERVAL_DAYS,
                    default=self._data.get(
                        CONF_BACKWASH_INTERVAL_DAYS, DEFAULT_BACKWASH_INTERVAL_DAYS
                    ),
                ): _number(1, 120, 1, "d"),
            }
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_FILTER_PRESSURE_NORMAL_MAX] <= user_input[
                CONF_FILTER_PRESSURE_NORMAL_MIN
            ]:
                errors[CONF_FILTER_PRESSURE_NORMAL_MAX] = "pressure_order"
            else:
                self._store(schema, user_input)
                for key in (CONF_SKIMMERS_COUNT, CONF_RETURNS_COUNT, CONF_BACKWASH_INTERVAL_DAYS):
                    self._data[key] = int(self._data[key])
                return await self._after("filtration")
        return self._form("filtration", schema, errors)

    # ── water treatment ──

    async def async_step_water(self, user_input: dict[str, Any] | None = None):
        d = self._data
        swimming = d.get(CONF_SWIMMING_MONTHS) or default_swimming_months(
            d.get(CONF_CHLORINATOR_ACTIVE_MONTHS),
            d.get(CONF_CHLORINATION_TYPE) == ChlorinationType.SALT,
            float(d.get(CONF_LATITUDE, self.hass.config.latitude) or 0),
        )
        is_salt = d.get(CONF_CHLORINATION_TYPE, ChlorinationType.SALT) == ChlorinationType.SALT
        shock_product = d.get(CONF_SHOCK_PRODUCT) or DEFAULT_SHOCK_PRODUCT
        shown_concentration = _or(
            d.get(CONF_SHOCK_CONCENTRATION), SHOCK_DEFAULT_CONCENTRATION[shock_product]
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CHLORINATION_TYPE,
                    default=d.get(CONF_CHLORINATION_TYPE, ChlorinationType.SALT),
                ): _select(_values(ChlorinationType), "chlorination_type"),
                vol.Required(CONF_PH_TARGET, default=d.get(CONF_PH_TARGET, DEFAULT_PH_TARGET)): _number(
                    6.8, 8.0, 0.1
                ),
                vol.Required(
                    CONF_PH_RANGE_MIN, default=d.get(CONF_PH_RANGE_MIN, DEFAULT_PH_RANGE_MIN)
                ): _number(6.5, 8.0, 0.1),
                vol.Required(
                    CONF_PH_RANGE_MAX, default=d.get(CONF_PH_RANGE_MAX, DEFAULT_PH_RANGE_MAX)
                ): _number(6.8, 8.5, 0.1),
                vol.Required(CONF_HAS_PH_DOSING, default=d.get(CONF_HAS_PH_DOSING, False)): bool,
                vol.Required(
                    CONF_PH_CALIBRATION_INTERVAL_DAYS,
                    default=d.get(
                        CONF_PH_CALIBRATION_INTERVAL_DAYS, DEFAULT_PH_CALIBRATION_INTERVAL_DAYS
                    ),
                ): _number(7, 365, 1, "d"),
                vol.Required(
                    CONF_FREE_CHLORINE_TARGET,
                    default=d.get(CONF_FREE_CHLORINE_TARGET, DEFAULT_FREE_CHLORINE_TARGET),
                ): _number(0, 10, 0.1, "ppm"),
                vol.Required(
                    CONF_FREE_CHLORINE_RANGE_MIN,
                    default=d.get(CONF_FREE_CHLORINE_RANGE_MIN, DEFAULT_FREE_CHLORINE_RANGE_MIN),
                ): _number(0, 10, 0.1, "ppm"),
                vol.Required(
                    CONF_FREE_CHLORINE_RANGE_MAX,
                    default=d.get(CONF_FREE_CHLORINE_RANGE_MAX, DEFAULT_FREE_CHLORINE_RANGE_MAX),
                ): _number(0, 10, 0.1, "ppm"),
                vol.Required(
                    CONF_SWIMMING_MONTHS, default=[str(m) for m in swimming]
                ): _select(MONTHS, "month", multiple=True),
                vol.Required(
                    CONF_WINTER_PRODUCT_TYPE, default=d.get(CONF_WINTER_PRODUCT_TYPE) or "none"
                ): _select(WINTER_PRODUCT_TYPES, "winter_product_type"),
                vol.Required(
                    CONF_WINTER_PRODUCT_DOSE_PER_M3,
                    default=d.get(CONF_WINTER_PRODUCT_DOSE_PER_M3)
                    or DEFAULT_WINTER_PRODUCT_DOSE_PER_M3,
                ): _number(0.001, 1, 0.001),
                vol.Required(
                    CONF_WINTER_PRODUCT_INTERVAL_DAYS,
                    default=d.get(CONF_WINTER_PRODUCT_INTERVAL_DAYS)
                    or DEFAULT_WINTER_PRODUCT_INTERVAL_DAYS,
                ): _number(7, 365, 1, "d"),
                **self._readings_fields(is_salt),
                vol.Required(CONF_SHOCK_PRODUCT, default=shock_product): _select(
                    SHOCK_PRODUCTS, "shock_product"
                ),
                # Empty, it follows the product: per cent for the granular
                # ones, g/L for the liquid.
                vol.Optional(
                    CONF_SHOCK_CONCENTRATION,
                    description={"suggested_value": shown_concentration},
                ): _number(1, 1000, "any"),  # judged per product below
                # The label's dose per 10 m³; HomePool has no figure of its own.
                vol.Optional(
                    CONF_CLARIFIER_DOSE_PER_10M3,
                    description=self._sv(CONF_CLARIFIER_DOSE_PER_10M3),
                ): _number(0, 10000, "any"),
                vol.Required(
                    CONF_CLARIFIER_DOSE_UNIT,
                    default=d.get(CONF_CLARIFIER_DOSE_UNIT) or DEFAULT_DOSE_UNIT,
                ): _DOSE_UNIT_SELECTOR,
                vol.Optional(
                    CONF_FLOCCULANT_DOSE_PER_10M3,
                    description=self._sv(CONF_FLOCCULANT_DOSE_PER_10M3),
                ): _number(0, 10000, "any"),
                vol.Required(
                    CONF_FLOCCULANT_DOSE_UNIT,
                    default=d.get(CONF_FLOCCULANT_DOSE_UNIT) or DEFAULT_DOSE_UNIT,
                ): _DOSE_UNIT_SELECTOR,
            }
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            concentration = _shock_concentration(user_input, shock_product, shown_concentration)
            if not user_input.get(CONF_SWIMMING_MONTHS):
                errors[CONF_SWIMMING_MONTHS] = "no_months"
            elif concentration is False:
                errors[CONF_SHOCK_CONCENTRATION] = "concentration_range"
            elif bad := self._reading_range_error(user_input):
                errors[bad] = "range_order"
            elif not (
                user_input[CONF_PH_RANGE_MIN]
                <= user_input[CONF_PH_TARGET]
                <= user_input[CONF_PH_RANGE_MAX]
            ):
                errors[CONF_PH_TARGET] = "ph_order"
            else:
                self._store(schema, user_input)
                self._data[CONF_PH_CALIBRATION_INTERVAL_DAYS] = int(
                    self._data[CONF_PH_CALIBRATION_INTERVAL_DAYS]
                )
                self._data[CONF_WINTER_PRODUCT_INTERVAL_DAYS] = int(
                    self._data[CONF_WINTER_PRODUCT_INTERVAL_DAYS]
                )
                self._data[CONF_SWIMMING_MONTHS] = sorted(
                    int(m) for m in self._data[CONF_SWIMMING_MONTHS]
                )
                for kind in KINDS:
                    self._data[f"{kind}_stale_days"] = int(self._data[f"{kind}_stale_days"])
                self._keep_only_changed(is_salt)
                self._data[CONF_SHOCK_CONCENTRATION] = concentration
                return await self._after("water")
        return self._form("water", schema, errors)

    def _keep_only_changed(self, is_salt: bool) -> None:
        """Forget the ranges left as the form showed them by default, so they
        keep following the chlorination (the cyanuric acid's does)."""
        d = self._data
        for kind in NEW_SENSOR_KINDS:
            for key, default in zip(
                (f"{kind}_range_min", f"{kind}_range_max"), default_range(kind, is_salt)
            ):
                if d.get(key) is not None and default is not None and d[key] == default:
                    d[key] = None

    def _readings_fields(self, is_salt: bool) -> dict[Any, Any]:
        """The ranges of the readings taken by hand, and how long each one is trusted."""
        d = self._data
        fields: dict[Any, Any] = {}
        for kind in NEW_SENSOR_KINDS:
            low, high = default_range(kind, is_salt)
            if low is not None:
                key = f"{kind}_range_min"
                fields[vol.Required(key, default=_or(d.get(key), low))] = _number(
                    0, 5000, "any", "mg/L"
                )
            key = f"{kind}_range_max"
            fields[vol.Required(key, default=_or(d.get(key), high))] = _number(
                0, 5000, "any", "mg/L"
            )
        for kind in KINDS:
            key = f"{kind}_stale_days"
            fields[vol.Required(key, default=d.get(key, DEFAULT_STALE_DAYS[kind]))] = _number(
                1, 365, 1, "d"
            )
        return fields

    def _reading_range_error(self, user_input: dict[str, Any]) -> str | None:
        """The first reading whose lowest value is above its highest, or None."""
        for kind in NEW_SENSOR_KINDS:
            low, high = user_input.get(f"{kind}_range_min"), user_input.get(f"{kind}_range_max")
            if low is not None and high is not None and low > high:
                return f"{kind}_range_min"
        return None

    async def async_step_chlorinator_model(self, user_input: dict[str, Any] | None = None):
        _, hardware = await _catalogs(self.hass)
        options = [CUSTOM, *[p["key"] for p in hardware["salt_chlorinators"]]]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CHLORINATOR_MODEL, default=self._data.get(CONF_CHLORINATOR_MODEL) or CUSTOM
                ): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=options,
                        translation_key="catalog_model",
                        mode=sel.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        if user_input is not None:
            model = user_input[CONF_CHLORINATOR_MODEL]
            item = find(hardware, "salt_chlorinators", model)
            if item and model != self._data.get(CONF_CHLORINATOR_MODEL):
                self._data[CONF_CHLORINATOR_NOMINAL_PRODUCTION] = item.get("nominal_production_g_h")
                self._data[CONF_CHLORINATOR_SELF_REGULATING] = bool(item.get("self_regulating"))
                if item.get("min_water_temp_c") is not None:
                    self._data[CONF_CHLORINATOR_MIN_WATER_TEMP] = item["min_water_temp_c"]
                if item.get("salt_ideal_g_l") is not None:
                    self._data[CONF_SALT_TARGET] = item["salt_ideal_g_l"]
            self._data[CONF_CHLORINATOR_MODEL] = None if model == CUSTOM else model
            return await self.async_step_chlorinator()
        return self._form("chlorinator_model", schema)

    async def async_step_chlorinator(self, user_input: dict[str, Any] | None = None):
        d = self._data
        south = float(d.get(CONF_LATITUDE, self.hass.config.latitude) or 0) < 0
        default_months = (
            DEFAULT_CHLORINATOR_ACTIVE_MONTHS_SOUTH if south else DEFAULT_CHLORINATOR_ACTIVE_MONTHS_NORTH
        )
        months = [str(m) for m in (d.get(CONF_CHLORINATOR_ACTIVE_MONTHS) or default_months)]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CHLORINATOR_NOMINAL_PRODUCTION,
                    description=self._sv(CONF_CHLORINATOR_NOMINAL_PRODUCTION),
                ): _number(1, 200, 1, "g/h"),
                vol.Required(
                    CONF_CHLORINATOR_PRODUCTION_DEFAULT,
                    default=d.get(
                        CONF_CHLORINATOR_PRODUCTION_DEFAULT, DEFAULT_CHLORINATOR_PRODUCTION_PCT
                    ),
                ): _number(0, 100, 5, "%", box=False),
                vol.Required(
                    CONF_CHLORINATOR_SELF_REGULATING,
                    default=d.get(CONF_CHLORINATOR_SELF_REGULATING, False),
                ): bool,
                vol.Required(
                    CONF_CHLORINATOR_CONTROLLABLE,
                    default=d.get(CONF_CHLORINATOR_CONTROLLABLE, False),
                ): bool,
                vol.Required(CONF_CHLORINATOR_ACTIVE_MONTHS, default=months): _select(
                    MONTHS, "month", multiple=True
                ),
                vol.Required(
                    CONF_CHLORINATOR_AUTO_TOGGLE, default=d.get(CONF_CHLORINATOR_AUTO_TOGGLE, True)
                ): bool,
                vol.Required(
                    CONF_CHLORINATOR_MIN_WATER_TEMP,
                    default=d.get(CONF_CHLORINATOR_MIN_WATER_TEMP, DEFAULT_CHLORINATOR_MIN_WATER_TEMP),
                ): _number(0, 30, 1, "°C"),
                vol.Required(CONF_SALT_TARGET, default=d.get(CONF_SALT_TARGET, DEFAULT_SALT_TARGET)): _number(
                    1, 10, 0.1, "g/L"
                ),
                vol.Required(
                    CONF_SALT_RANGE_MIN, default=d.get(CONF_SALT_RANGE_MIN, DEFAULT_SALT_RANGE_MIN)
                ): _number(1, 10, 0.1, "g/L"),
                vol.Required(
                    CONF_SALT_RANGE_MAX, default=d.get(CONF_SALT_RANGE_MAX, DEFAULT_SALT_RANGE_MAX)
                ): _number(1, 12, 0.1, "g/L"),
            }
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_CHLORINATOR_ACTIVE_MONTHS):
                errors[CONF_CHLORINATOR_ACTIVE_MONTHS] = "no_months"
            else:
                self._store(schema, user_input)
                self._data[CONF_CHLORINATOR_ACTIVE_MONTHS] = sorted(
                    int(m) for m in self._data[CONF_CHLORINATOR_ACTIVE_MONTHS]
                )
                return await self._after("chlorinator")
        return self._form("chlorinator", schema, errors)

    # ── connections ──

    def _connections_schema(self) -> vol.Schema:
        sv = self._sv
        pump = {
            vol.Required(CONF_PUMP_SWITCH, description=sv(CONF_PUMP_SWITCH)): _entity(
                ["switch", "input_boolean", "light"]
            ),
            vol.Optional(CONF_PUMP_POWER_SENSOR, description=sv(CONF_PUMP_POWER_SENSOR)): _entity(
                ["sensor"], "power"
            ),
            vol.Optional(CONF_PUMP_ENERGY_SENSOR, description=sv(CONF_PUMP_ENERGY_SENSOR)): _entity(
                ["sensor"], "energy"
            ),
            vol.Optional(CONF_HANDS_OFF_ENTITY, description=sv(CONF_HANDS_OFF_ENTITY)): _entity(
                ["input_boolean", "switch", "binary_sensor"]
            ),
        }
        water = {
            vol.Optional(
                CONF_WATER_TEMPERATURE_SENSOR, description=sv(CONF_WATER_TEMPERATURE_SENSOR)
            ): _entity(["sensor"], "temperature"),
            vol.Optional(
                CONF_AIR_TEMPERATURE_SENSOR, description=sv(CONF_AIR_TEMPERATURE_SENSOR)
            ): _entity(["sensor"], "temperature"),
            vol.Optional(CONF_PH_SENSOR, description=sv(CONF_PH_SENSOR)): _entity(["sensor"]),
            vol.Optional(CONF_PH_DOSING_ENTITY, description=sv(CONF_PH_DOSING_ENTITY)): _entity(
                ["binary_sensor", "switch", "input_boolean"]
            ),
            vol.Optional(CONF_ORP_SENSOR, description=sv(CONF_ORP_SENSOR)): _entity(["sensor"]),
            vol.Optional(CONF_SALINITY_SENSOR, description=sv(CONF_SALINITY_SENSOR)): _entity(
                ["sensor"]
            ),
            vol.Optional(
                CONF_FREE_CHLORINE_SENSOR, description=sv(CONF_FREE_CHLORINE_SENSOR)
            ): _entity(["sensor"]),
        }
        room = {
            vol.Optional(
                CONF_FILTER_PRESSURE_SENSOR, description=sv(CONF_FILTER_PRESSURE_SENSOR)
            ): _entity(["sensor"]),
            vol.Optional(
                CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR,
                description=sv(CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR),
            ): _entity(["sensor"], "temperature"),
            vol.Optional(
                CONF_EQUIPMENT_ROOM_HUMIDITY_SENSOR,
                description=sv(CONF_EQUIPMENT_ROOM_HUMIDITY_SENSOR),
            ): _entity(["sensor"], "humidity"),
            vol.Optional(CONF_FLOOD_SENSOR, description=sv(CONF_FLOOD_SENSOR)): _entity(
                ["binary_sensor"]
            ),
        }
        solar = {
            vol.Optional(
                CONF_SOLAR_EXCESS_SENSOR, description=sv(CONF_SOLAR_EXCESS_SENSOR)
            ): _entity(["sensor"], "power"),
            vol.Required(
                CONF_SOLAR_EXCESS_SIGN,
                default=self._data.get(CONF_SOLAR_EXCESS_SIGN) or ExcessSign.EXPORT_POSITIVE,
            ): _select(_values(ExcessSign), "solar_excess_sign"),
            vol.Required(
                CONF_SOLAR_IMPORT_TOLERANCE,
                default=self._data.get(CONF_SOLAR_IMPORT_TOLERANCE, DEFAULT_SOLAR_IMPORT_TOLERANCE_W),
            ): _number(0, 3000, 50, "W"),
        }
        weather = {
            vol.Optional(CONF_WEATHER_ENTITY, description=sv(CONF_WEATHER_ENTITY)): _entity(
                ["weather"]
            ),
            vol.Optional(CONF_UV_SENSOR, description=sv(CONF_UV_SENSOR)): _entity(["sensor"]),
            vol.Optional(CONF_RAIN_SENSOR, description=sv(CONF_RAIN_SENSOR)): _entity(["sensor"]),
        }
        fields: dict[Any, Any] = {
            vol.Required("pump"): section(vol.Schema(pump), {"collapsed": False}),
            vol.Required("water"): section(vol.Schema(water), {"collapsed": False}),
            vol.Required("equipment_room"): section(vol.Schema(room), {"collapsed": True}),
        }
        if self._data.get(CONF_CHLORINATION_TYPE) == ChlorinationType.SALT:
            chlorinator = {
                vol.Optional(
                    CONF_CHLORINATOR_SWITCH, description=sv(CONF_CHLORINATOR_SWITCH)
                ): _entity(["switch", "input_boolean"]),
                vol.Optional(
                    CONF_CHLORINATOR_PRODUCTION_ENTITY,
                    description=sv(CONF_CHLORINATOR_PRODUCTION_ENTITY),
                ): _entity(["number", "input_number", "select", "input_select"]),
            }
            fields[vol.Required("chlorinator")] = section(
                vol.Schema(chlorinator), {"collapsed": False}
            )
        fields[vol.Required("solar")] = section(vol.Schema(solar), {"collapsed": True})
        fields[vol.Required("weather")] = section(vol.Schema(weather), {"collapsed": True})
        return vol.Schema(fields)

    async def async_step_connections(self, user_input: dict[str, Any] | None = None):
        schema = self._connections_schema()
        errors: dict[str, str] = {}
        if user_input is not None:
            flat = _flatten(user_input)
            if flat.get(CONF_CHLORINATOR_SWITCH) and flat.get(CONF_CHLORINATOR_SWITCH) == flat.get(
                CONF_PUMP_SWITCH
            ):
                errors["base"] = "same_switch"
            else:
                self._store(schema, user_input)
                return await self._after("connections")
        return self._form("connections", schema, errors)

    # ── control ──

    async def async_step_control(self, user_input: dict[str, Any] | None = None):
        d = self._data
        sv = self._sv
        schema = vol.Schema(
            {
                vol.Optional(CONF_TIMER_SLOTS, description=sv(CONF_TIMER_SLOTS)): str,
                vol.Required(
                    CONF_MANUAL_OVERRIDE_MINUTES,
                    default=d.get(CONF_MANUAL_OVERRIDE_MINUTES, DEFAULT_MANUAL_OVERRIDE_MINUTES),
                ): _number(5, 1440, 5, "min"),
                vol.Required(
                    CONF_FREEZE_PROTECTION, default=d.get(CONF_FREEZE_PROTECTION, True)
                ): bool,
                vol.Required(
                    CONF_FREEZE_THRESHOLD, default=d.get(CONF_FREEZE_THRESHOLD, DEFAULT_FREEZE_THRESHOLD)
                ): _number(0, 10, 0.5, "°C"),
                vol.Required(
                    CONF_PH_CORRECTION_MINUTES,
                    default=d.get(CONF_PH_CORRECTION_MINUTES, DEFAULT_PH_CORRECTION_MINUTES),
                ): _number(5, 240, 5, "min"),
                vol.Required(
                    CONF_PH_CORRECTION_MAX_DAILY,
                    default=d.get(CONF_PH_CORRECTION_MAX_DAILY, DEFAULT_PH_CORRECTION_MAX_DAILY),
                ): _number(0, 720, 10, "min"),
                vol.Required(
                    CONF_EQUIPMENT_ROOM_MAX_TEMP,
                    default=d.get(CONF_EQUIPMENT_ROOM_MAX_TEMP, DEFAULT_EQUIPMENT_ROOM_MAX_TEMP),
                ): _number(30, 80, 1, "°C"),
                vol.Required(
                    CONF_FILTER_PRESSURE_CRITICAL,
                    default=d.get(CONF_FILTER_PRESSURE_CRITICAL, DEFAULT_FILTER_PRESSURE_CRITICAL),
                ): _number(0.5, 5, 0.1, "bar"),
                vol.Optional(CONF_ENERGY_PRICE, description=sv(CONF_ENERGY_PRICE)): _number(
                    0, 5, 0.001
                ),
                vol.Optional(
                    CONF_ENERGY_PRICE_ENTITY, description=sv(CONF_ENERGY_PRICE_ENTITY)
                ): _entity(["sensor", "input_number"]),
                vol.Optional(CONF_LIGHT_ENTITIES, description=sv(CONF_LIGHT_ENTITIES)): _entity(
                    ["light", "switch"], multiple=True
                ),
                vol.Required(
                    CONF_POOL_CLEANER_TYPE,
                    default=d.get(CONF_POOL_CLEANER_TYPE, PoolCleanerType.NONE),
                ): _select(_values(PoolCleanerType), "pool_cleaner_type"),
                vol.Optional(CONF_ROBOT_ENTITY, description=sv(CONF_ROBOT_ENTITY)): _entity(
                    ["switch", "vacuum", "input_boolean"]
                ),
            }
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            from .coordinator import parse_timer_slots

            slots_text = user_input.get(CONF_TIMER_SLOTS)
            if slots_text and not parse_timer_slots(slots_text):
                errors[CONF_TIMER_SLOTS] = "bad_slots"
            else:
                self._store(schema, user_input)
                return await self._after("control")
        return self._form("control", schema, errors)

    # ── notifications ──

    async def async_step_notifications(self, user_input: dict[str, Any] | None = None):
        d = self._data
        services = sorted(
            f"notify.{name}" for name in self.hass.services.async_services_for_domain("notify")
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_BUILTIN_NOTIFICATIONS,
                    default=d.get(CONF_ENABLE_BUILTIN_NOTIFICATIONS, False),
                ): bool,
                vol.Optional(
                    CONF_NOTIFICATION_SERVICE, description=self._sv(CONF_NOTIFICATION_SERVICE)
                ): sel.SelectSelector(
                    sel.SelectSelectorConfig(
                        options=services, custom_value=True, mode=sel.SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required(
                    CONF_NOTIFICATION_SEVERITY_MIN,
                    default=d.get(CONF_NOTIFICATION_SEVERITY_MIN, DEFAULT_NOTIFICATION_SEVERITY),
                ): _select(_values(Severity), "severity"),
                vol.Optional(
                    CONF_NOTIFICATION_QUIET_HOURS_START,
                    description=self._sv(CONF_NOTIFICATION_QUIET_HOURS_START),
                ): sel.TimeSelector(),
                vol.Optional(
                    CONF_NOTIFICATION_QUIET_HOURS_END,
                    description=self._sv(CONF_NOTIFICATION_QUIET_HOURS_END),
                ): sel.TimeSelector(),
                vol.Required(
                    CONF_CRITICAL_IGNORE_QUIET_HOURS,
                    default=d.get(CONF_CRITICAL_IGNORE_QUIET_HOURS, True),
                ): bool,
            }
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_ENABLE_BUILTIN_NOTIFICATIONS] and not user_input.get(
                CONF_NOTIFICATION_SERVICE
            ):
                errors[CONF_NOTIFICATION_SERVICE] = "service_required"
            else:
                self._store(schema, user_input)
                return await self._after("notifications")
        return self._form("notifications", schema, errors)

    # ── tasks ──

    def _coordinator(self):
        """The running pool, when there is one (the setup wizard has none yet)."""
        return None

    def _last_done_date(self, key: str):
        coordinator = self._coordinator()
        if coordinator is None:
            return None
        done = dt_util.parse_datetime(coordinator.tasks.get(TASKS_BY_KEY[key].action) or "")
        return dt_util.as_local(done).date() if done else None

    async def _record_last_done(self, key: str, day, entry: dict[str, Any]) -> None:
        """Keep a "last done" date, to be taken in when the pool loads."""
        entry["last_done"] = day.isoformat()

    async def async_step_tasks(self, user_input: dict[str, Any] | None = None):
        d = self._data
        stored: dict[str, dict[str, Any]] = d.get("tasks") or {}
        shown = [t for t in TASKS if task_applies(t.key, d)]
        fields: dict[Any, Any] = {}
        for defn in shown:
            key, mine = defn.key, stored.get(defn.key, {})
            fields[
                vol.Required(f"{key}_days", default=mine.get("days", configured_days(defn, d, "swimming")))
            ] = _number(1, 3650, 1, "d")
            if defn.pump_hours is not None:
                fields[
                    vol.Required(
                        f"{key}_pump_hours", default=mine.get("pump_hours", defn.pump_hours)
                    )
                ] = _number(1, 2000, 1, "h")
            if defn.optional:
                fields[
                    vol.Required(
                        f"{key}_enabled", default=mine.get("enabled", defn.enabled_by_default)
                    )
                ] = bool
            last = self._last_done_date(key)
            fields[
                vol.Optional(
                    f"{key}_last_done",
                    description={"suggested_value": last.isoformat()} if last else {},
                )
            ] = sel.DateSelector()
        fields[
            vol.Required(
                CONF_HAS_PH_PROBE_OUTSIDE, default=d.get(CONF_HAS_PH_PROBE_OUTSIDE, False)
            )
        ] = bool
        schema = vol.Schema(fields)
        errors: dict[str, str] = {}
        if user_input is not None:
            today = dt_util.now().date()
            dates = {}
            for defn in shown:
                given = dt_util.parse_date(user_input.get(f"{defn.key}_last_done") or "")
                if given is not None and given > today:
                    errors[f"{defn.key}_last_done"] = "date_in_future"
                if given is not None:
                    dates[defn.key] = given
            if not errors:
                # Only what differs from the default is kept, so a default that
                # depends on the season (the water test in winter) still follows it.
                tasks = dict(stored)
                for defn in shown:
                    key, entry = defn.key, {}
                    days = int(user_input[f"{key}_days"])
                    if days != configured_days(defn, d, "swimming"):
                        entry["days"] = days
                    if defn.pump_hours is not None:
                        hours = float(user_input[f"{key}_pump_hours"])
                        if hours != defn.pump_hours:
                            entry["pump_hours"] = hours
                    if defn.optional:
                        enabled = bool(user_input[f"{key}_enabled"])
                        if enabled != defn.enabled_by_default:
                            entry["enabled"] = enabled
                    if key in dates and dates[key] != self._last_done_date(key):
                        await self._record_last_done(key, dates[key], entry)
                    if entry:
                        tasks[key] = entry
                    else:
                        tasks.pop(key, None)
                d["tasks"] = tasks
                d[CONF_HAS_PH_PROBE_OUTSIDE] = bool(user_input[CONF_HAS_PH_PROBE_OUTSIDE])
                return await self._after("tasks")
        return self._form("tasks", schema, errors)


class HomePoolConfigFlow(_Wizard, ConfigFlow, domain=DOMAIN):
    """Set up a pool, one group of questions at a time."""

    VERSION = CONFIG_VERSION

    ORDER = (
        "identity",
        "geometry",
        "construction",
        "filtration",
        "water",
        "chlorinator",
        "connections",
        "control",
        "notifications",
        "tasks",
    )

    def __init__(self) -> None:
        self._data = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        return await self.async_step_identity(user_input)

    async def _after(self, step: str) -> ConfigFlowResult:
        nxt = self.ORDER[self.ORDER.index(step) + 1] if step != self.ORDER[-1] else None
        if nxt == "chlorinator" and self._data.get(CONF_CHLORINATION_TYPE) != ChlorinationType.SALT:
            nxt = "connections"
        if nxt is None:
            return self.async_create_entry(title=self._data[CONF_POOL_NAME], data=self._data)
        return await {
            "geometry": self.async_step_shape,
            "construction": self.async_step_construction,
            "filtration": self.async_step_pump,
            "water": self.async_step_water,
            "chlorinator": self.async_step_chlorinator_model,
            "connections": self.async_step_connections,
            "control": self.async_step_control,
            "notifications": self.async_step_notifications,
            "tasks": self.async_step_tasks,
        }[nxt]()

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return HomePoolOptionsFlow()


class HomePoolOptionsFlow(_Wizard, OptionsFlow):
    """Edit one group at a time from a menu."""

    def __init__(self) -> None:
        self._data = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        self._data = {**self.config_entry.data, **self.config_entry.options}
        menu = ["identity", "shape", "construction", "pump", "water"]
        if self._data.get(CONF_CHLORINATION_TYPE) == ChlorinationType.SALT:
            menu.append("chlorinator_model")
        menu += ["connections", "control", "notifications", "tasks"]
        return self.async_show_menu(step_id="init", menu_options=menu)

    def _coordinator(self):
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return None
        return self.config_entry.runtime_data

    async def _record_last_done(self, key: str, day, entry: dict[str, Any]) -> None:
        coordinator = self._coordinator()
        if coordinator is None:
            await super()._record_last_done(key, day, entry)
        else:
            await coordinator.async_complete_task(key, day)

    async def _after(self, step: str) -> ConfigFlowResult:
        if step == "water" and self._data.get(CONF_CHLORINATION_TYPE) == ChlorinationType.SALT and (
            not self._data.get(CONF_CHLORINATOR_NOMINAL_PRODUCTION)
        ):
            # Switched to salt just now: the chlorinator needs describing too.
            return await self.async_step_chlorinator_model()
        return self.async_create_entry(data=self._data)
