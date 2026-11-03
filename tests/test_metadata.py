"""Parse real ICY byte framing using a local HTTP server, without external IO."""

import asyncio
import unittest
from unittest.mock import patch

from aiohttp import web
from homeassistant.core import State

from custom_components.intuibase_radio.metadata import (
    NowPlaying, StreamMetadataReader, icy_metadata, player_metadata,
)


class MetadataParsingTests(unittest.TestCase):
    def test_utf8_artist_title_and_apostrophes(self):
        self.assertEqual(
            icy_metadata("StreamTitle='Guns N' Roses - Don't Cry';StreamUrl='';".encode()),
            NowPlaying("Don't Cry", "Guns N' Roses", source='stream'))
        self.assertEqual(icy_metadata("StreamTitle='Żółć - Łódź';".encode()).title, 'Łódź')

    def test_show_title_empty_title_and_missing_metadata(self):
        self.assertEqual(icy_metadata(b"StreamTitle='Evening programme';").title, 'Evening programme')
        self.assertEqual(icy_metadata(b"StreamTitle='';"), NowPlaying('', source='stream'))
        self.assertIsNone(icy_metadata(b"StreamUrl='https://radio.test';"))

    def test_declared_encoding_and_entities(self):
        metadata = icy_metadata("StreamTitle='Żółć &amp; Łódź';".encode('cp1250'), 'windows-1250')
        self.assertEqual(metadata.title, 'Żółć & Łódź')

    def test_player_metadata_filters_urls_station_names_and_non_playing_states(self):
        for title in ('', 'https://radio.test/live.mp3', 'My station', 'Query'):
            with self.subTest(title=title):
                state = State('media_player.test', 'playing', {'media_title': title})
                self.assertIsNone(player_metadata(state, 'My station', 'Query'))
        self.assertIsNone(player_metadata(State('media_player.test', 'idle', {'media_title': 'Old song'}), 'Station', 'query'))
        self.assertEqual(player_metadata(State('media_player.test', 'playing', {
            'media_title': 'Song', 'media_artist': 'Artist', 'media_album_name': 'Album',
        }), 'Station', 'query'), NowPlaying('Song', 'Artist', 'Album'))


class IcyReaderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = 0
        self.interval = '8'
        self.metadata = b"StreamTitle='Artist - Song';"
        self.status = 200
        self.body = None
        self.reader = StreamMetadataReader()

        async def stream(request):
            self.calls += 1
            self.assertEqual(request.headers['Icy-MetaData'], '1')
            self.assertIn('IntuiBase-Radio', request.headers['User-Agent'])
            self.assertEqual(request.headers['Accept-Encoding'], 'identity')
            headers = {'Content-Type': 'audio/mpeg'}
            if self.interval is not None:
                headers['icy-metaint'] = self.interval
            length = (len(self.metadata) + 15) // 16
            data = b'12345678' + bytes([length]) + self.metadata.ljust(length * 16, b'\x00')
            return web.Response(status=self.status, body=data if self.body is None else self.body, headers=headers)

        app = web.Application()
        app.router.add_get('/stream', stream)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.addAsyncCleanup(self.runner.cleanup)
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        port = self.runner.addresses[0][1]
        self.url = f'http://127.0.0.1:{port}/stream'

    async def test_reads_audio_interval_and_caches_one_probe_for_multiple_sessions(self):
        first, second = await asyncio.gather(self.reader.read(self.url), self.reader.read(self.url))
        self.assertEqual(first, NowPlaying('Song', 'Artist', source='stream'))
        self.assertEqual(second, first)
        self.assertEqual(self.calls, 1)

    async def test_missing_or_invalid_intervals_do_not_read_unbounded_audio(self):
        for interval in (None, 'not a number', '0', '-1', '999999999'):
            with self.subTest(interval=interval):
                self.interval = interval
                self.assertIsNone(await StreamMetadataReader().read(self.url))

    async def test_empty_title_and_http_errors_are_optional(self):
        self.metadata = b"StreamTitle='';"
        self.assertEqual(await self.reader.read(self.url), NowPlaying('', source='stream'))
        self.status = 503
        self.assertIsNone(await StreamMetadataReader().read(self.url))

    async def test_zero_length_blocks_and_truncated_streams(self):
        length = (len(self.metadata) + 15) // 16
        self.body = b'12345678\x00' + b'12345678' + bytes([length]) + self.metadata.ljust(length * 16, b'\x00')
        self.assertEqual(await self.reader.read(self.url), NowPlaying('Song', 'Artist', source='stream'))
        self.body = b'12345678\x05truncated'
        self.assertIsNone(await StreamMetadataReader().read(self.url))

    async def test_hls_and_invalid_urls_are_not_probed_as_icy(self):
        for url in ('https://radio.test/live.m3u8?token=abc', 'https://radio.test/live.mpd',
                    'file:///etc/passwd', 'http://[invalid'):
            with self.subTest(url=url), patch('custom_components.intuibase_radio.metadata.ClientSession') as factory:
                self.assertIsNone(await self.reader.read(url))
                factory.assert_not_called()
