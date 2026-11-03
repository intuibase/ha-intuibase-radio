"""Station artwork is independent of the first playable audio URL."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.intuibase_radio.controller import RadioController


class ArtworkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.controller = RadioController(
            SimpleNamespace(config=SimpleNamespace(language='en')),
            SimpleNamespace(options={'stations': {'Polskie Radio Trójka': 'Trójka'}}))

    def response(self, content_type='image/png', error=None, results=None):
        response = MagicMock()
        response.headers = {'Content-Type': content_type}
        response.raise_for_status.side_effect = error
        response.json = AsyncMock(return_value=results)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        return context

    def session(self, responses):
        session = MagicMock()
        session.get.side_effect = responses
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=session)
        context.__aexit__ = AsyncMock(return_value=False)
        return context, session

    async def test_bad_first_image_uses_next_and_caches_success(self):
        context, session = self.session([
            self.response(error=RuntimeError('402 Payment Required')),
            self.response(),
        ])
        candidates = ['https://images.test/broken.jpg', 'https://images.test/trojka.png']
        with patch('custom_components.intuibase_radio.controller.ClientSession', return_value=context):
            image = await self.controller.resolve_station_image(candidates)
            cached = await self.controller.resolve_station_image(candidates)
        self.assertEqual(image, candidates[1])
        self.assertEqual(cached, image)
        self.assertEqual(session.get.call_count, 2)

    async def test_non_image_response_and_missing_images_do_not_block_radio(self):
        context, session = self.session([self.response('text/html')])
        with patch('custom_components.intuibase_radio.controller.ClientSession', return_value=context):
            self.assertIsNone(await self.controller.resolve_station_image(['https://images.test/page']))
            self.assertIsNone(await self.controller.resolve_station_image([]))
        self.assertEqual(session.get.call_count, 1)

    async def test_image_host_requiring_identified_client_is_supported(self):
        context, session = self.session([])
        image = 'https://images.test/Radió.jpg'

        def request(url, **kwargs):
            agent = kwargs.get('headers', {}).get('User-Agent', '')
            if 'IntuiBase-Radio' not in agent or 'github.com/intuibase/ha-intuibase-radio' not in agent:
                return self.response(error=RuntimeError('403 Forbidden'))
            return self.response('image/jpeg')

        session.get.side_effect = request
        with patch('custom_components.intuibase_radio.controller.ClientSession', return_value=context):
            self.assertEqual(await self.controller.resolve_station_image([image]), image)

    async def test_audio_order_preserved_with_one_working_station_logo(self):
        results = [
            {'name': 'Trójka', 'url_resolved': 'https://audio.test/first',
             'favicon': 'https://images.test/broken.jpg'},
            {'name': 'Polskie Radio Trójka', 'url_resolved': 'http://audio.test/second',
             'favicon': 'https://images.test/trojka.png'},
            {'name': 'Trójka mp3', 'url_resolved': 'http://audio.test/third', 'favicon': ''},
        ]
        context, session = self.session([self.response(results=results)])
        with (patch('custom_components.intuibase_radio.controller.ClientSession', return_value=context),
              patch.object(self.controller, 'resolve_station_image',
                           new=AsyncMock(return_value='https://images.test/trojka.png')) as image):
            streams = await self.controller.resolve_streams()
        self.assertEqual(streams[0][0], 'https://audio.test/first')
        self.assertEqual(len(streams), 3)
        self.assertEqual({item[2] for item in streams}, {'https://images.test/trojka.png'})
        self.assertEqual(image.call_args.args[0][0], 'https://images.test/trojka.png')
