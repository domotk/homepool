"""Constants for the HomePool integration."""

from __future__ import annotations

from enum import StrEnum

DOMAIN = "homepool"
PLATFORMS = [
    "binary_sensor",
    "button",
    "number",
    "select",
    "sensor",
    "switch",
]

CONFIG_VERSION = 1
STORAGE_VERSION = 1

# ──────────────────────────────────────────────
# Configuration keys
# ──────────────────────────────────────────────

# Identity and location
CONF_POOL_NAME = "name"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"

# Geometry
CONF_SHAPE = "shape"
CONF_SIDE = "side"
CONF_LENGTH = "length"
CONF_WIDTH = "width"
CONF_DIAMETER = "diameter"
CONF_LENGTH_1 = "length_1"
CONF_WIDTH_1 = "width_1"
CONF_LENGTH_2 = "length_2"
CONF_WIDTH_2 = "width_2"
CONF_DEPTH_MIN = "depth_min"
CONF_DEPTH_MAX = "depth_max"
CONF_LAYOUT_VARIANT = "layout_variant"
CONF_LAYOUT_ORIENTATION = "layout_orientation"
CONF_VOLUME_OVERRIDE = "volume_override"
CONF_VOLUME = "volume"  # the volume actually used, stored once confirmed

DIMENSION_KEYS = {
    "square": (CONF_SIDE,),
    "rectangular": (CONF_LENGTH, CONF_WIDTH),
    "oval": (CONF_LENGTH, CONF_WIDTH),
    "round": (CONF_DIAMETER,),
    "kidney": (CONF_LENGTH, CONF_WIDTH),
    "l_shape": (CONF_LENGTH_1, CONF_WIDTH_1, CONF_LENGTH_2, CONF_WIDTH_2),
}

# Construction and environment
CONF_CONSTRUCTION_TYPE = "construction_type"
CONF_HAS_COVER = "has_cover"
CONF_COVER_ENTITY = "cover_entity"
CONF_HAS_HEATING = "has_heating"
CONF_HEATING_TYPE = "heating_type"
CONF_HEATING_ENTITY = "heating_entity"
CONF_IS_COVERED_BY_ROOF = "is_covered_by_roof"
CONF_ORIENTATION = "orientation"
CONF_LINER_TYPE = "liner_type"
CONF_LINER_COLOR = "liner_color"

# Filtration
CONF_PUMP_MODEL = "pump_model"
CONF_PUMP_SPEED_TYPE = "pump_speed_type"
CONF_PUMP_NOMINAL_FLOW_RATE = "pump_nominal_flow_rate"
CONF_PUMP_NOMINAL_POWER = "pump_nominal_power"
CONF_SKIMMERS_COUNT = "skimmers_count"
CONF_HAS_AUTOFILL_SKIMMER = "has_autofill_skimmer"
CONF_RETURNS_COUNT = "returns_count"
CONF_FILTER_TYPE = "filter_type"
CONF_FILTER_PRESSURE_NORMAL_MIN = "filter_pressure_normal_min"
CONF_FILTER_PRESSURE_NORMAL_MAX = "filter_pressure_normal_max"
CONF_BACKWASH_INTERVAL_DAYS = "backwash_interval_days"

# Water treatment
CONF_CHLORINATION_TYPE = "chlorination_type"
CONF_PH_TARGET = "ph_target"
CONF_PH_RANGE_MIN = "ph_range_min"
CONF_PH_RANGE_MAX = "ph_range_max"
CONF_PH_CALIBRATION_INTERVAL_DAYS = "ph_calibration_interval_days"
CONF_HAS_PH_DOSING = "has_ph_dosing"
CONF_HAS_PH_PROBE_OUTSIDE = "has_ph_probe_outside"
CONF_FREE_CHLORINE_TARGET = "free_chlorine_target"
CONF_FREE_CHLORINE_RANGE_MIN = "free_chlorine_range_min"
CONF_FREE_CHLORINE_RANGE_MAX = "free_chlorine_range_max"

