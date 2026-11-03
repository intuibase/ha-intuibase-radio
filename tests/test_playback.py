"""Playback supervision with HA's real state machine, bus and service registry."""

import asyncio
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import Context, HomeAssistant, callback

from custom_components.intuibase_radio.controller import RadioController
from custom_components.intuibase_radio.media_player import InternetRadioPlayer
from custom_components.intuibase_radio.metadata import NowPlaying
from custom_components.intuibase_radio.select import StationSelect
from custom_components.intuibase_radio.sensor import RadioStatus


KITCHEN = 'media_player.kitchen'
SALON = 'media_player.salon'


class PlaybackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.hass = HomeAssistant(directory)
        self.hass.config.language = 'en'
        self.controller = RadioController(self.hass, SimpleNamespace(options={
            'stations': {'Trójka': 'Trójka query', 'Jazz': 'Jazz query'},
            'target_player': KITCHEN,
        }))
        self.catalogue = {
            name: [(f'https://radio.test/{name}/{i}', 'audio/mpeg', None) for i in range(count)]
            for name, count in [('Trójka', 6), ('Jazz', 2)]
        }
        self.controller.resolve_streams = AsyncMock(side_effect=self.resolve)
        self.controller.metadata_reader.read = AsyncMock(return_value=None)
        self.calls = []
        self.fail_urls = set()
        self.silent_urls = set()
        self.buffer_urls = set()
        self.no_identity_urls = set()
        self.before_play = None
        for player in (KITCHEN, SALON):
            self.set_state(player, 'idle')

        async def play(call):
            player = call.data['entity_id']
            url = call.data['media_content_id']
            self.calls.append((player, url))
            if self.before_play:
                await self.before_play(player, url)
            if url in self.fail_urls:
                raise RuntimeError('Broken stream')
            if url in self.silent_urls:
                return
            self.set_state(player, 'buffering' if url in self.buffer_urls else 'playing',
                           None if url in self.no_identity_urls else url, 'radio-app')

        async def transport(call):
            previous = self.hass.states.get(call.data['entity_id'])
            self.set_state(call.data['entity_id'],
                           {'media_stop': 'idle', 'media_pause': 'paused',
                            'turn_off': 'off', 'media_play': 'playing'}[call.service],
                           previous.attributes.get('media_content_id'),
                           previous.attributes.get('app_id'))

        self.hass.services.async_register('media_player', 'play_media', play)
        for service in ('media_stop', 'media_pause', 'turn_off', 'media_play'):
            self.hass.services.async_register('media_player', service, transport)
        self.unsub_state = self.hass.bus.async_listen(EVENT_STATE_CHANGED, self.state_changed)
        self.unsub_service = self.hass.bus.async_listen(EVENT_CALL_SERVICE, self.controller.service_called)
        self.enterContext(patch('custom_components.intuibase_radio.playback.CONNECT_TIMEOUT', 0.05))
        self.enterContext(patch('custom_components.intuibase_radio.playback.BUFFER_TIMEOUT', 0.05))
        self.enterContext(patch('custom_components.intuibase_radio.playback.RECOVERY_DELAYS', (0.02, 0.02, 0.02)))

    async def asyncTearDown(self):
        self.unsub_state()
        self.unsub_service()
        await self.controller.async_shutdown()
        await self.hass.async_stop(force=True)

    async def resolve(self, station, query):
        self.assertEqual(query, f'{station} query')
        return list(self.catalogue[station])

    @callback
    def state_changed(self, event):
        self.controller.player_changed(event.data['entity_id'], event.data.get('new_state'))

    def set_state(self, player, state, url=None, app=None, **metadata):
        attributes = dict(metadata)
        if url is not None:
            attributes['media_content_id'] = url
        if app is not None:
            attributes['app_id'] = app
        self.hass.states.async_set(player, state, attributes)

    async def flush(self):
        await self.hass.async_block_till_done()

    async def settle(self, player=KITCHEN):
        await self.flush()
        session = self.controller.sessions[player]
        if session.task and not session.task.done():
            await asyncio.gather(session.task, return_exceptions=True)
        await self.flush()
        return session

    async def start(self, player=KITCHEN, station='Trójka'):
        await self.controller.play(player, station)
        await self.flush()
        return self.controller.sessions[player]

    async def test_six_urls_first_fails_second_plays(self):
        urls = [item[0] for item in self.catalogue['Trójka']]
        self.fail_urls.add(urls[0])
        session = await self.start()
        self.assertEqual(self.calls, [(KITCHEN, urls[0]), (KITCHEN, urls[1])])
        self.assertEqual(session.index, 1)
        self.assertTrue(session.confirmed)
        self.assertEqual(session.phase, 'playing')

    async def test_stale_spotify_playing_does_not_confirm_dead_first_url(self):
        self.set_state(KITCHEN, 'playing', 'spotify:track:old', 'spotify-app')
        self.silent_urls.add(self.catalogue['Trójka'][0][0])
        session = await self.start()
        self.assertEqual(session.index, 1)
        self.assertEqual(len(self.calls), 2)

    async def test_buffering_timeout_tries_next_url(self):
        self.buffer_urls.add(self.catalogue['Trójka'][0][0])
        session = await self.start()
        self.assertEqual(session.index, 1)
        self.assertEqual(session.phase, 'playing')

    async def test_first_url_that_buffers_then_turns_off_still_tries_next(self):
        first = self.catalogue['Trójka'][0][0]
        self.buffer_urls.add(first)

        async def before(player, url):
            if url == first:
                self.hass.loop.call_later(0.001, self.set_state, player, 'off')

        self.before_play = before
        session = await self.start()
        self.assertEqual(session.index, 1)
        self.assertEqual(session.phase, 'playing')
        self.assertEqual(len(self.calls), 2)

    async def test_playback_keeps_callers_user_context(self):
        context = Context(user_id='test-user')
        await self.controller.play(KITCHEN, 'Trójka', context=context)
        await self.flush()
        session = self.controller.sessions[KITCHEN]
        self.assertEqual(session.command_context.user_id, 'test-user')
        self.assertEqual(session.command_context.parent_id, context.id)

    async def test_all_six_dead_urls_stop_after_one_initial_pass(self):
        self.fail_urls.update(item[0] for item in self.catalogue['Trójka'])
        session = await self.start()
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(session.phase, 'failed')
        self.assertFalse(session.desired_playing)

    async def test_two_users_capture_device_and_station_before_lookup(self):
        searching = asyncio.Event()
        release = asyncio.Event()

        async def resolve(station, query):
            if station == 'Trójka':
                searching.set()
                await release.wait()
            return await self.resolve(station, query)

        self.controller.resolve_streams.side_effect = resolve
        first = asyncio.create_task(self.controller.play())
        await searching.wait()
        self.controller.player = SALON
        self.controller.station = 'Jazz'
        second = await self.start(SALON, 'Jazz')
        release.set()
        await first
        await self.flush()
        first_session = self.controller.sessions[KITCHEN]
        self.assertEqual(first_session.station, 'Trójka')
        self.assertEqual(second.station, 'Jazz')
        self.assertEqual(set(self.calls), {
            (KITCHEN, self.catalogue['Trójka'][0][0]),
            (SALON, self.catalogue['Jazz'][0][0]),
        })
        self.assertEqual(self.controller.stream_url, second.url)

    async def test_recovery_uses_current_then_next_url_only_on_affected_player(self):
        kitchen = await self.start()
        salon = await self.start(SALON, 'Jazz')
        self.controller.player = SALON
        await StationSelect(self.controller).async_select_option('Jazz')
        self.calls.clear()
        original = kitchen.url
        self.fail_urls.add(original)
        self.set_state(KITCHEN, 'idle', original, 'radio-app')
        await self.settle()
        self.assertEqual(self.calls, [(KITCHEN, original), (KITCHEN, self.catalogue['Trójka'][1][0])])
        self.assertEqual(kitchen.station, 'Trójka')
        self.assertEqual(kitchen.phase, 'playing')
        self.assertEqual(salon.phase, 'playing')
        self.assertEqual(self.hass.states.get(SALON).attributes['media_content_id'], salon.url)

    async def test_recovery_retries_working_current_url(self):
        session = await self.start()
        self.calls.clear()
        self.set_state(KITCHEN, 'idle', session.url, 'radio-app')
        await self.settle()
        self.assertEqual(self.calls, [(KITCHEN, session.url)])
        self.assertEqual(session.phase, 'playing')

    async def test_brief_idle_recovers_itself_without_service_call(self):
        session = await self.start()
        self.calls.clear()
        self.set_state(KITCHEN, 'idle', session.url, 'radio-app')
        await self.flush()
        self.set_state(KITCHEN, 'playing', session.url, 'radio-app')
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_spotify_takeover_is_never_overwritten(self):
        session = await self.start()
        self.calls.clear()
        self.set_state(KITCHEN, 'playing', 'spotify:track:new', 'spotify-app')
        await self.flush()
        self.assertEqual(session.phase, 'released')
        self.set_state(KITCHEN, 'idle')
        await self.settle()
        self.assertEqual(self.calls, [])
        self.assertFalse(session.desired_playing)

    async def test_spotify_during_recovery_grace_cancels_retry(self):
        session = await self.start()
        self.calls.clear()
        self.set_state(KITCHEN, 'idle', session.url, 'radio-app')
        await self.flush()
        task = session.task
        self.set_state(KITCHEN, 'playing', 'spotify:track:new', 'spotify-app')
        await self.flush()
        await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(self.calls, [])
        self.assertFalse(session.desired_playing)

    async def test_spotify_cancels_inflight_retry_without_trying_next_url(self):
        session = await self.start()
        entered = asyncio.Event()
        gate = asyncio.Event()

        async def before_play(player, url):
            entered.set()
            await gate.wait()

        self.before_play = before_play
        self.calls.clear()
        self.set_state(KITCHEN, 'idle', session.url, 'radio-app')
        await entered.wait()
        self.set_state(KITCHEN, 'playing', 'spotify:track:new', 'spotify-app')
        await self.flush()
        gate.set()
        await asyncio.gather(session.task, return_exceptions=True)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.hass.states.get(KITCHEN).attributes['app_id'], 'spotify-app')

    async def test_new_app_even_with_old_media_id_relinquishes_session(self):
        session = await self.start()
        self.set_state(KITCHEN, 'playing', session.url, 'spotify-app')
        await self.flush()
        self.assertEqual(session.phase, 'released')

    async def test_unknown_playing_source_is_not_overwritten(self):
        session = await self.start()
        self.calls.clear()
        self.set_state(KITCHEN, 'playing')
        await self.flush()
        self.assertEqual(session.phase, 'released')
        self.assertEqual(self.calls, [])

    async def test_player_without_media_id_plays_without_automatic_recovery(self):
        self.no_identity_urls.add(self.catalogue['Trójka'][0][0])
        session = await self.start()
        self.assertEqual(session.phase, 'playing')
        self.assertFalse(session.confirmed)
        self.calls.clear()
        self.set_state(KITCHEN, 'idle')
        await self.settle()
        self.assertEqual(self.calls, [])

    async def test_explicit_external_stop_to_idle_disarms_recovery(self):
        session = await self.start()
        self.calls.clear()
        await self.hass.services.async_call('media_player', 'media_stop',
                                            {'entity_id': KITCHEN}, blocking=True)
        await self.settle()
        self.assertEqual(self.calls, [])
        self.assertFalse(session.desired_playing)

    async def test_pause_and_off_do_not_restart_radio(self):
        for state in ('paused', 'off'):
            with self.subTest(state=state):
                session = await self.start()
                self.calls.clear()
                self.set_state(KITCHEN, state, session.url, 'radio-app')
                await self.settle()
                self.assertEqual(self.calls, [])
                self.assertFalse(session.desired_playing)

    async def test_control_stop_cancels_pending_recovery(self):
        session = await self.start()
        self.calls.clear()
        self.set_state(KITCHEN, 'idle', session.url, 'radio-app')
        await self.flush()
        await self.controller.command('media_stop')
        await self.settle()
        self.assertEqual(self.calls, [])
        self.assertFalse(session.desired_playing)

    async def test_recovery_is_bounded_when_every_candidate_breaks(self):
        session = await self.start()
        self.fail_urls.update(item[0] for item in session.streams)
        self.calls.clear()
        self.set_state(KITCHEN, 'idle', session.url, 'radio-app')
        await self.settle()
        self.assertEqual(len(self.calls), 18)
        self.assertEqual(session.phase, 'failed')
        self.assertFalse(session.desired_playing)
        self.assertEqual(self.controller.resolve_streams.await_count, 3)

    async def test_unload_cancels_recovery_without_device_commands(self):
        session = await self.start()
        self.calls.clear()
        self.set_state(KITCHEN, 'idle', session.url, 'radio-app')
        await self.flush()
        await self.controller.async_shutdown()
        self.assertEqual(self.calls, [])
        self.assertTrue(session.task.done())

    async def test_recovery_refreshes_urls_if_original_candidates_all_fail(self):
        session = await self.start()
        self.fail_urls.update(item[0] for item in session.streams)
        original = session.url
        fresh = 'https://radio.test/new-stream'
        self.catalogue['Trójka'] = [(fresh, 'audio/mpeg', None)]
        self.calls.clear()
        self.set_state(KITCHEN, 'idle', original, 'radio-app')
        await self.settle()
        self.assertEqual(self.calls[-1], (KITCHEN, fresh))
        self.assertEqual(len(self.calls), 7)
        self.assertEqual(session.phase, 'playing')

    async def test_unknown_source_starting_during_url_refresh_is_left_alone(self):
        session = await self.start()
        self.fail_urls.update(item[0] for item in session.streams)
        searching = asyncio.Event()
        release = asyncio.Event()

        async def resolve(station, query):
            searching.set()
            await release.wait()
            return await self.resolve(station, query)

        self.controller.resolve_streams.side_effect = resolve
        self.calls.clear()
        self.set_state(KITCHEN, 'idle', session.url, 'radio-app')
        await searching.wait()
        self.set_state(KITCHEN, 'playing')
        await self.flush()
        release.set()
        await self.settle()
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(session.phase, 'released')
        self.assertEqual(self.hass.states.get(KITCHEN).state, 'playing')

    async def test_external_stop_targeting_area_disarms_session(self):
        session = await self.start()
        self.calls.clear()
        with patch('custom_components.intuibase_radio.controller.target_helpers.async_extract_referenced_entity_ids',
                   return_value=SimpleNamespace(referenced=set(), indirectly_referenced={KITCHEN})):
            self.hass.bus.async_fire(EVENT_CALL_SERVICE, {
                'domain': 'media_player', 'service': 'media_stop',
                'service_data': {'area_id': 'kitchen'},
            })
            await self.flush()
        self.set_state(KITCHEN, 'idle', session.url, 'radio-app')
        await self.settle()
        self.assertFalse(session.desired_playing)
        self.assertEqual(self.calls, [])

    async def test_new_app_without_prior_app_identity_is_not_overwritten(self):
        session = await self.start()
        session.app_id = None
        self.calls.clear()
        self.set_state(KITCHEN, 'idle', app='spotify-app')
        await self.settle()
        self.assertEqual(session.phase, 'released')
        self.assertEqual(self.calls, [])

    async def test_unavailable_player_recovers_without_switching_target(self):
        session = await self.start()
        self.calls.clear()
        self.set_state(KITCHEN, 'unavailable')
        await self.flush()
        self.controller.player = SALON
        self.set_state(KITCHEN, 'idle', session.url, 'radio-app')
        await self.settle()
        self.assertEqual(self.calls, [(KITCHEN, session.url)])
        self.assertEqual(session.phase, 'playing')

    async def test_explicit_foreign_play_before_state_update_disarms_session(self):
        session = await self.start()
        self.calls.clear()
        self.hass.bus.async_fire(EVENT_CALL_SERVICE, {
            'domain': 'media_player', 'service': 'play_media',
            'service_data': {'entity_id': KITCHEN, 'media_content_id': 'spotify:track:new'},
        })
        await self.flush()
        self.set_state(KITCHEN, 'idle', session.url, 'radio-app')
        await self.settle()
        self.assertEqual(session.phase, 'released')
        self.assertEqual(self.calls, [])

    async def test_new_play_on_same_device_cancels_older_search(self):
        searching = asyncio.Event()
        never = asyncio.Event()

        async def resolve(station, query):
            if station == 'Trójka':
                searching.set()
                await never.wait()
            return await self.resolve(station, query)

        self.controller.resolve_streams.side_effect = resolve
        old = asyncio.create_task(self.controller.play(KITCHEN, 'Trójka'))
        await searching.wait()
        await self.start(KITCHEN, 'Jazz')
        await old
        self.assertEqual(self.calls, [(KITCHEN, self.catalogue['Jazz'][0][0])])
        self.assertEqual(self.controller.sessions[KITCHEN].station, 'Jazz')

    async def test_next_stream_uses_selected_devices_playing_station(self):
        await self.start()
        self.controller.station = 'Jazz'
        self.calls.clear()
        await self.controller.switch_stream(1)
        await self.flush()
        self.assertEqual(self.calls, [(KITCHEN, self.catalogue['Trójka'][1][0])])
        self.assertEqual(self.controller.sessions[KITCHEN].station, 'Trójka')

    async def test_diagnostics_expose_independent_sessions(self):
        kitchen = await self.start()
        salon = await self.start(SALON, 'Jazz')
        sessions = RadioStatus(self.controller).extra_state_attributes['playback_sessions']
        self.assertEqual(sessions[KITCHEN]['stream_url'], kitchen.url)
        self.assertEqual(sessions[SALON]['station'], 'Jazz')
        self.controller.player = SALON
        self.controller.show_session()
        self.assertEqual(self.controller.stream_url, salon.url)

    async def test_player_title_changes_publish_without_restarting_playback(self):
        session = await self.start()
        self.calls.clear()
        self.set_state(KITCHEN, 'playing', session.url, 'radio-app',
                       media_title='First song', media_artist='Artist', media_album_name='Album')
        await self.flush()
        player = InternetRadioPlayer(self.controller)
        self.assertEqual(player.media_title, 'First song')
        self.assertEqual(player.media_artist, 'Artist')
        self.assertEqual(player.media_album_name, 'Album')
        self.set_state(KITCHEN, 'playing', session.url, 'radio-app', media_title='Next programme')
        await self.flush()
        self.assertEqual(player.media_title, 'Next programme')
        self.assertIsNone(player.media_artist)
        attributes = RadioStatus(self.controller).extra_state_attributes
        self.assertEqual(attributes['media_title'], 'Next programme')
        self.assertEqual(attributes['metadata_source'], 'player')
        self.assertIsNotNone(attributes['metadata_updated_at'])
        self.assertTrue(session.confirmed)
        self.assertEqual(self.calls, [])

    async def test_two_outputs_keep_separate_now_playing_information(self):
        kitchen = await self.start()
        salon = await self.start(SALON, 'Jazz')
        self.set_state(KITCHEN, 'playing', kitchen.url, 'radio-app', media_title='Kitchen song')
        self.set_state(SALON, 'playing', salon.url, 'radio-app', media_title='Salon song')
        await self.flush()
        self.assertEqual(self.controller.now_playing.title, 'Kitchen song')
        self.controller.player = SALON
        self.controller.show_session()
        self.assertEqual(self.controller.now_playing.title, 'Salon song')
        sessions = RadioStatus(self.controller).extra_state_attributes['playback_sessions']
        self.assertEqual(sessions[KITCHEN]['media_title'], 'Kitchen song')
        self.assertEqual(sessions[SALON]['media_title'], 'Salon song')

    async def test_icy_fallback_and_player_metadata_priority(self):
        self.controller.metadata_reader.read.return_value = NowPlaying('Stream song', 'Stream artist', source='stream')
        session = await self.start()
        await asyncio.sleep(0)
        self.assertEqual(session.now_playing.title, 'Stream song')
        self.assertEqual(session.now_playing.source, 'stream')
        self.set_state(KITCHEN, 'playing', session.url, 'radio-app',
                       media_title='Player song', media_artist='Player artist')
        await self.flush()
        self.assertEqual(session.now_playing.title, 'Player song')
        self.assertEqual(session.now_playing.source, 'player')

    async def test_metadata_failure_never_restarts_or_stops_playback(self):
        self.controller.metadata_reader.read.side_effect = RuntimeError('Metadata unavailable')
        session = await self.start()
        await asyncio.sleep(0)
        self.assertIsNone(session.now_playing)
        self.assertEqual(session.phase, 'playing')
        self.assertTrue(session.desired_playing)
        self.assertEqual(len(self.calls), 1)

    async def test_spotify_clears_radio_metadata_and_cancels_reader(self):
        session = await self.start()
        self.set_state(KITCHEN, 'playing', session.url, 'radio-app', media_title='Radio song')
        await self.flush()
        task = session.metadata_task
        self.set_state(KITCHEN, 'playing', 'spotify:track:new', 'spotify-app', media_title='Spotify song')
        await self.flush()
        self.assertEqual(session.phase, 'released')
        self.assertIsNone(session.now_playing)
        self.assertIsNone(self.controller.metadata_attributes['media_title'])
        self.assertTrue(task.done())

    async def test_stop_clears_title_and_reader(self):
        session = await self.start()
        self.set_state(KITCHEN, 'playing', session.url, 'radio-app', media_title='Radio song')
        await self.flush()
        task = session.metadata_task
        await self.controller.command('media_stop')
        await self.flush()
        self.assertIsNone(session.now_playing)
        self.assertTrue(task.done())
        self.assertEqual(InternetRadioPlayer(self.controller).media_title, 'Trójka')

    async def test_old_metadata_response_cannot_update_new_session(self):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def read(url):
            if 'Trójka' in url:
                entered.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    await release.wait()
                return NowPlaying('Old station song', source='stream')
            return NowPlaying('New station song', source='stream')

        self.controller.metadata_reader.read.side_effect = read
        try:
            old = await self.start()
            await entered.wait()
            old_task = old.metadata_task
            new = await self.start(KITCHEN, 'Jazz')
        finally:
            release.set()
        await old_task
        await self.flush()
        self.assertIsNone(old.now_playing)
        self.assertEqual(new.now_playing.title, 'New station song')
        self.assertEqual(self.controller.now_playing.title, 'New station song')

    async def test_expired_stream_metadata_is_removed(self):
        self.controller.metadata_reader.read.return_value = NowPlaying('Old song', source='stream')
        session = await self.start()
        await asyncio.sleep(0)
        self.assertIsNotNone(session.now_playing)
        session._stream_metadata_at -= 121
        session.refresh_metadata(self.hass.states.get(KITCHEN))
        self.assertIsNone(session.now_playing)


if __name__ == '__main__':
    unittest.main()
