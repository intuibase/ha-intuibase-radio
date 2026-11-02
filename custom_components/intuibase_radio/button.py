"""Radio transport buttons."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import RadioEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        RadioButton(controller, "play_station", "mdi:play-circle", None),
        RadioButton(controller, "resume", "mdi:play", "media_play"),
        RadioButton(controller, "pause", "mdi:pause", "media_pause"),
        RadioButton(controller, "stop", "mdi:stop", "media_stop"),
        RadioButton(controller, "previous_stream", "mdi:skip-previous", "previous_stream"),
        RadioButton(controller, "next_stream", "mdi:skip-next", "next_stream"),
    ])


class RadioButton(RadioEntity, ButtonEntity):
    def __init__(self, controller, key: str, icon: str, service: str | None) -> None:
        super().__init__(controller, key)
        self._attr_icon = icon
        self.service = service

    async def async_press(self) -> None:
        if self.service is None:
            await self.controller.play()
        elif self.service == "previous_stream":
            await self.controller.switch_stream(-1)
        elif self.service == "next_stream":
            await self.controller.switch_stream(1)
        else:
            await self.controller.command(self.service)