# Salt chlorinator
CONF_CHLORINATOR_MODEL = "chlorinator_model"
CONF_SALT_TARGET = "salt_target"
CONF_SALT_RANGE_MIN = "salt_range_min"
CONF_SALT_RANGE_MAX = "salt_range_max"
CONF_CHLORINATOR_NOMINAL_PRODUCTION = "chlorinator_nominal_production"
CONF_CHLORINATOR_PRODUCTION_DEFAULT = "chlorinator_production_default"
CONF_CHLORINATOR_CONTROLLABLE = "chlorinator_controllable"
CONF_CHLORINATOR_SELF_REGULATING = "chlorinator_self_regulating"
CONF_CHLORINATOR_ACTIVE_MONTHS = "chlorinator_active_months"
CONF_CHLORINATOR_AUTO_TOGGLE = "chlorinator_auto_toggle"
# The months the pool is used, for every pool: what the season state follows.
CONF_SWIMMING_MONTHS = "swimming_months"
CONF_WINTER_PRODUCT_TYPE = "winter_product_type"
CONF_WINTER_PRODUCT_DOSE_PER_M3 = "winter_product_dose_per_m3"
CONF_WINTER_PRODUCT_INTERVAL_DAYS = "winter_product_interval_days"
CONF_CHLORINATOR_MIN_WATER_TEMP = "chlorinator_min_water_temp"

# Lighting and auxiliary
CONF_LIGHT_ENTITIES = "light_entities"
CONF_POOL_CLEANER_TYPE = "pool_cleaner_type"
CONF_ROBOT_ENTITY = "robot_entity"
CONF_ROBOT_CYCLE_HOURS = "robot_cycle_hours"

# Connected entities
CONF_PUMP_SWITCH = "pump_switch"
CONF_PUMP_POWER_SENSOR = "pump_power_sensor"
CONF_PUMP_ENERGY_SENSOR = "pump_energy_sensor"
CONF_HANDS_OFF_ENTITY = "hands_off_entity"
CONF_PH_SENSOR = "ph_sensor"
CONF_PH_DOSING_ENTITY = "ph_dosing_entity"
CONF_WATER_TEMPERATURE_SENSOR = "water_temperature_sensor"
CONF_AIR_TEMPERATURE_SENSOR = "air_temperature_sensor"
CONF_SALINITY_SENSOR = "salinity_sensor"
CONF_ORP_SENSOR = "orp_sensor"
CONF_FREE_CHLORINE_SENSOR = "free_chlorine_sensor"
CONF_FILTER_PRESSURE_SENSOR = "filter_pressure_sensor"
CONF_EQUIPMENT_ROOM_TEMPERATURE_SENSOR = "equipment_room_temperature_sensor"
CONF_EQUIPMENT_ROOM_HUMIDITY_SENSOR = "equipment_room_humidity_sensor"
CONF_FLOOD_SENSOR = "flood_sensor"
CONF_CHLORINATOR_SWITCH = "chlorinator_switch"
CONF_CHLORINATOR_PRODUCTION_ENTITY = "chlorinator_production_entity"
CONF_SOLAR_EXCESS_SENSOR = "solar_excess_sensor"
CONF_SOLAR_EXCESS_SIGN = "solar_excess_sign"
CONF_SOLAR_IMPORT_TOLERANCE = "solar_import_tolerance"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_UV_SENSOR = "uv_sensor"
CONF_RAIN_SENSOR = "rain_sensor"

# Energy
CONF_ENERGY_PRICE = "energy_price"
CONF_ENERGY_PRICE_ENTITY = "energy_price_entity"

