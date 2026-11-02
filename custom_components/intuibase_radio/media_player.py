"""A native Home Assistant media player facade for Internet Radio."""

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import RadioEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([InternetRadioPlayer(hass.data[DOMAIN][entry.entry_id])])


class InternetRadioPlayer(RadioEntity, MediaPlayerEntity):
    """Expose the controller through HA's standard media-player interface."""

    _attr_icon = "mdi:radio"
    _attr_media_image_remotely_accessible = True
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, controller) -> None:
        super().__init__(controller, "media_player")

    @property
    def state(self) -> str:
        if self.controller.player:
            target = self.hass.states.get(self.controller.player)
            if target is not None:
                return target.state
        return "idle"

    @property
    def source(self) -> str:
        return self.controller.station

    @property
    def source_list(self) -> list[str]:
        return list(self.controller.stations)

    @property
    def volume_level(self) -> float:
        return self.controller.volume

    @property
    def media_title(self) -> str:
        return self.controller.station

    @property
    def media_content_type(self) -> MediaType:
        return MediaType.MUSIC

    @property
    def media_image_url(self) -> str | None:
        return self.controller.station_image_url

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "target_media_player": self.controller.player,
            "stream_url": self.controller.stream_url,
            "station_image_url": self.controller.station_image_url,
            "stream_attempt": self.controller.attempt,
            "stream_attempt_count": self.controller.attempt_count,
            "activity_log": self.controller.activity_log,
            "short_status": self.controller.short_status,
        }

    async def async_media_play(self) -> None:
        await self.controller.play()

    async def async_media_pause(self) -> None:
        await self.controller.command("media_pause")

    async def async_media_stop(self) -> None:
        await self.controller.command("media_stop")

    async def async_set_volume_level(self, volume: float) -> None:
        await self.controller.set_volume(volume)

    async def async_select_source(self, source: str) -> None:
        if source in self.controller.stations:
            self.controller.station = source
            self.controller.stream_url = None
            self.controller.attempt = 0
            self.controller.attempt_count = 0
            self.controller.streams = []
            self.controller.stream_index = -1
            self.controller.set_status(
                self.controller._t("Selected", "Wybrano") + f": {source}"
            )
