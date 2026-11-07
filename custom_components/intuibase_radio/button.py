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

    @property
    def available(self) -> bool:
        """Only offer transport actions that apply to the selected output."""
        player = self.controller.player
        state = self.controller.hass.states.get(player) if player else None
        if state is None or state.state in ("unknown", "unavailable"):
            return False
        if self.service == "media_pause":
            return state.state == "playing"
        if self.service == "media_stop":
            return state.state in ("playing", "buffering", "paused")
        if self.service == "media_play":
            return state.state == "paused"
        if self.service is None:
            # Keep station changes possible while another station is playing.
            return not (
                state.state in ("playing", "buffering")
                and self.controller.station == self.controller.playing_station
            )
        return True

    async def async_press(self) -> None:
        if self.service is None:
            await self.controller.play(context=self._context)
        elif self.service == "previous_stream":
            await self.controller.switch_stream(-1, context=self._context)
        elif self.service == "next_stream":
            await self.controller.switch_stream(1, context=self._context)
        else:
            await self.controller.command(self.service)