# Control behaviour
CONF_TIMER_SLOTS = "timer_slots"
CONF_MANUAL_OVERRIDE_MINUTES = "manual_override_minutes"
CONF_FREEZE_PROTECTION = "freeze_protection"
CONF_FREEZE_THRESHOLD = "freeze_threshold"
CONF_EQUIPMENT_ROOM_MAX_TEMP = "equipment_room_max_temp"
CONF_FILTER_PRESSURE_CRITICAL = "filter_pressure_critical"
CONF_PH_CORRECTION_MINUTES = "ph_correction_minutes"
CONF_PH_CORRECTION_MAX_DAILY = "ph_correction_max_daily"

# Notifications
CONF_ENABLE_BUILTIN_NOTIFICATIONS = "enable_builtin_notifications"
CONF_NOTIFICATION_SERVICE = "notification_service"
CONF_NOTIFICATION_SEVERITY_MIN = "notification_severity_min"
CONF_NOTIFICATION_QUIET_HOURS_START = "notification_quiet_hours_start"
CONF_NOTIFICATION_QUIET_HOURS_END = "notification_quiet_hours_end"
CONF_CRITICAL_IGNORE_QUIET_HOURS = "critical_ignore_quiet_hours"


# ──────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────


class PoolShape(StrEnum):
    SQUARE = "square"
    RECTANGULAR = "rectangular"
    OVAL = "oval"
    ROUND = "round"
    KIDNEY = "kidney"
    L_SHAPE = "l_shape"


class ConstructionType(StrEnum):
    BUILT_IN = "built_in"
    PREFAB = "prefab"
    ABOVE_GROUND = "above_ground"


class CoverType(StrEnum):
    NONE = "none"
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class HeatingType(StrEnum):
    NONE = "none"
    HEAT_PUMP = "heat_pump"
    HEAT_EXCHANGER = "heat_exchanger"
    SOLAR_THERMAL = "solar_thermal"
    ELECTRIC = "electric"
    OTHER = "other"


class Orientation(StrEnum):
    NOT_SPECIFIED = "not_specified"
    NORTH = "north"
    NORTHEAST = "northeast"
    EAST = "east"
    SOUTHEAST = "southeast"
    SOUTH = "south"
    SOUTHWEST = "southwest"
    WEST = "west"
    NORTHWEST = "northwest"


class LinerType(StrEnum):
    NOT_SPECIFIED = "not_specified"
    TILE = "tile"
    POLYESTER = "polyester"
    LINER = "liner"
    PAINTED_CONCRETE = "painted_concrete"
    NATURAL_STONE = "natural_stone"
    FIBERGLASS = "fiberglass"


class LinerColor(StrEnum):
    WHITE = "white"
    LIGHT_BLUE = "light_blue"
    BLUE = "blue"
    DARK_BLUE = "dark_blue"
    GREEN = "green"
    SAND = "sand"
    GREY = "grey"
    BLACK = "black"


class PumpSpeedType(StrEnum):
    FIXED = "fixed"
    VARIABLE = "variable"


class FilterType(StrEnum):
    SAND = "sand"
    GLASS = "glass"
    CARTRIDGE = "cartridge"
    DIATOMACEOUS_EARTH = "diatomaceous_earth"
    OTHER = "other"


class ChlorinationType(StrEnum):
    SALT = "salt"
    TABLETS = "tablets"
    LIQUID = "liquid"
    OTHER = "other"


class PoolCleanerType(StrEnum):
    NONE = "none"
    CABLE_ELECTRIC = "cable_electric"
    BATTERY = "battery"
    HYDRAULIC = "hydraulic"


class OperationMode(StrEnum):
    OFF = "off"
    TIMER = "timer"
    SMART = "smart"
    SOLAR = "solar"
    SMART_SOLAR = "smart_solar"


class ExcessSign(StrEnum):
    """How the excess sensor reports a surplus."""

    EXPORT_POSITIVE = "export_positive"  # a grid meter: export > 0, import < 0
    IMPORT_POSITIVE = "import_positive"  # a grid meter: import > 0, export < 0
    SURPLUS = "surplus"  # already a surplus figure, never negative


class OverallStatus(StrEnum):
    OK = "ok"
    ATTENTION = "attention"
    ACTION_REQUIRED = "action_required"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}


