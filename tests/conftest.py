"""Pytest configuration for HomePool tests.

Adds the project root to sys.path and mocks homeassistant
so that pool/ pure-Python modules can be tested without
a full Home Assistant installation.
"""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Mock homeassistant and its submodules so that importing
# custom_components.homepool doesn't fail in test environments
# where HA is not installed. This only affects the HA glue code;
# the pool/ modules are pure Python and don't need HA.
_HA_MODULES = [
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.core",
    "homeassistant.data_entry_flow",
    "homeassistant.helpers",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.entity_platform",
]
for mod_name in _HA_MODULES:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Also mock voluptuous which is used in config_flow
if "voluptuous" not in sys.modules:
    vol_mock = MagicMock()
    vol_mock.Schema = MagicMock(return_value=MagicMock())
    vol_mock.Required = MagicMock(return_value="required")
    vol_mock.Optional = MagicMock(return_value="optional")
    sys.modules["voluptuous"] = vol_mock
