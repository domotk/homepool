"""Config flow for HomePool integration.

Multi-step config flow with conditional branching.
All fields are also available in the options flow after setup.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_POOL_NAME

_LOGGER = logging.getLogger(__name__)


class HomePoolConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HomePool."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1 — Identity."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_location()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_POOL_NAME, default="Pool"): str,
            }),
            errors=errors,
        )

    async def async_step_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2 — Location."""
        # TODO: Implement LocationSelector + manual coordinates
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_geometry()

        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema({}),  # TODO: Add location fields
        )

    async def async_step_geometry(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3 — Geometry (shape, dimensions, layout)."""
        # TODO: Implement shape selection, dimensions, layout variant
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_geometry_confirm()

        return self.async_show_form(
            step_id="geometry",
            data_schema=vol.Schema({}),  # TODO: Add geometry fields
        )

    async def async_step_geometry_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3b — Confirm calculated volume."""
        # TODO: Show calculated volume, allow override
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_construction()

        return self.async_show_form(
            step_id="geometry_confirm",
            data_schema=vol.Schema({}),  # TODO: Volume confirmation
        )

    async def async_step_construction(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4 — Construction & Environment."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_filtration()

        return self.async_show_form(
            step_id="construction",
            data_schema=vol.Schema({}),  # TODO: Add fields
        )

    async def async_step_filtration(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 5 — Filtration System."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_water_treatment()

        return self.async_show_form(
            step_id="filtration",
            data_schema=vol.Schema({}),  # TODO: Add fields
        )

    async def async_step_water_treatment(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 6 — Water Treatment."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_lighting()

        return self.async_show_form(
            step_id="water_treatment",
            data_schema=vol.Schema({}),  # TODO: Add fields
        )

    async def async_step_lighting(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 7 — Lighting & Auxiliary Elements."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_connect_core()

        return self.async_show_form(
            step_id="lighting",
            data_schema=vol.Schema({}),  # TODO: Add fields
        )

    # --- Step 8 sub-steps: Entity connections ---

    async def async_step_connect_core(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 8a — Core equipment (pump switch, required)."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_connect_pump_monitoring()

        return self.async_show_form(
            step_id="connect_core",
            data_schema=vol.Schema({}),  # TODO: pump_switch EntitySelector
        )

    async def async_step_connect_pump_monitoring(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 8b — Pump monitoring (optional)."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_connect_water_chemistry()

        return self.async_show_form(
            step_id="connect_pump_monitoring",
            data_schema=vol.Schema({}),  # TODO: Add fields
        )

    async def async_step_connect_water_chemistry(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 8c — Water chemistry sensors (optional)."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_connect_filter()

        return self.async_show_form(
            step_id="connect_water_chemistry",
            data_schema=vol.Schema({}),  # TODO: Add fields
        )

    async def async_step_connect_filter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 8d — Filter monitoring (optional)."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_connect_equipment_room()

        return self.async_show_form(
            step_id="connect_filter",
            data_schema=vol.Schema({}),  # TODO: Add fields
        )

    async def async_step_connect_equipment_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 8e — Equipment room sensors (optional)."""
        if user_input is not None:
            self._data.update(user_input)
            # Skip chlorinator step if not salt
            if self._data.get("chlorination_type") == "salt":
                return await self.async_step_connect_chlorinator()
            return await self.async_step_connect_solar()

        return self.async_show_form(
            step_id="connect_equipment_room",
            data_schema=vol.Schema({}),  # TODO: Add fields
        )

    async def async_step_connect_chlorinator(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 8f — Salt chlorinator control (only if salt)."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_connect_solar()

        return self.async_show_form(
            step_id="connect_chlorinator",
            data_schema=vol.Schema({}),  # TODO: Add fields
        )

    async def async_step_connect_solar(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 8g — Solar integration (optional)."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_connect_weather()

        return self.async_show_form(
            step_id="connect_solar",
            data_schema=vol.Schema({}),  # TODO: Add fields
        )

    async def async_step_connect_weather(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 8h — Weather integration (optional)."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_notifications()

        return self.async_show_form(
            step_id="connect_weather",
            data_schema=vol.Schema({}),  # TODO: Add fields
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 10 — Notifications (optional)."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_review()

        return self.async_show_form(
            step_id="notifications",
            data_schema=vol.Schema({}),  # TODO: Add fields
        )

    async def async_step_review(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 9 — Review & Finish."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._data.get(CONF_POOL_NAME, "Pool"),
                data=self._data,
            )

        return self.async_show_form(
            step_id="review",
            data_schema=vol.Schema({}),  # TODO: Show summary
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HomePoolOptionsFlow:
        """Get the options flow handler."""
        return HomePoolOptionsFlow(config_entry)


class HomePoolOptionsFlow(config_entries.OptionsFlow):
    """Handle HomePool options — all config fields editable post-setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Options flow entry point."""
        # TODO: Present all configurable options organized by category
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),  # TODO: All editable options
        )
