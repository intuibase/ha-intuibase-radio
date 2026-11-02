"""Configuration flow for Polish Internet Radio."""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CREATE_DASHBOARD,
    CONF_DASHBOARD_NAME,
    CONF_EXCLUDED_PLAYERS,
    CONF_STATIONS,
    DEFAULT_DASHBOARD_NAME,
    DOMAIN,
    STATIONS,
)
from .stations import format_stations, parse_stations


def _station_field(default: str) -> dict:
    return {
        vol.Required(CONF_STATIONS, default=default): selector.TextSelector(
            selector.TextSelectorConfig(multiline=True)
        )
    }


class InternetRadioConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the single radio controller."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return InternetRadioOptionsFlow()

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Set up from the integrations screen."""
        errors = {}
        values = user_input or {}
        if user_input is not None:
            try:
                stations = parse_stations(user_input[CONF_STATIONS])
            except ValueError:
                errors[CONF_STATIONS] = "invalid_stations"
        if user_input is not None and not errors:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="IntuiBase Radio",
                data={},
                options={**user_input, CONF_STATIONS: stations},
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    **_station_field(
                        user_input[CONF_STATIONS] if user_input is not None
                        else format_stations(STATIONS)
                    ),
                    vol.Optional(
                        CONF_CREATE_DASHBOARD,
                        default=values.get(CONF_CREATE_DASHBOARD, True),
                    ): bool,
                    vol.Optional(
                        CONF_DASHBOARD_NAME,
                        default=values.get(CONF_DASHBOARD_NAME, DEFAULT_DASHBOARD_NAME),
                    ): str,
                    vol.Optional(
                        CONF_EXCLUDED_PLAYERS,
                        default=values.get(CONF_EXCLUDED_PLAYERS, []),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="media_player", multiple=True
                        )
                    ),
                }
            ),
            errors=errors,
        )


class InternetRadioOptionsFlow(config_entries.OptionsFlowWithReload):
    """Edit the station catalogue and dashboard after installation."""

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        errors = {}
        values = {**self.config_entry.options, **(user_input or {})}
        if user_input is not None:
            try:
                stations = parse_stations(user_input[CONF_STATIONS])
            except ValueError:
                errors[CONF_STATIONS] = "invalid_stations"
        if user_input is not None and not errors:
            return self.async_create_entry(
                data={
                    **self.config_entry.options,
                    **user_input,
                    CONF_STATIONS: stations,
                }
            )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    **_station_field(
                        user_input[CONF_STATIONS] if user_input is not None
                        else format_stations(
                            self.config_entry.options.get(CONF_STATIONS, STATIONS)
                        )
                    ),
                    vol.Optional(
                        CONF_CREATE_DASHBOARD,
                        default=values.get(CONF_CREATE_DASHBOARD, True),
                    ): bool,
                    vol.Optional(
                        CONF_DASHBOARD_NAME,
                        default=values.get(
                            CONF_DASHBOARD_NAME, DEFAULT_DASHBOARD_NAME
                        ),
                    ): str,
                    vol.Optional(
                        CONF_EXCLUDED_PLAYERS,
                        default=values.get(CONF_EXCLUDED_PLAYERS, []),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="media_player", multiple=True
                        )
                    ),
                }
            ),
            errors=errors,
        )
