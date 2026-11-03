"""Tests using Home Assistant's actual configuration and entity APIs."""
import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.core import State

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.intuibase_radio.config_flow import (
    InternetRadioConfigFlow, InternetRadioOptionsFlow,
)
from custom_components.intuibase_radio.const import CONF_STATIONS, STATIONS
from custom_components.intuibase_radio.controller import RadioController
from custom_components.intuibase_radio.media_player import InternetRadioPlayer
from custom_components.intuibase_radio.number import RadioVolume
from custom_components.intuibase_radio.select import PlayerSelect, StationSelect
from custom_components.intuibase_radio.stations import format_stations, parse_stations


class StationTests(unittest.TestCase):
    def test_builtin_round_trip(self):
        self.assertEqual(parse_stations(format_stations(STATIONS)), STATIONS)

    def test_custom_order_queries_and_whitespace(self):
        self.assertEqual(parse_stations(' Radio 357 \n\n Jedynka = Polskie Radio 1 \nBBC '),
                         {'Radio 357': 'Radio 357', 'Jedynka': 'Polskie Radio 1', 'BBC': 'BBC'})

    def test_invalid_lists(self):
        for value in ['', ' \n ', '= query', 'Name = ', 'BBC\nbbc = another']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_stations(value)


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def make_hass(self):
        hass = MagicMock()
        hass.config.language = 'pl'
        return hass

    def options_flow(self, options):
        flow = InternetRadioOptionsFlow()
        flow.hass = self.make_hass()
        flow.handler = 'test_entry'
        flow.hass.config_entries.async_get_known_entry.return_value = SimpleNamespace(options=options)
        return flow

    async def test_existing_entry_defaults(self):
        flow = self.options_flow({})
        result = await flow.async_step_init()
        self.assertEqual(result['type'], 'form')
        values = result['data_schema']({})
        self.assertEqual(parse_stations(values[CONF_STATIONS]), STATIONS)
        self.assertTrue(flow.automatic_reload)

    async def test_saved_list_defaults_and_preserves_player(self):
        options = {'stations': {'My radio': 'different query'}, 'target_player': 'media_player.kitchen',
                   'excluded_players': ['media_player.tv'], 'dashboard_name': 'Music'}
        flow = self.options_flow(options)
        result = await flow.async_step_init()
        self.assertEqual(result['data_schema']({})['stations'], 'My radio = different query')
        result = await flow.async_step_init({'stations': 'BBC\nMy radio = query'})
        self.assertEqual(result['type'], 'create_entry')
        self.assertEqual(result['data']['stations'], {'BBC': 'BBC', 'My radio': 'query'})
        self.assertEqual(result['data']['target_player'], options['target_player'])
        self.assertEqual(result['data']['excluded_players'], options['excluded_players'])

    async def test_invalid_input_keeps_form_and_text(self):
        for flow, step in [(self.options_flow({}), 'async_step_init'),
                           (InternetRadioConfigFlow(), 'async_step_user')]:
            if flow.hass is None:
                flow.hass = self.make_hass()
            result = await getattr(flow, step)({'stations': 'BBC\nbbc'})
            self.assertEqual(result['errors'], {'stations': 'invalid_stations'})
            self.assertEqual(result['data_schema']({})['stations'], 'BBC\nbbc')

    async def test_initial_setup_saves_parsed_catalogue(self):
        flow = InternetRadioConfigFlow()
        flow.hass = self.make_hass()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        result = await flow.async_step_user({'stations': 'My radio = my query'})
        self.assertEqual(result['options']['stations'], {'My radio': 'my query'})

    async def test_controller_entities_and_query(self):
        hass = self.make_hass()
        entry = SimpleNamespace(options={'stations': {'Custom radio': 'search this', 'BBC': 'BBC'}})
        controller = RadioController(hass, entry)
        self.assertEqual(controller.station, 'Custom radio')
        self.assertEqual(StationSelect(controller).options, ['Custom radio', 'BBC'])
        player = InternetRadioPlayer(controller)
        self.assertEqual(player.source_list, ['Custom radio', 'BBC'])
        await player.async_select_source('BBC')
        self.assertEqual(controller.station, 'BBC')
        await player.async_select_source('not configured')
        self.assertEqual(controller.station, 'BBC')
        await player.async_select_source('Custom radio')
        response = AsyncMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = [{'name': 'search this', 'url_resolved': 'https://radio.test/live'}]
        session = MagicMock()
        session.get.return_value.__aenter__ = AsyncMock(return_value=response)
        session.get.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch('custom_components.intuibase_radio.controller.ClientSession') as factory:
            factory.return_value.__aenter__ = AsyncMock(return_value=session)
            factory.return_value.__aexit__ = AsyncMock(return_value=False)
            streams = await controller.resolve_streams()
        self.assertEqual(session.get.call_args.kwargs['params']['name'], 'search this')
        self.assertEqual(streams[0][0], 'https://radio.test/live')

    async def test_controller_without_saved_catalogue(self):
        controller = RadioController(self.make_hass(), SimpleNamespace(options={}))
        self.assertEqual(controller.stations, STATIONS)
        self.assertEqual(InternetRadioPlayer(controller).source_list, list(STATIONS))

    async def test_destination_reads_volume_and_notifies_slider(self):
        for reported_volume, refresh_error in [(0.72, None), (None, None),
                                                (0.72, RuntimeError('offline'))]:
            with self.subTest(volume=reported_volume, error=refresh_error):
                hass = self.make_hass()
                entry = SimpleNamespace(options={'target_player': 'media_player.kitchen'})
                controller = RadioController(hass, entry)
                states = {
                    entity_id: State(entity_id, 'idle', {
                        'friendly_name': name,
                        'supported_features': int(MediaPlayerEntityFeature.PLAY_MEDIA),
                        'volume_level': volume,
                    })
                    for entity_id, name, volume in [
                        ('media_player.kitchen', 'Kitchen', 0.2),
                        ('media_player.bedroom', 'Bedroom', 0.4),
                    ]
                }
                hass.states.async_all.side_effect = lambda domain: list(states.values())
                hass.states.get.side_effect = states.get
                registry = MagicMock()
                registry.async_get.return_value = None

                async def refresh(hass_arg, entity_id):
                    if refresh_error:
                        raise refresh_error
                    attributes = dict(states[entity_id].attributes)
                    attributes.pop('volume_level')
                    if reported_volume is not None:
                        attributes['volume_level'] = reported_volume
                    states[entity_id] = State(entity_id, 'idle', attributes)

                with (patch('custom_components.intuibase_radio.controller.er.async_get', return_value=registry),
                      patch('custom_components.intuibase_radio.controller.dr.async_get', return_value=registry),
                      patch('custom_components.intuibase_radio.controller.async_update_entity',
                            new=AsyncMock(side_effect=refresh)) as update):
                    controller.refresh_players()
                    volume = RadioVolume(controller)
                    observed = []
                    controller.add_listener(lambda: observed.append(volume.native_value))
                    await PlayerSelect(controller).async_select_option('Bedroom')
                    update.assert_awaited_once_with(hass, 'media_player.bedroom')
                    expected = 40 if refresh_error else (20 if reported_volume is None else 72)
                    self.assertEqual(volume.native_value, expected)
                    self.assertTrue(volume.available)
                    self.assertEqual(observed[-1], expected)
                    self.assertEqual(controller.player, 'media_player.bedroom')
                    hass.config_entries.async_update_entry.assert_called_once_with(
                        entry, options={'target_player': 'media_player.bedroom'})
                    hass.services.async_call.assert_not_called()

    def volume_controller(self):
        hass = self.make_hass()
        controller = RadioController(
            hass, SimpleNamespace(options={'target_player': 'media_player.kitchen'}))
        states = {
            f'media_player.{name.lower()}': State(f'media_player.{name.lower()}', 'idle', {
                'friendly_name': name,
                'supported_features': int(MediaPlayerEntityFeature.PLAY_MEDIA),
                'volume_level': volume,
            }) for name, volume in [('Kitchen', 0.2), ('Bedroom', 0.4)]
        }
        hass.states.async_all.side_effect = lambda domain: list(states.values())
        hass.states.get.side_effect = states.get
        registry = MagicMock()
        registry.async_get.return_value = None
        for name in ('er', 'dr'):
            self.enterContext(patch(
                f'custom_components.intuibase_radio.controller.{name}.async_get',
                return_value=registry))
        controller.refresh_players()
        return hass, controller, states

    async def test_rapid_destination_changes_ignore_outdated_reads(self):
        for completion_order in [(0, 1, 2), (2, 1, 0)]:
            with self.subTest(order=completion_order):
                hass, controller, states = self.volume_controller()
                pending = []

                async def refresh(hass_arg, entity_id):
                    future = asyncio.get_running_loop().create_future()
                    pending.append(future)
                    await future

                with patch('custom_components.intuibase_radio.controller.async_update_entity',
                           new=AsyncMock(side_effect=refresh)):
                    tasks = []
                    volume = RadioVolume(controller)
                    for name in ['Bedroom', 'Kitchen', 'Bedroom']:
                        tasks.append(asyncio.create_task(
                            PlayerSelect(controller).async_select_option(name)))
                        await asyncio.sleep(0)
                        self.assertEqual(volume.native_value, 20)
                        self.assertTrue(volume.available)
                    for index in completion_order:
                        pending[index].set_result(None)
                        await tasks[index]
                        if not tasks[2].done():
                            self.assertEqual(volume.native_value, 20)
                        else:
                            self.assertEqual(volume.native_value, 40)
                            self.assertTrue(volume.available)
                    self.assertEqual(controller.player, 'media_player.bedroom')
                    self.assertTrue(controller.status.endswith('Bedroom'))
                    hass.services.async_call.assert_not_called()

    async def test_inflight_volume_write_does_not_change_new_destination_slider(self):
        hass, controller, states = self.volume_controller()
        started = asyncio.Event()
        finished = asyncio.Event()

        async def write(*args, **kwargs):
            started.set()
            await finished.wait()

        hass.services.async_call = AsyncMock(side_effect=write)
        task = asyncio.create_task(controller.set_volume(0.9))
        await started.wait()
        with patch('custom_components.intuibase_radio.controller.async_update_entity',
                   new=AsyncMock()):
            await controller.select_player('media_player.bedroom')
        finished.set()
        await task
        self.assertEqual(RadioVolume(controller).native_value, 40)
        hass.services.async_call.assert_awaited_once_with(
            'media_player', 'volume_set',
            {'entity_id': 'media_player.kitchen', 'volume_level': 0.9}, blocking=True)

    async def test_missing_volume_preserves_slider_and_allows_manual_control(self):
        hass, controller, states = self.volume_controller()
        attributes = dict(states['media_player.bedroom'].attributes)
        attributes.pop('volume_level')
        states['media_player.bedroom'] = State('media_player.bedroom', 'off', attributes)
        hass.services.async_call = AsyncMock()
        with patch('custom_components.intuibase_radio.controller.async_update_entity',
                   new=AsyncMock()):
            await controller.select_player('media_player.bedroom')
        volume = RadioVolume(controller)
        self.assertTrue(volume.available)
        self.assertEqual(volume.native_value, 20)
        hass.services.async_call.assert_not_called()
        await volume.async_set_native_value(65)
        controller.refresh_players()
        self.assertTrue(volume.available)
        self.assertEqual(volume.native_value, 65)
        hass.services.async_call.assert_awaited_once_with(
            'media_player', 'volume_set',
            {'entity_id': 'media_player.bedroom', 'volume_level': 0.65}, blocking=True)

    async def test_first_device_without_volume_keeps_slider_available(self):
        hass, controller, states = self.volume_controller()
        controller.volume = 0.35
        for entity_id, state in list(states.items()):
            attributes = dict(state.attributes)
            attributes.pop('volume_level')
            states[entity_id] = State(entity_id, 'off', attributes)
        controller.refresh_players()
        self.assertEqual(RadioVolume(controller).native_value, 35)
        self.assertTrue(RadioVolume(controller).available)

    async def test_play_keeps_device_volume(self):
        hass, controller, states = self.volume_controller()
        hass.services.async_call = AsyncMock()
        controller.resolve_streams = AsyncMock(
            return_value=[('https://radio.test/live', 'music', None)])
        controller._play_stream = AsyncMock()
        await controller.play()
        controller._play_stream.assert_awaited_once_with(0)
        hass.services.async_call.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
