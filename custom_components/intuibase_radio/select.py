"""Station and output selection entities."""

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import RadioEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StationSelect(controller), PlayerSelect(controller)])


class StationSelect(RadioEntity, SelectEntity):
    _attr_icon = "mdi:radio-tower"

    def __init__(self, controller) -> None:
        super().__init__(controller, "station")
        self._attr_options = list(controller.stations)

    @property
    def current_option(self) -> str:
        return self.controller.station

    async def async_select_option(self, option: str) -> None:
        self.controller.station = option
        self.controller.stream_url = None
        self.controller.attempt = 0
        self.controller.attempt_count = 0
        self.controller.streams = []
        self.controller.stream_index = -1
        self.controller.set_status(
            self.controller._t("Selected", "Wybrano") + f": {option}"
        )


class PlayerSelect(RadioEntity, SelectEntity):
    _attr_icon = "mdi:speaker-multiple"

    def __init__(self, controller) -> None:
        super().__init__(controller, "player")

    @property
    def options(self) -> list[str]:
        return list(self.controller.players) or [self.controller.no_players_label]

    @property
    def current_option(self) -> str:
        return self.controller.selected_player_name or self.controller.no_players_label

    async def async_select_option(self, option: str) -> None:
        if option in self.controller.players:
            if await self.controller.select_player(self.controller.players[option]):
                self.controller.set_status(
                    self.controller._t("Media player", "Odtwarzacz") + f": {option}"
                )
