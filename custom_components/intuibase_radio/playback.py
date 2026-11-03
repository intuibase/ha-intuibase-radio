"""Independent playback and conservative recovery for one output device."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Context, State, callback
from homeassistant.util import dt as dt_util

from .metadata import METADATA_INTERVAL, METADATA_MAX_AGE, NowPlaying, player_metadata

if TYPE_CHECKING:
    from .controller import RadioController

CONNECT_TIMEOUT = 30
BUFFER_TIMEOUT = 60
RECOVERY_DELAYS = (5, 30, 120)


class PlaybackSession:
    """Keep a station, candidate URLs and recovery task bound to one player."""

    def __init__(self, controller: RadioController, player: str, station: str, query: str,
                 context: Context | None = None) -> None:
        self.controller = controller
        self.hass = controller.hass
        self.player = player
        self.station = station
        self.query = query
        self.context = context
        self.streams: list[tuple[str, str, str | None]] = []
        self.index = -1
        self.phase = "idle"
        self.status = ""
        self.short_status = ""
        self.activity_log: list[str] = []
        self.last_error: str | None = None
        self.desired_playing = True
        self.confirmed = False
        self.app_id: str | None = None
        self.task: asyncio.Task | None = None
        self.command_context: Context | None = None
        self.now_playing: NowPlaying | None = None
        self.metadata_updated_at: str | None = None
        self.metadata_task: asyncio.Task | None = None
        self._stream_metadata: NowPlaying | None = None
        self._stream_metadata_at = 0.0
        self._changed = asyncio.Event()
        self._revision = 0
        self._known_urls: set[str] = set()
        self._baseline = self._identity(self.hass.states.get(player))

    @property
    def url(self) -> str | None:
        return self.streams[self.index][0] if self.index >= 0 else None

    @property
    def image(self) -> str | None:
        return self.streams[self.index][2] if self.index >= 0 else None

    @staticmethod
    def _identity(state: State | None) -> tuple[str | None, str | None]:
        if state is None:
            return None, None
        return state.attributes.get("media_content_id"), state.attributes.get("app_id")

    def _is_ours(self, state: State | None) -> bool:
        content_id, app_id = self._identity(state)
        return bool(
            content_id and content_id == self.url
            and not (self.app_id and app_id and app_id != self.app_id)
        )

    def _is_foreign(self, state: State | None) -> bool:
        content_id, app_id = self._identity(state)
        if (self.confirmed and app_id and self.app_id != app_id
                and (self.app_id or content_id != self.url)):
            return True
        if content_id and content_id not in self._known_urls | {item[0] for item in self.streams}:
            return self.confirmed or (content_id, app_id) != self._baseline
        return False

    def launch(self, coroutine) -> asyncio.Task:
        self.task = self.controller.create_task(coroutine)
        self.task.add_done_callback(self._finished)
        return self.task

    def _finished(self, task: asyncio.Task) -> None:
        if task is self.task and self.desired_playing and self.phase == "playing":
            self.observe(self.hass.states.get(self.player))

    @callback
    def update(self, short: str, detail: str | None = None) -> None:
        self.short_status = short
        self.status = (detail or short)[:255]
        timestamp = dt_util.now().strftime("%H:%M:%S")
        self.activity_log.append(f"{timestamp} — {detail or short}"[:700])
        self.activity_log = self.activity_log[-20:]
        self.controller.session_updated(self)

    @callback
    def suspend(self, phase: str = "stopped") -> None:
        """Relinquish recovery without sending any command to the device."""
        self.desired_playing = False
        self.phase = phase
        self.stop_metadata()
        if self.task and not self.task.done() and self.task is not asyncio.current_task():
            self.task.cancel()
        self._changed.set()
        if phase == "released":
            label = self.controller._t("Playback taken over", "Odtwarzanie przejęte")
        elif phase == "paused":
            label = self.controller._t("Paused", "Pauza")
        else:
            label = self.controller._t("Stopped", "Stop")
        self.update(label)

    @callback
    def stop_metadata(self) -> None:
        if self.metadata_task and not self.metadata_task.done():
            self.metadata_task.cancel()
        self.metadata_task = None
        self._stream_metadata = None
        self._stream_metadata_at = 0.0
        self._set_metadata(None)

    @callback
    def _set_metadata(self, metadata: NowPlaying | None) -> None:
        if metadata == self.now_playing:
            return
        self.now_playing = metadata
        self.metadata_updated_at = dt_util.utcnow().isoformat() if metadata else None
        self.controller.session_updated(self)

    @callback
    def refresh_metadata(self, state: State | None) -> None:
        if (not self.desired_playing or self.phase != "playing" or state is None
                or state.state != "playing" or self._is_foreign(state)):
            self.stop_metadata()
            return
        metadata = player_metadata(state, self.station, self.query)
        if metadata is None and time.monotonic() - self._stream_metadata_at < METADATA_MAX_AGE:
            metadata = self._stream_metadata
        if metadata and (not metadata.title or (
                not metadata.artist and metadata.title.casefold() in
                (self.station.casefold(), self.query.casefold()))):
            metadata = None
        self._set_metadata(metadata)
        if self.url and (self.metadata_task is None or self.metadata_task.done()):
            self.metadata_task = self.controller.create_task(self._poll_metadata(self.url))

    async def _poll_metadata(self, url: str) -> None:
        # HA starts background tasks eagerly. Let refresh_metadata store this
        # task before a cached reader result can publish another update.
        await asyncio.sleep(0)
        while self.desired_playing and self.phase == "playing" and self.url == url:
            state = self.hass.states.get(self.player)
            metadata = None
            if player_metadata(state, self.station, self.query) is None:
                try:
                    metadata = await self.controller.metadata_reader.read(url)
                except Exception:
                    pass
            # A source, URL or entire session can change during the HTTP read.
            if (not self.desired_playing or self.phase != "playing" or self.url != url
                    or self.controller.sessions.get(self.player) is not self):
                return
            if metadata is not None:
                self._stream_metadata = metadata
                self._stream_metadata_at = time.monotonic()
            self.refresh_metadata(self.hass.states.get(self.player))
            await asyncio.sleep(METADATA_INTERVAL)

    @callback
    def observe(self, state: State | None) -> None:
        """React only to this device, never to the dashboard's current target."""
        self._revision += 1
        self._changed.set()
        if not self.desired_playing:
            return
        if self._is_foreign(state):
            self.suspend("released")
            return
        if self._is_ours(state) and state.attributes.get("app_id"):
            self.app_id = state.attributes["app_id"]
        if state and state.state in ("paused", "off") and self.confirmed:
            self.suspend("paused" if state.state == "paused" else "stopped")
            return
        if self.task and not self.task.done():
            return
        if not self.confirmed:
            # No URL identity means we cannot safely distinguish radio from
            # another application. Manual playback still works without recovery.
            return
        if state and state.state == "playing":
            if not self._is_ours(state):
                self.suspend("released")
            return
        if state is None or state.state in ("idle", "buffering", STATE_UNAVAILABLE, STATE_UNKNOWN):
            self.phase = "recovering"
            self.update(self.controller._t("Reconnecting stream", "Wznawiam stream"))
            self.launch(self.recover())

    async def _wait(self, expected: set[str], revision: int, initial: State | None) -> str:
        while self.desired_playing:
            self._changed.clear()
            state = self.hass.states.get(self.player)
            if self._is_foreign(state):
                self.suspend("released")
                raise asyncio.CancelledError
            if state is not None and state.state in expected:
                content_id, _ = self._identity(state)
                if self._is_ours(state):
                    self.confirmed |= state.state == "playing"
                    self.app_id = state.attributes.get("app_id")
                    return state.state
                if (not content_id and self._revision > revision
                        and (initial is None or initial.state != "playing")):
                    # Players without media IDs can confirm manual playback,
                    # but cannot enable automatic recovery.
                    return state.state
            if state is not None and state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                raise RuntimeError("Media player unavailable")
            await self._changed.wait()
        raise asyncio.CancelledError

    async def attempt(self, index: int, *, automatic: bool = False) -> None:
        if not self.desired_playing:
            raise asyncio.CancelledError
        initial = self.hass.states.get(self.player)
        if self._is_foreign(initial):
            self.suspend("released")
            raise asyncio.CancelledError
        if automatic and initial and initial.state == "playing":
            if not self._is_ours(initial):
                self.suspend("released")
                raise asyncio.CancelledError
            self.phase = "playing"
            self.update(self.controller._t("Playing", "Odtwarzam") + f": {self.station}")
            self.refresh_metadata(initial)
            return
        if automatic and initial and initial.state in ("paused", "off"):
            self.suspend("paused" if initial.state == "paused" else "stopped")
            raise asyncio.CancelledError
        self.stop_metadata()
        self.index = index
        self.phase = "connecting"
        revision = self._revision
        label = self.controller._t("Connecting to stream", "Łączę stream")
        self.update(f"{label} {index + 1}/{len(self.streams)}…", f"{label}: {self.url}")
        self._known_urls.add(self.url)
        self.command_context = Context(
            parent_id=self.context.id if self.context else None,
            user_id=self.context.user_id if self.context else None,
        )
        async with asyncio.timeout(CONNECT_TIMEOUT):
            await self.hass.services.async_call(
                "media_player", "play_media",
                {ATTR_ENTITY_ID: self.player, "media_content_id": self.url,
                 "media_content_type": "music"}, blocking=True, context=self.command_context,
            )
            state = await self._wait({"buffering", "playing"}, revision, initial)
        if state == "buffering":
            self.phase = "buffering"
            label = self.controller._t("Buffering stream", "Buforuję stream")
            self.update(f"{label} {index + 1}/{len(self.streams)}…")
            async with asyncio.timeout(BUFFER_TIMEOUT):
                await self._wait({"playing"}, revision, initial)
        self.phase = "playing"
        self.last_error = None
        label = self.controller._t("Playing stream", "Odtwarzam stream")
        self.update(f"{label} {index + 1}/{len(self.streams)}: {self.station}",
                    f"{self.station} — {self.url}")
        self.refresh_metadata(self.hass.states.get(self.player))

    async def try_candidates(self, indices: list[int], *, automatic: bool = False) -> bool:
        for index in indices:
            try:
                await self.attempt(index, automatic=automatic)
            except Exception as err:
                self.last_error = f"{type(err).__name__}: {err}"
                label = self.controller._t("Failed attempt", "Nieudana próba")
                self.update(f"{label} {index + 1}/{len(self.streams)}",
                            f"{label}: {self.url} — {self.last_error}")
            else:
                return True
        return False

    async def start(self, *, offset: int | None = None) -> None:
        try:
            if not self.streams:
                self.phase = "searching"
                self.update(self.controller._t("Searching for streams…", "Szukam streamów…"))
                self.streams = await self.controller.resolve_streams(self.station, self.query)
            if offset is None:
                indices = list(range(len(self.streams)))
            else:
                index = (self.index + offset) % len(self.streams) if self.index >= 0 else (
                    0 if offset > 0 else len(self.streams) - 1)
                indices = [index]
            if await self.try_candidates(indices):
                return
        except Exception as err:
            self.last_error = str(err)
        self.phase = "failed"
        self.desired_playing = False
        self.update(self.controller._t("Playback error", "Błąd odtwarzania"), self.last_error)

    async def recover(self) -> None:
        """Retry our URL, then the other candidates, with bounded backoff."""
        try:
            for round_index, delay in enumerate(RECOVERY_DELAYS):
                state = self.hass.states.get(self.player)
                if round_index == 0 and state and state.state == "buffering":
                    delay = BUFFER_TIMEOUT
                await asyncio.sleep(delay)
                if not self.desired_playing:
                    return
                state = self.hass.states.get(self.player)
                if self._is_foreign(state):
                    self.suspend("released")
                    return
                if state and state.state in ("paused", "off"):
                    self.suspend("paused" if state.state == "paused" else "stopped")
                    return
                if state and state.state == "playing":
                    if not self._is_ours(state):
                        self.suspend("released")
                    else:
                        self.phase = "playing"
                        self.update(self.controller._t("Playing", "Odtwarzam") + f": {self.station}")
                        self.refresh_metadata(state)
                    return
                if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    continue
                if round_index:
                    # A broadcaster may have replaced its URLs since playback began.
                    try:
                        streams = await self.controller.resolve_streams(self.station, self.query)
                    except Exception as err:
                        self.last_error = str(err)
                    else:
                        current = self.url
                        self.streams = streams
                        self.index = next((i for i, item in enumerate(streams) if item[0] == current), 0)
                indices = [(self.index + offset) % len(self.streams)
                           for offset in range(len(self.streams))]
                if await self.try_candidates(indices, automatic=True):
                    return
        except Exception as err:
            self.last_error = str(err)
        self.phase = "failed"
        self.desired_playing = False
        self.update(self.controller._t("Automatic recovery stopped", "Zakończono próby wznowienia"),
                    self.last_error)

    def diagnostics(self) -> dict:
        return {
            "station": self.station,
            "phase": self.phase,
            "stream_url": self.url,
            "stream_attempt": self.index + 1,
            "stream_attempt_count": len(self.streams),
            "automatic_recovery": self.desired_playing and self.confirmed,
            "last_error": self.last_error,
            **self.metadata_attributes(),
        }

    def metadata_attributes(self) -> dict:
        return {
            "media_title": self.now_playing.title if self.now_playing else None,
            "media_artist": self.now_playing.artist if self.now_playing else None,
            "media_album_name": self.now_playing.album if self.now_playing else None,
            "metadata_source": self.now_playing.source if self.now_playing else None,
            "metadata_updated_at": self.metadata_updated_at,
        }
