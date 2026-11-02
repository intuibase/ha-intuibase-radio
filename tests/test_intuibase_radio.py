"""Tests using Home Assistant's actual configuration and entity APIs."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.intuibase_radio.config_flow import (
    InternetRadioConfigFlow, InternetRadioOptionsFlow,
)
from custom_components.intuibase_radio.const import CONF_STATIONS, STATIONS
from custom_components.intuibase_radio.controller import RadioController
from custom_components.intuibase_radio.media_player import InternetRadioPlayer
from custom_components.intuibase_radio.select import StationSelect
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
