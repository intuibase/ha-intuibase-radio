"""State and playback logic shared by the radio entities."""

from __future__ import annotations

import asyncio
import logging
import re
import socket
import time
import unicodedata

from aiohttp import ClientSession, ClientTimeout, TCPConnector
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers import target as target_helpers
from homeassistant.helpers.entity_component import async_update_entity
from homeassistant.util import dt as dt_util

from .const import CONF_EXCLUDED_PLAYERS, CONF_TARGET_PLAYER, HTTP_USER_AGENT, RADIO_BROWSER_URLS

from .localize import translate
from .metadata import StreamMetadataReader
from .playback import PlaybackSession
from .stations import ordered_stations

_LOGGER = logging.getLogger(__name__)


def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", value.lower())


class RadioController:
    """Keep selections and translate them into media-player calls."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.stations = ordered_stations(entry.options)
        self.station = next(iter(self.stations))
        self.playing_station: str | None = None
        self.player: str | None = entry.options.get(CONF_TARGET_PLAYER)
        self.volume = 0.35
        self._player_selection = 0
        self._volume_sync_pending = False
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
        self.unsubscribe_services = None
        self.dashboard = None
        self.sessions: dict[str, PlaybackSession] = {}
        self.metadata_reader = StreamMetadataReader()
        self._tasks: set[asyncio.Task] = set()
        self._image_cache: dict[tuple[str, ...], tuple[float, str | None]] = {}
        self.set_status(self._t("Ready", "Gotowe"), notify=False)

    def _t(self, english: str, polish: str) -> str:
        """Return a runtime label in the Home Assistant language."""
        return translate(self.hass.config.language, english, polish)

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
    def add_listener(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

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
        previous_player = self.player
        if self.player not in players.values():
            self.player = next(iter(players.values()), None)
            changed = True
        if self.player:
            state = self.hass.states.get(self.player)
            if not self._volume_sync_pending:
                value = state.attributes.get("volume_level") if state else None
                if (isinstance(value, (float, int)) and not isinstance(value, bool)
                        and 0 <= value <= 1):
                    new_volume = float(value)
                    changed |= new_volume != self.volume
                    self.volume = new_volume
            if state and state.state != self.player_state:
                self.player_state = state.state
                changed = True
        if previous_player != self.player:
            self.show_session()
        if changed:
            self.notify()

    async def select_player(self, entity_id: str) -> bool:
        """Select the output and synchronize its current volume."""
        self._player_selection += 1
        selection = self._player_selection
        self._volume_sync_pending = True
        self.player = entity_id
        options = {**self.entry.options, CONF_TARGET_PLAYER: entity_id}
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self.refresh_players()
        self.show_session()
        self.notify()
        try:
            await async_update_entity(self.hass, entity_id)
        except Exception as err:
            _LOGGER.warning("Could not refresh selected media player %s: %s", entity_id, err)
        finally:
            if selection == self._player_selection:
                self._volume_sync_pending = False
                self.refresh_players()
                self.notify()
        return selection == self._player_selection and self.player == entity_id

    @property
    def selected_player_name(self) -> str | None:
        return next((name for name, entity in self.players.items() if entity == self.player), None)

    async def resolve_streams(
        self, station: str | None = None, query: str | None = None,
    ) -> list[tuple[str, str, str | None]]:
        station = station or self.station
        query = query if query is not None else self.stations[station]
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
                        headers={"User-Agent": HTTP_USER_AGENT},
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
                + f": {station}"
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
        image_results = sorted(
            results,
            key=lambda item: (
                _plain(item.get("name", "")) == _plain(station),
                str(item.get("favicon") or "").startswith("https://"),
            ), reverse=True,
        )
        image = await self.resolve_station_image([
            item["favicon"] for item in image_results
            if isinstance(item.get("favicon"), str)
            and item["favicon"].startswith(("http://", "https://"))
        ])
        for result in results:
            url = result.get("url_resolved") or result.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            codec = str(result.get("codec") or "").upper()
            media_type = "audio/aac" if "AAC" in codec else "audio/mpeg"
            streams.append((url, media_type, image))
        if not streams:
            raise ValueError(
                self._t(
                    "The station did not return a stream URL",
                    "Stacja nie zwróciła adresu streamu",
                )
                + f": {station}"
            )
        return streams

    async def resolve_station_image(self, candidates: list[str]) -> str | None:
        """Use a working station logo, even if the chosen stream has a bad one."""
        candidates = list(dict.fromkeys(candidates))[:5]
        if not candidates:
            return None
        key = tuple(candidates)
        cached = self._image_cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        image = None
        try:
            async with asyncio.timeout(8):
                async with ClientSession(connector=TCPConnector(family=socket.AF_INET)) as session:
                    for candidate in candidates:
                        try:
                            async with session.get(
                                candidate, timeout=ClientTimeout(total=2),
                                headers={"User-Agent": HTTP_USER_AGENT},
                            ) as response:
                                response.raise_for_status()
                                if response.headers.get("Content-Type", "").lower().startswith("image/"):
                                    image = candidate
                                    break
                        except Exception:
                            continue
        except TimeoutError:
            pass
        self._image_cache[key] = (time.monotonic() + (1800 if image else 60), image)
        return image

    def create_task(self, coroutine) -> asyncio.Task:
        task = self.hass.async_create_background_task(coroutine, "IntuiBase Radio playback")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    @callback
    def show_session(self) -> None:
        """Project the selected device's session into the existing dashboard."""
        session = self.sessions.get(self.player)
        self.streams = session.streams if session else []
        self.stream_index = session.index if session else -1
        self.stream_url = session.url if session else None
        self.station_image_url = session.image if session else None
        self.playing_station = session.station if session else None
        self.attempt = session.index + 1 if session else 0
        self.attempt_count = len(session.streams) if session else 0
        self.playback_phase = session.phase if session else "idle"
        self.activity_log = list(session.activity_log) if session else []
        self.status = session.status if session else self._t("Ready", "Gotowe")
        self.short_status = session.short_status if session else self.status

    @callback
    def session_updated(self, session: PlaybackSession) -> None:
        if self.sessions.get(session.player) is not session:
            return
        if self.player == session.player:
            self.show_session()
        self.notify()

    @callback
    def player_changed(self, entity_id: str, state) -> None:
        if session := self.sessions.get(entity_id):
            session.observe(state)
            session.refresh_metadata(state)

    @property
    def now_playing(self):
        session = self.sessions.get(self.player)
        return session.now_playing if session else None

    @property
    def metadata_attributes(self) -> dict:
        session = self.sessions.get(self.player)
        return session.metadata_attributes() if session else {
            "media_title": None, "media_artist": None, "media_album_name": None,
            "metadata_source": None, "metadata_updated_at": None,
        }

    @callback
    def service_called(self, event) -> None:
        """Respect explicit stop/pause and playback started outside the radio."""
        if event.data.get("domain") != "media_player":
            return
        service = event.data.get("service")
        if service not in ("media_stop", "media_pause", "turn_off", "play_media"):
            return
        data = event.data.get("service_data", {})
        targets = data.get(ATTR_ENTITY_ID) or []
        if isinstance(targets, str):
            targets = [item.strip() for item in targets.split(",")]
        targets = set(targets)
        if any(data.get(key) for key in ("area_id", "device_id", "floor_id", "label_id")):
            selected = target_helpers.async_extract_referenced_entity_ids(
                self.hass, target_helpers.TargetSelection(data), True,
            )
            targets |= selected.referenced | selected.indirectly_referenced
        for player, session in list(self.sessions.items()):
            if player not in targets and "all" not in targets:
                continue
            if session.command_context and event.context.id == session.command_context.id:
                continue
            phase = "released" if service == "play_media" else (
                "paused" if service == "media_pause" else "stopped")
            session.suspend(phase)

    async def async_shutdown(self) -> None:
        """Cancel all supervisors on unload, without stopping the devices."""
        for session in self.sessions.values():
            session.suspend()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_session(self, session: PlaybackSession, *, offset: int | None = None) -> None:
        task = session.launch(session.start(offset=offset))
        try:
            await task
        except asyncio.CancelledError:
            if session.desired_playing:
                raise

    async def play(self, entity_id: str | None = None, station: str | None = None,
                   *, context: Context | None = None) -> None:
        # Capture both selections before any await; another user may change the
        # dashboard while this device is resolving or connecting to its stream.
        player = entity_id or self.player
        station = station or self.station
        if not player:
            self.short_status = self._t("Error: no media player", "Błąd: brak odtwarzacza")
            self.set_status(self._t("No media_player available", "Brak odtwarzacza media_player"))
            return
        if station not in self.stations:
            raise ValueError(f"Unknown station: {station}")
        if not player.startswith("media_player."):
            raise ValueError("The output must be a media_player entity")
        state = self.hass.states.get(player)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            raise ValueError(self._t("The selected media player is unavailable", "Wybrany odtwarzacz jest niedostępny"))
        previous = self.sessions.get(player)
        session = PlaybackSession(self, player, station, self.stations[station], context)
        self.sessions[player] = session
        if previous:
            previous.suspend()
        await self._run_session(session)

    async def switch_stream(self, offset: int, *, context: Context | None = None) -> None:
        player = self.player
        if not player:
            return
        previous = self.sessions.get(player)
        station = previous.station if previous else self.station
        query = previous.query if previous else self.stations[station]
        session = PlaybackSession(self, player, station, query, context)
        if previous:
            session.streams = list(previous.streams)
            session.index = previous.index
        self.sessions[player] = session
        if previous:
            previous.suspend()
        await self._run_session(session, offset=offset)

    async def command(self, service: str) -> None:
        player = self.player
        if not player:
            return
        session = self.sessions.get(player)
        if session and service in ("media_pause", "media_stop"):
            session.suspend("paused" if service == "media_pause" else "stopped")
        await self.hass.services.async_call(
            "media_player", service, {ATTR_ENTITY_ID: player}, blocking=True
        )
        if session and service == "media_play" and session._is_ours(self.hass.states.get(player)):
            session.desired_playing = True
            session.phase = "playing"
            session.update(self._t("Playing", "Odtwarzam") + f": {session.station}")
            session.observe(self.hass.states.get(player))
            session.refresh_metadata(self.hass.states.get(player))

    async def set_volume(self, value: float) -> None:
        if not self.player:
            return
        player = self.player
        selection = self._player_selection
        await self.hass.services.async_call(
            "media_player",
            "volume_set",
            {ATTR_ENTITY_ID: player, "volume_level": value},
            blocking=True,
        )
        if selection == self._player_selection and player == self.player:
            self.volume = value
            self.notify()
