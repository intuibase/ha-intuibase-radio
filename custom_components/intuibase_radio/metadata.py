"""Read now-playing information without changing an output's playback."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import html
import re
import socket
import time
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, TCPConnector
from homeassistant.core import State

from .const import HTTP_USER_AGENT

METADATA_INTERVAL = 30
METADATA_MAX_AGE = 120
MAX_ICY_INTERVAL = 262144


def clean_text(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(html.unescape(value).replace("\x00", "").split())[:512]
    if not text or text.lower().startswith(("http://", "https://", "icy://")):
        return None
    return text


@dataclass(frozen=True)
class NowPlaying:
    title: str
    artist: str | None = None
    album: str | None = None
    source: str = "player"


def player_metadata(state: State | None, station: str, query: str) -> NowPlaying | None:
    if state is None or state.state != "playing":
        return None
    title = clean_text(state.attributes.get("media_title"))
    artist = clean_text(state.attributes.get("media_artist"))
    album = clean_text(state.attributes.get("media_album_name"))
    if not title or (title.casefold() in (station.casefold(), query.casefold()) and not artist):
        return None
    return NowPlaying(title, artist, album)


def icy_metadata(block: bytes, charset: str | None = None) -> NowPlaying | None:
    """Parse ICY's title field, including apostrophes inside a title."""
    text = None
    for encoding in dict.fromkeys(filter(None, (charset, "utf-8", "latin-1"))):
        try:
            text = block.rstrip(b"\x00").decode(encoding)
            break
        except (LookupError, UnicodeDecodeError):
            continue
    if text is None:
        return None
    match = re.search(r"(?:^|;)\s*StreamTitle\s*=\s*(['\"])(.*?)\1\s*;", text, re.I | re.S)
    if match is None:
        return None
    title = clean_text(match.group(2))
    if title is None:
        # An explicit empty title clears the previous song immediately.
        return NowPlaying("", source="stream")
    artist, separator, track = title.partition(" - ")
    if separator and clean_text(artist) and clean_text(track):
        return NowPlaying(clean_text(track), clean_text(artist), source="stream")
    return NowPlaying(title, source="stream")


class StreamMetadataReader:
    """Share small, bounded ICY probes between sessions using the same URL."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, NowPlaying | None]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def read(self, url: str) -> NowPlaying | None:
        try:
            parsed = urlsplit(url)
        except ValueError:
            return None
        if parsed.scheme not in ("http", "https"):
            return None
        async with self._locks.setdefault(url, asyncio.Lock()):
            cached = self._cache.get(url)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            result = None
            ttl = METADATA_INTERVAL
            # HLS and DASH do not carry ICY blocks. Their metadata must come
            # from the player; never display playlist filenames as song titles.
            if parsed.path.lower().endswith((".m3u8", ".mpd")):
                ttl = 600
            else:
                try:
                    result, supported = await self._probe(url)
                    if not supported:
                        ttl = 600
                except Exception:
                    # Metadata is optional: errors must never trigger fallback
                    # playback, change the volume or interrupt another source.
                    pass
            self._cache[url] = (time.monotonic() + ttl, result)
            return result

    async def _probe(self, url: str) -> tuple[NowPlaying | None, bool]:
        async with ClientSession(connector=TCPConnector(family=socket.AF_INET)) as session:
            async with session.get(
                url,
                headers={"User-Agent": HTTP_USER_AGENT, "Icy-MetaData": "1",
                         "Accept-Encoding": "identity"},
                timeout=ClientTimeout(total=12, sock_connect=3, sock_read=5),
                auto_decompress=False,
            ) as response:
                response.raise_for_status()
                try:
                    interval = int(response.headers.get("icy-metaint", "0"))
                except ValueError:
                    return None, False
                if not 0 < interval <= MAX_ICY_INTERVAL:
                    return None, False
                charset = response.headers.get("icy-charset") or response.charset
                for _ in range(3):
                    await response.content.readexactly(interval)
                    length = (await response.content.readexactly(1))[0] * 16
                    if not length:
                        continue
                    block = await response.content.readexactly(length)
                    if (metadata := icy_metadata(block, charset)) is not None:
                        return metadata, True
                return None, True