class ChlorinationMode(StrEnum):
    SALT = "salt"
    TABLETS = "tablets"
    OFF = "off"
    WINTER_PRODUCT = "winter_product"


class ManualAction(StrEnum):
    BACKWASH = "backwash"
    FILTER_CLEANED = "filter_cleaned"
    SALT_ADDED = "salt_added"
    PH_CALIBRATED = "ph_calibrated"
    CHLORINE_ADDED = "chlorine_added"
    PH_ADJUSTED = "ph_adjusted"
    WATER_ADDED = "water_added"
    CELL_CLEANED = "cell_cleaned"
    WINTER_PRODUCT_ADDED = "winter_product_added"
    WATER_TESTED = "water_tested"
    SKIMMER_BASKETS_EMPTIED = "skimmer_baskets_emptied"
    FILTER_MEDIA_CHECKED = "filter_media_checked"
    OTHER = "other"


class PhTrend(StrEnum):
    RISING = "rising"
    STABLE = "stable"
    FALLING = "falling"


class ControlSource(StrEnum):
    """Who decided the pump's current state: shown on the control sensor."""

    HANDS_OFF = "hands_off"
    MAINTENANCE_LOCK = "maintenance_lock"
    SAFETY = "safety"
    FREEZE_PROTECTION = "freeze_protection"
    PH_CORRECTION = "ph_correction"
    MANUAL_CYCLE = "manual_cycle"
    MANUAL_OVERRIDE = "manual_override"
    MODE = "mode"
    UNAVAILABLE = "unavailable"


# ──────────────────────────────────────────────
# Defaults
# ──────────────────────────────────────────────

DEFAULT_NAME = "Pool"
DEFAULT_PH_TARGET = 7.4
DEFAULT_PH_RANGE_MIN = 7.2
DEFAULT_PH_RANGE_MAX = 7.6
DEFAULT_FREE_CHLORINE_TARGET = 1.5
DEFAULT_FREE_CHLORINE_RANGE_MIN = 1.0
DEFAULT_FREE_CHLORINE_RANGE_MAX = 3.0
DEFAULT_SALT_TARGET = 4.0
DEFAULT_SALT_RANGE_MIN = 3.0
DEFAULT_SALT_RANGE_MAX = 5.5
DEFAULT_CHLORINATOR_PRODUCTION_PCT = 50
DEFAULT_CHLORINATOR_MIN_WATER_TEMP = 15.0
DEFAULT_FILTER_PRESSURE_NORMAL_MIN = 0.6
DEFAULT_FILTER_PRESSURE_NORMAL_MAX = 1.2
DEFAULT_FILTER_PRESSURE_CRITICAL = 2.0
DEFAULT_SKIMMERS_COUNT = 1
DEFAULT_RETURNS_COUNT = 2
DEFAULT_ROBOT_CYCLE_HOURS = 2.0
DEFAULT_USER_MULTIPLIER = 1.0
DEFAULT_BACKWASH_INTERVAL_DAYS = 14
DEFAULT_WINTER_PRODUCT_DOSE_PER_M3 = 0.02  # one floater for 50 m³
DEFAULT_WINTER_PRODUCT_INTERVAL_DAYS = 56
DEFAULT_PH_CALIBRATION_INTERVAL_DAYS = 180
DEFAULT_MANUAL_OVERRIDE_MINUTES = 120
DEFAULT_FREEZE_THRESHOLD = 2.0
DEFAULT_EQUIPMENT_ROOM_MAX_TEMP = 50.0
DEFAULT_PH_CORRECTION_MINUTES = 30
DEFAULT_PH_CORRECTION_MAX_DAILY = 120
# While the pump runs on surplus, this much import is tolerated before it
# counts as no surplus: houses have short peaks (an oven, a kettle) in the
# middle of a sunny day, and following each one would cycle the motor.
DEFAULT_SOLAR_IMPORT_TOLERANCE_W = 400
DEFAULT_NOTIFICATION_SEVERITY = "warning"

