"""Current radio status entity."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import RadioEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([RadioStatus(hass.data[DOMAIN][entry.entry_id])])


class RadioStatus(RadioEntity, SensorEntity):
    _attr_icon = "mdi:radio"

    def __init__(self, controller) -> None:
        super().__init__(controller, "status")

    @property
    def native_value(self) -> str:
        return self.controller.status

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "station": self.controller.station,
            "playing_station": self.controller.playing_station,
            "media_player": self.controller.player,
            "stream_url": self.controller.stream_url,
            "station_image_url": self.controller.station_image_url,
            "stream_attempt": self.controller.attempt,
            "stream_attempt_count": self.controller.attempt_count,
            "activity_log": self.controller.activity_log,
            "short_status": self.controller.short_status,
            "player_state": self.controller.player_state,
        }
