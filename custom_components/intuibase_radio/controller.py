"""State and playback logic shared by the radio entities."""

from __future__ import annotations

import asyncio
import logging
import re
import socket
import unicodedata

from aiohttp import ClientSession, TCPConnector
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.const import ATTR_ENTITY_ID, EVENT_STATE_CHANGED, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .const import CONF_EXCLUDED_PLAYERS, CONF_STATIONS, CONF_TARGET_PLAYER, RADIO_BROWSER_URLS, STATIONS

_LOGGER = logging.getLogger(__name__)


def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", value.lower())


class RadioController:
    """Keep selections and translate them into media-player calls."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.stations = dict(entry.options.get(CONF_STATIONS, STATIONS))
        self.station = next(iter(self.stations))
        self.playing_station: str | None = None
        self.player: str | None = entry.options.get(CONF_TARGET_PLAYER)
        self.volume = 0.35
        self.stream_url: str | None = None
        self.station_image_url: str | None = None
        self.attempt = 0
        self.attempt_count = 0
        self.streams: list[tuple[str, str, str | None]] = []
        self.stream_index = -1
        self.status = self._t("Ready", "Gotowe")
        self.short_status = self._t("Ready", "Gotowe")
        self.player_state: str | None = None
        self.playback_phase = "idle"
        self.activity_log: list[str] = []
        self.players: dict[str, str] = {}
        self.listeners: list = []
        self.unsubscribe = None
        self.dashboard = None
        self.set_status(self._t("Ready", "Gotowe"), notify=False)

    def _t(self, english: str, polish: str) -> str:
        """Return a runtime label in the Home Assistant language."""
        return polish if self.hass.config.language.lower().startswith("pl") else english

    @property
    def no_players_label(self) -> str:
        return self._t("No media players", "Brak odtwarzaczy")

    @callback
    def set_status(self, message: str, *, notify: bool = True) -> None:
        """Update the current status and retain a short readable activity log."""
        self.status = message[:255]
        timestamp = dt_util.now().strftime("%H:%M:%S")
        self.activity_log.append(f"{timestamp} — {message}"[:700])
        self.activity_log = self.activity_log[-20:]
        if notify:
            self.notify()

    @callback
    def add_listener(self, listener) -> None:
        self.listeners.append(listener)

    @callback
    def notify(self) -> None:
        for listener in self.listeners:
            listener()

    @callback
    def refresh_players(self) -> None:
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)

        def sort_key(state) -> tuple[bool, str]:
            entity = entity_registry.async_get(state.entity_id)
            device = device_registry.async_get(entity.device_id) if entity and entity.device_id else None
            is_cast_group = bool(device and device.model == "Google Cast Group")
            return (not is_cast_group, state.name.casefold())

        players: dict[str, str] = {}
        used: set[str] = set()
        excluded = set(self.entry.options.get(CONF_EXCLUDED_PLAYERS, []))
        for state in sorted(
            self.hass.states.async_all("media_player"),
            key=sort_key,
        ):
            supported = int(state.attributes.get("supported_features") or 0)
            if (
                state.entity_id in excluded
                or
                state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)
                or not supported & MediaPlayerEntityFeature.PLAY_MEDIA
            ):
                continue
            label = state.name
            if label in used:
                label = f"{label} ({state.entity_id})"
            used.add(label)
            players[label] = state.entity_id
        changed = players != self.players
        self.players = players
        if self.player not in players.values():
            self.player = next(iter(players.values()), None)
            changed = True
        if self.player:
            state = self.hass.states.get(self.player)
            if state and isinstance(state.attributes.get("volume_level"), (float, int)):
                new_volume = float(state.attributes["volume_level"])
                changed |= new_volume != self.volume
                self.volume = new_volume
            if state and state.state != self.player_state:
                previous_player_state = self.player_state
                self.player_state = state.state
                if self.stream_url:
                    if state.state == "buffering":
                        self.short_status = self._t("Buffering…", "Buforuję…")
                    elif state.state == "playing":
                        self.short_status = self._t("Playing", "Odtwarzam") + f": {self.station}"
                    elif state.state == "paused":
                        self.short_status = self._t("Paused", "Pauza")
                    elif state.state == "idle" and previous_player_state in (
                        "buffering",
                        "playing",
                    ):
                        self.short_status = self._t("Ready", "Gotowe")
                changed = True
        if changed:
            self.notify()

    @callback
    def select_player(self, entity_id: str) -> None:
        """Select and persist the output used after future HA restarts."""
        self.player = entity_id
        options = {**self.entry.options, CONF_TARGET_PLAYER: entity_id}
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self.refresh_players()

    @property
    def selected_player_name(self) -> str | None:
        return next((name for name, entity in self.players.items() if entity == self.player), None)

    async def resolve_streams(self) -> list[tuple[str, str, str | None]]:
        query = self.stations[self.station]
        params = {
            "name": query,
            "hidebroken": "true",
            "order": "clickcount",
            "reverse": "true",
            "limit": "30",
        }
        results = []
        api_errors: list[str] = []
        connector = TCPConnector(family=socket.AF_INET)
        async with ClientSession(connector=connector) as session:
            for api_url in RADIO_BROWSER_URLS:
                try:
                    async with session.get(
                        api_url,
                        params=params,
                        headers={"User-Agent": "IntuiBase-Radio/0.3.0"},
                        timeout=15,
                    ) as response:
                        response.raise_for_status()
                        results = await response.json()
                except Exception as err:
                    api_errors.append(f"{api_url}: {err}")
                    _LOGGER.warning(
                        "Radio Browser request failed: %s: %s", api_url, err
                    )
                    continue
                if results:
                    break
        if not results and len(api_errors) == len(RADIO_BROWSER_URLS):
            raise ConnectionError(
                self._t(
                    "Radio Browser is unavailable",
                    "Radio Browser jest niedostępne",
                )
                + f": {api_errors[-1]}"
            )
        if not results:
            raise ValueError(
                self._t("No streams found for", "Nie znaleziono streamu dla")
                + f": {self.station}"
            )
        wanted = _plain(query)
        results.sort(
            key=lambda item: (
                _plain(item.get("name", "")) == wanted,
                wanted in _plain(item.get("name", "")),
                (item.get("url_resolved") or item.get("url") or "").startswith("https://"),
                int(item.get("votes") or 0),
                int(item.get("clickcount") or 0),
                int(item.get("bitrate") or 0),
            ),
            reverse=True,
        )
        streams: list[tuple[str, str, str | None]] = []
        seen: set[str] = set()
        fallback_image = next(
            (
                image
                for result in results
                if (image := result.get("favicon"))
                and image.startswith(("http://", "https://"))
            ),
            None,
        )
        for result in results:
            url = result.get("url_resolved") or result.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            codec = str(result.get("codec") or "").upper()
            media_type = "audio/aac" if "AAC" in codec else "audio/mpeg"
            image = result.get("favicon")
            if not image or not image.startswith(("http://", "https://")):
                image = fallback_image
            streams.append((url, media_type, image))
        if not streams:
            raise ValueError(
                self._t(
                    "The station did not return a stream URL",
                    "Stacja nie zwróciła adresu streamu",
                )
                + f": {self.station}"
            )
        return streams

    async def _wait_for_player_state(self, expected: set[str]) -> str:
        """Wait until the target reports one of the expected playback states."""
        changed = asyncio.Event()
        result: str | None = None

        @callback
        def state_changed(event: Event) -> None:
            nonlocal result
            if event.data.get("entity_id") != self.player:
                return
            state = event.data.get("new_state")
            if state is not None and state.state in expected:
                result = state.state
                changed.set()

        unsubscribe = self.hass.bus.async_listen(EVENT_STATE_CHANGED, state_changed)
        try:
            state = self.hass.states.get(self.player) if self.player else None
            if state is not None and state.state in expected:
                return state.state
            await changed.wait()
            assert result is not None
            return result
        finally:
            unsubscribe()

    async def _play_stream(self, index: int) -> None:
        """Play one resolved stream and require a real playing confirmation."""
        url, _media_type, image = self.streams[index]
        self.stream_index = index
        self.attempt = index + 1
        self.attempt_count = len(self.streams)
        self.stream_url = url
        self.station_image_url = image
        self.playing_station = self.station
        self.playback_phase = "connecting"
        self.short_status = self._t("Connecting to stream", "Łączę stream") + f" {index + 1}/{len(self.streams)}…"
        self.set_status(self._t("Connecting", "Łączenie") + f" {index + 1}/{len(self.streams)}: {url}")
        async with asyncio.timeout(30):
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                {
                    ATTR_ENTITY_ID: self.player,
                    "media_content_id": url,
                    "media_content_type": "music",
                },
                blocking=True,
            )
            state = await self._wait_for_player_state({"buffering", "playing"})
        if state == "buffering":
            self.playback_phase = "buffering"
            self.short_status = self._t("Buffering stream", "Buforuję stream") + f" {index + 1}/{len(self.streams)}…"
            self.set_status(self._t("Buffering", "Buforowanie") + f" {index + 1}/{len(self.streams)}: {url}")
            async with asyncio.timeout(60):
                await self._wait_for_player_state({"playing"})
        self.playback_phase = "playing"

    async def switch_stream(self, offset: int) -> None:
        """Manually move to the previous or next resolved stream."""
        if not self.player:
            self.short_status = self._t("Error: no media player", "Błąd: brak odtwarzacza")
            self.set_status(self._t("No media_player available", "Brak odtwarzacza media_player"))
            return
        if not self.streams:
            self.short_status = self._t("Searching for streams…", "Szukam streamów…")
            self.set_status(self._t("Searching for streams", "Wyszukiwanie streamów") + f": {self.station}")
            try:
                self.streams = await self.resolve_streams()
            except Exception as err:
                self.short_status = self._t("Search error", "Błąd wyszukiwania")
                self.set_status(self._t("Error", "Błąd") + f": {err}")
                return
        if self.stream_index < 0:
            index = 0 if offset > 0 else len(self.streams) - 1
        else:
            index = (self.stream_index + offset) % len(self.streams)
        try:
            await self._play_stream(index)
        except TimeoutError:
            timeout = 60 if self.playback_phase == "buffering" else 30
            phase = self._t("buffering", "buforowania") if self.playback_phase == "buffering" else self._t("connection", "połączenia")
            self.short_status = f"Timeout {phase}: stream {index + 1}/{len(self.streams)}"
            self.set_status(
                f"Timeout {phase} {self._t('after', 'po')} {timeout} s: {self.streams[index][0]}"
            )
            return
        except Exception as err:
            self.short_status = self._t("Stream error", "Błąd streamu") + f" {index + 1}/{len(self.streams)}"
            self.set_status(self._t("Manually selected stream error", "Błąd ręcznie wybranego streamu") + f": {err}")
            return
        self.short_status = self._t("Playing stream", "Odtwarzam stream") + f" {index + 1}/{len(self.streams)}"
        self.set_status(self._t("Playing", "Gra") + f": {self.station} — {self.streams[index][0]}")

    async def play(self) -> None:
        if not self.player:
            self.short_status = self._t("Error: no media player", "Błąd: brak odtwarzacza")
            self.set_status(self._t("No media player with play_media support", "Brak dostępnego odtwarzacza z obsługą play_media"))
            return
        player_state = self.hass.states.get(self.player)
        if player_state is None or player_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self.short_status = self._t("Error: media player unavailable", "Błąd: odtwarzacz niedostępny")
            self.set_status(self._t("The selected media player is unavailable", "Wybrany odtwarzacz jest niedostępny"))
            return
        self.activity_log = []
        self.short_status = self._t("Searching for streams…", "Szukam streamów…")
        self.set_status(self._t("Searching for streams", "Wyszukiwanie streamów") + f": {self.station}")
        try:
            self.streams = await self.resolve_streams()
            self.attempt_count = len(self.streams)
            errors: list[str] = []
            await self.hass.services.async_call(
                "media_player",
                "volume_set",
                {
                    ATTR_ENTITY_ID: self.player,
                    "volume_level": self.volume,
                },
                blocking=True,
            )
            for index, (url, _media_type, _image) in enumerate(self.streams):
                try:
                    await self._play_stream(index)
                except TimeoutError:
                    timeout = 60 if self.playback_phase == "buffering" else 30
                    phase = self._t("buffering", "buforowania") if self.playback_phase == "buffering" else self._t("connection", "połączenia")
                    errors.append(f"{url}: timeout {phase} {timeout} s")
                    self.short_status = f"Timeout {phase}: stream {index + 1}/{len(self.streams)}"
                    self.set_status(
                        f"Timeout {phase} {index + 1}/{len(self.streams)} {self._t('after', 'po')} {timeout} s: {url}"
                    )
                    _LOGGER.warning("Radio stream %s timed out after %s seconds: %s", phase, timeout, url)
                    continue
                except Exception as err:
                    errors.append(f"{url}: {err}")
                    self.short_status = self._t("Stream error", "Błąd streamu") + f" {index + 1}/{len(self.streams)}"
                    self.set_status(
                        self._t("Failed attempt", "Nieudana próba") + f" {index + 1}/{len(self.streams)}: {url} — {err}"
                    )
                    _LOGGER.warning("Radio stream failed, trying next URL: %s: %s", url, err)
                    continue
                self.short_status = (
                    self._t("Playing stream", "Odtwarzam stream") + f" {index + 1}/{len(self.streams)}: {self.station}"
                )
                self.set_status(self._t("Playing", "Gra") + f": {self.station} — {url}")
                return
            raise RuntimeError(
                self._t("None of", "Żaden z") + f" {len(self.streams)} " + self._t("streams worked", "streamów nie zadziałał")
                + (f" ({errors[-1]})" if errors else "")
            )
        except Exception as err:  # Home Assistant surfaces the useful service/API error.
            _LOGGER.warning("Could not play %s: %s", self.station, err)
            self.short_status = self._t("Playback error", "Błąd odtwarzania")
            self.set_status(self._t("Error", "Błąd") + f": {err}")

    async def command(self, service: str) -> None:
        if not self.player:
            self.short_status = self._t("Error: no media player", "Błąd: brak odtwarzacza")
            self.set_status(self._t("No media_player available", "Brak odtwarzacza media_player"))
        else:
            await self.hass.services.async_call(
                "media_player", service, {ATTR_ENTITY_ID: self.player}, blocking=True
            )
            label = {
                "media_play": self._t("Playing", "Odtwarzam"),
                "media_pause": self._t("Paused", "Pauza"),
                "media_stop": self._t("Stopped", "Stop"),
            }.get(service, service)
            self.short_status = label
            self.set_status(label)

    async def set_volume(self, value: float) -> None:
        self.volume = value
        if self.player:
            await self.hass.services.async_call(
                "media_player",
                "volume_set",
                {ATTR_ENTITY_ID: self.player, "volume_level": value},
                blocking=True,
            )
        self.notify()
