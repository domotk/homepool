"""Constants for the HomePool integration."""

from enum import StrEnum

DOMAIN = "homepool"
PLATFORMS = [
    "sensor",
    "binary_sensor",
    "switch",
    "select",
    "number",
    "button",
]

# ──────────────────────────────────────────────
# Config flow field keys
# ──────────────────────────────────────────────

# Step 1 - Identity
CONF_POOL_NAME = "name"

# Step 2 - Location
CONF_LOCATION_SOURCE = "location_source"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"

# Step 3 - Geometry
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

# Step 4 - Construction & Environment
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

# Step 5 - Filtration System
CONF_USE_PUMP_CATALOG = "use_pump_catalog"
CONF_PUMP_BRAND = "pump_brand"
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

# Step 6 - Water Treatment
CONF_CHLORINATION_TYPE = "chlorination_type"
CONF_PH_TARGET = "ph_target"
CONF_PH_RANGE_MIN = "ph_range_min"
CONF_PH_RANGE_MAX = "ph_range_max"
CONF_FREE_CHLORINE_TARGET = "free_chlorine_target"
CONF_FREE_CHLORINE_RANGE_MIN = "free_chlorine_range_min"
CONF_FREE_CHLORINE_RANGE_MAX = "free_chlorine_range_max"
CONF_SALT_TARGET = "salt_target"
CONF_SALT_RANGE_MIN = "salt_range_min"
CONF_SALT_RANGE_MAX = "salt_range_max"
CONF_CHLORINATOR_NOMINAL_PRODUCTION = "chlorinator_nominal_production"
CONF_CHLORINATOR_PRODUCTION_DEFAULT = "chlorinator_production_default"
CONF_CHLORINATOR_CONTROLLABLE = "chlorinator_controllable"
CONF_CHLORINATOR_SELF_REGULATING = "chlorinator_self_regulating"
CONF_CHLORINATOR_ACTIVE_MONTHS = "chlorinator_active_months"
CONF_CHLORINATOR_AUTO_TOGGLE = "chlorinator_auto_toggle"

# Step 7 - Lighting & Auxiliary
CONF_LIGHT_GROUPS = "light_groups"
CONF_POOL_CLEANER_TYPE = "pool_cleaner_type"
CONF_ROBOT_ENTITY = "robot_entity"
CONF_ROBOT_CYCLE_HOURS = "robot_cycle_hours"

# Step 8 - Entity connections
CONF_PUMP_SWITCH = "pump_switch"
CONF_PUMP_POWER_SENSOR = "pump_power_sensor"
CONF_PUMP_ENERGY_SENSOR = "pump_energy_sensor"
CONF_PH_SENSOR = "ph_sensor"
CONF_WATER_TEMPERATURE_SENSOR = "water_temperature_sensor"
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
CONF_SOLAR_FORECAST_ENTITY = "solar_forecast_entity"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_UV_SENSOR = "uv_sensor"

# Step 10 - Notifications
CONF_ENABLE_BUILTIN_NOTIFICATIONS = "enable_builtin_notifications"
CONF_NOTIFICATION_SERVICE = "notification_service"
CONF_NOTIFICATION_SEVERITY_MIN = "notification_severity_min"
CONF_NOTIFICATION_QUIET_HOURS_START = "notification_quiet_hours_start"
CONF_NOTIFICATION_QUIET_HOURS_END = "notification_quiet_hours_end"
CONF_CRITICAL_IGNORE_QUIET_HOURS = "critical_ignore_quiet_hours"


# ──────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────

class LocationSource(StrEnum):
    HOME_ASSISTANT = "home_assistant"
    MANUAL = "manual"


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
    HEAT_PUMP = "heat_pump"
    HEAT_EXCHANGER = "heat_exchanger"
    SOLAR_THERMAL = "solar_thermal"
    ELECTRIC = "electric"
    OTHER = "other"


class Orientation(StrEnum):
    NORTH = "north"
    NORTHEAST = "northeast"
    EAST = "east"
    SOUTHEAST = "southeast"
    SOUTH = "south"
    SOUTHWEST = "southwest"
    WEST = "west"
    NORTHWEST = "northwest"
    NOT_SPECIFIED = "not_specified"


class LinerType(StrEnum):
    TILE = "tile"
    POLYESTER = "polyester"
    LINER = "liner"
    PAINTED_CONCRETE = "painted_concrete"
    NATURAL_STONE = "natural_stone"
    FIBERGLASS = "fiberglass"
    NOT_SPECIFIED = "not_specified"


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
    CARTRIDGE = "cartridge"
    DIATOMACEOUS_EARTH = "diatomaceous_earth"
    GLASS = "glass"
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


class LightLocation(StrEnum):
    UNDERWATER = "underwater"
    PERIMETER = "perimeter"


class OperationMode(StrEnum):
    OFF = "off"
    TIMER = "timer"
    SMART = "smart"
    SOLAR = "solar"
    SMART_SOLAR = "smart_solar"


class OverallStatus(StrEnum):
    OK = "ok"
    ATTENTION = "attention"
    ACTION_REQUIRED = "action_required"


class NotificationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ChlorinationMode(StrEnum):
    SALT = "salt"
    TABLETS = "tablets"
    OFF = "off"


class LayoutOrientation(StrEnum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


# ──────────────────────────────────────────────
# Default values
# ──────────────────────────────────────────────

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
DEFAULT_FILTER_PRESSURE_NORMAL_MIN = 0.6
DEFAULT_FILTER_PRESSURE_NORMAL_MAX = 1.2
DEFAULT_SKIMMERS_COUNT = 1
DEFAULT_RETURNS_COUNT = 2
DEFAULT_ROBOT_CYCLE_HOURS = 2.0
DEFAULT_USER_MULTIPLIER = 1.0
DEFAULT_SOLAR_EXCESS_THRESHOLD_W = 500

# Chlorinator calendar defaults (hemisphere north)
DEFAULT_CHLORINATOR_ACTIVE_MONTHS_NORTH = [6, 7, 8, 9]  # Jun-Sep
DEFAULT_CHLORINATOR_ACTIVE_MONTHS_SOUTH = [12, 1, 2, 3]  # Dec-Mar

# Operation
DEFAULT_OPERATION_MODE = OperationMode.OFF
DEFAULT_PH_CORRECTION_MIN_MINUTES = 30

# Filtration algorithm
FILTRATION_BASE_TURNOVERS = 2
FILTRATION_MIN_TURNOVERS = 1
FILTRATION_MAX_TURNOVERS = 7
AIR_TO_WATER_TEMP_OFFSET_C = -2.0