DEFAULT_CHLORINATOR_ACTIVE_MONTHS_NORTH = [6, 7, 8, 9]
DEFAULT_CHLORINATOR_ACTIVE_MONTHS_SOUTH = [12, 1, 2, 3]

DEFAULT_OPERATION_MODE = OperationMode.OFF

# ──────────────────────────────────────────────
# Control loop tuning
# ──────────────────────────────────────────────

# How often the controller re-evaluates, besides reacting to state changes.
EVALUATION_INTERVAL_S = 60
# A pump that has just changed state is left alone for this long, unless
# something with higher authority (lock, safety) asks otherwise. Relays and
# motors both last longer when they are not cycled every minute.
MIN_ON_MINUTES = 20
MIN_OFF_MINUTES = 10
# Solar has to hold for this long before the pump follows it. The real
# November traces this was tuned against have clouds that cut the surplus for
# five to ten minutes at a time.
SOLAR_START_DELAY_MIN = 5
SOLAR_STOP_DELAY_MIN = 10
# The salt cell is only allowed on once water has been flowing for this long.
CHLORINATOR_FLOW_DELAY_S = 120
# A switch that has not reached the commanded state after this long gets the
# command again. Some relays reject the first request after a while idle.
COMMAND_RETRY_S = 20
COMMAND_MAX_ATTEMPTS = 3
# How far before the end of the day a guaranteed mode must have finished.
END_OF_DAY_MARGIN_MIN = 10
# Target recalculation: how often, and how much it may change at once.
RECALC_INTERVAL_MIN = 60
# Filtration days kept in the store, for the card's history and diagnostics.
HISTORY_DAYS = 30

# ──────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────

EVENT_ALERT = f"{DOMAIN}_alert"
EVENT_SAFETY_SHUTOFF = f"{DOMAIN}_safety_shutoff"
EVENT_TARGET_RECALCULATED = f"{DOMAIN}_target_recalculated"
EVENT_MANUAL_ACTION_DUE = f"{DOMAIN}_manual_action_due"
EVENT_CHLORINATOR_SEASON_START = f"{DOMAIN}_chlorinator_season_start"
EVENT_CHLORINATOR_SEASON_END = f"{DOMAIN}_chlorinator_season_end"
EVENT_SEASON_PROPOSAL = f"{DOMAIN}_season_proposal"
EVENT_SEASON_STATE_CHANGED = f"{DOMAIN}_season_state_changed"

# ──────────────────────────────────────────────
# Services
# ──────────────────────────────────────────────

SERVICE_START_CYCLE = "start_cycle"
SERVICE_STOP_CYCLE = "stop_cycle"
SERVICE_RECORD_MANUAL_ACTION = "record_manual_action"
SERVICE_RECORD_SALT_LEVEL = "record_salt_level"
SERVICE_RECORD_FREE_CHLORINE = "record_free_chlorine"
SERVICE_RECORD_READING = "record_reading"
SERVICE_RECALCULATE = "recalculate_schedule"
SERVICE_FORCE_PH_WINDOW = "force_ph_correction_window"
SERVICE_RESET_DAILY = "reset_daily_counters"
SERVICE_COMPLETE_TASK = "complete_task"
SERVICE_SET_SEASON_STATE = "set_season_state"
SERVICE_DISMISS_SEASON_PROPOSAL = "dismiss_season_proposal"
SERVICE_COMPLETE_STEP = "complete_step"
SERVICE_DISMISS_CHECKLIST = "dismiss_checklist"

ATTR_DURATION = "duration"
ATTR_ACTION_TYPE = "action_type"
ATTR_VALUE = "value"
ATTR_KIND = "kind"
ATTR_NOTES = "notes"
ATTR_TASK = "task"
ATTR_DATE = "date"
ATTR_STATE = "state"
ATTR_STEP = "step"
ATTR_CHECKLIST = "checklist"
