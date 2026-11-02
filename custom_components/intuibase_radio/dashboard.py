"""A self-contained, integration-managed radio dashboard."""

from homeassistant.components import frontend
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import LovelaceStorage
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify


class RadioDashboard:
    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        entry_id: str,
        media_player_entity_id: str | None,
    ) -> None:
        self.hass = hass
        self.name = name.strip() or "Radio"
        self.path = f"internet-radio-{slugify(self.name, separator='-')}-{entry_id[:8].lower()}"
        self.media_player_entity_id = media_player_entity_id or "media_player.intuibase_radio_player"
        self.store = None

    def _t(self, english: str, polish: str) -> str:
        return polish if self.hass.config.language.lower().startswith("pl") else english

    async def async_start(self) -> None:
        self.store = await self._async_start_panel(
            self.path, self.name, "mdi:radio", self._config()
        )

    async def _async_start_panel(
        self, path: str, title: str, icon: str, dashboard_config: dict
    ) -> LovelaceStorage | None:
        dashboards = self.hass.data[LOVELACE_DATA].dashboards
        if path in dashboards:
            store = dashboards[path]
            await store.async_save(dashboard_config)
            return store
        if frontend.async_panel_exists(self.hass, path):
            return None
        config = {
            "id": path,
            "url_path": path,
            "title": title,
            "icon": icon,
            "show_in_sidebar": True,
            "require_admin": False,
        }
        store = LovelaceStorage(self.hass, config)
        await store.async_save(dashboard_config)
        dashboards[path] = store
        frontend.async_register_built_in_panel(
            self.hass,
            "lovelace",
            frontend_url_path=path,
            sidebar_title=config["title"],
            sidebar_icon=config["icon"],
            show_in_sidebar=True,
            require_admin=False,
            config={"mode": "storage"},
        )
        return store

    async def async_stop(self) -> None:
        if self.store is not None:
            frontend.async_remove_panel(self.hass, self.path)
            self.hass.data[LOVELACE_DATA].dashboards.pop(self.path, None)
            self.store = None

    def _config(self) -> dict:
        return {
            "views": [{
                "title": "Radio",
                "path": "radio",
                "icon": "mdi:radio",
                "type": "sections",
                "max_columns": 3,
                "sections": [
                    {
                        "type": "grid",
                        "column_span": 2,
                        "cards": [
                            {
                                "type": "heading",
                                "heading": "IntuiBase Radio",
                                "heading_style": "title",
                                "icon": "mdi:radio",
                            },
                            {
                                "type": "custom:intuibase-radio-status",
                                "grid_options": {"columns": 12, "rows": 1},
                                "entity": "sensor.intuibase_radio_status",
                                "title": self._t("Connection status", "Status połączenia"),
                                "previous_button": "button.intuibase_radio_previous_stream",
                                "next_button": "button.intuibase_radio_next_stream",
                            },
                            {
                                "type": "custom:intuibase-radio-stations",
                                "entity": "select.intuibase_radio_station",
                                "title": self._t("Choose a station", "Wybierz stację"),
                                "max_height": "360px",
                                "play_button": "button.intuibase_radio_play_station",
                                "grid_options": {"columns": 12, "rows": 6},
                            },
                            {
                                "type": "tile",
                                "entity": "select.intuibase_radio_play_on",
                                "name": self._t("Play on", "Odtwarzaj na"),
                                "grid_options": {"columns": 12, "rows": 2},
                                "features": [{"type": "select-options"}],
                            },
                            {
                                "type": "custom:intuibase-radio-artwork",
                                "entity": "sensor.intuibase_radio_status",
                                "grid_options": {"columns": 12, "rows": 5},
                            },
                        ],
                    },
                    {
                        "type": "grid",
                        "column_span": 2,
                        "cards": [
                            {
                                "type": "heading",
                                "heading": self._t("Controls", "Sterowanie"),
                                "icon": "mdi:remote",
                            },
                            {
                                "type": "horizontal-stack",
                                "grid_options": {"columns": 12, "rows": 2},
                                "cards": [
                                    self._transport_button(
                                        "button.intuibase_radio_play_station",
                                        self._t("PLAY STATION", "GRAJ"),
                                        "mdi:radio-tower",
                                    ),
                                    self._transport_button(
                                        "button.intuibase_radio_resume",
                                        "PLAY",
                                        "mdi:play",
                                    ),
                                    self._transport_button(
                                        "button.intuibase_radio_pause",
                                        self._t("PAUSE", "PAUZA"),
                                        "mdi:pause",
                                    ),
                                    self._transport_button(
                                        "button.intuibase_radio_stop",
                                        "STOP",
                                        "mdi:stop",
                                    ),
                                ],
                            },
                            {
                                "type": "tile",
                                "entity": "number.intuibase_radio_volume",
                                "name": self._t("Volume", "Głośność"),
                                "icon": "mdi:volume-high",
                                "grid_options": {"columns": 12, "rows": 1},
                                "features": [{"type": "numeric-input", "style": "slider"}],
                            },
                        ],
                    },
                ],
            }, self._diagnostics_config()["views"][0]]
        }

    def _diagnostics_config(self) -> dict:
        return {
            "views": [{
                "title": self._t("Diagnostics", "Diagnostyka"),
                "path": "diagnostyka",
                "icon": "mdi:bug-outline",
                "type": "sections",
                "max_columns": 1,
                "sections": [{
                    "type": "grid",
                    "cards": [
                        {
                            "type": "media-control",
                            "entity": self.media_player_entity_id,
                            "grid_options": {"columns": 12},
                        },
                        {
                            "type": "markdown",
                            "title": self._t("Connection status", "Status połączenia"),
                            "grid_options": {"columns": 12},
                            "content": (
                                "{% set radio = states.sensor.intuibase_radio_status %}\n"
                                "## {{ radio.state }}\n\n"
                                f"**{self._t('Station', 'Stacja')}:** {{{{ radio.attributes.station or '—' }}}}  \n"
                                f"**{self._t('Attempt', 'Próba')}:** {{{{ radio.attributes.stream_attempt or 0 }}}}"
                                "/{{ radio.attributes.stream_attempt_count or 0 }}  \n"
                                "{% set url = radio.attributes.stream_url %}"
                                "{% if url %}**Stream:** [{{ url }}]({{ url }})"
                                "{% else %}**Stream:** —{% endif %}\n\n"
                                f"### {self._t('Attempt history', 'Historia prób')}\n"
                                "{% for line in radio.attributes.activity_log or [] %}"
                                "- {{ line }}\n"
                                f"{{% else %}}- {self._t('No events', 'Brak zdarzeń')}\n{{% endfor %}}"
                            ),
                            "entity_id": ["sensor.intuibase_radio_status"],
                        },
                    ],
                }],
            }]
        }

    @staticmethod
    def _transport_button(entity_id: str, name: str, icon: str) -> dict:
        return {
            "type": "button",
            "entity": entity_id,
            "name": name,
            "icon": icon,
            "show_state": False,
            "grid_options": {"columns": 3, "rows": 2},
            "tap_action": {
                "action": "perform-action",
                "perform_action": "button.press",
                "target": {"entity_id": entity_id},
            },
            "hold_action": {"action": "none"},
        }
