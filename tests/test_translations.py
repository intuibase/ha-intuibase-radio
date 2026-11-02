"""Check complete form, entity and runtime translations."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from custom_components.intuibase_radio.controller import RadioController
from custom_components.intuibase_radio.dashboard import RadioDashboard
from custom_components.intuibase_radio.localize import GERMAN, translate

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/intuibase_radio'


def leaves(value, prefix=''):
    result = {}
    for key, item in value.items():
        path = f'{prefix}.{key}' if prefix else key
        if isinstance(item, dict):
            result.update(leaves(item, path))
        else:
            result[path] = item
    return result


class TranslationTests(unittest.TestCase):
    def test_form_and_entity_translations_have_all_keys(self):
        base = json.loads((ROOT / 'strings.json').read_text())
        for language in ['en', 'pl', 'de']:
            with self.subTest(language=language):
                translated = json.loads((ROOT / f'translations/{language}.json').read_text())
                self.assertEqual(leaves(base).keys(), leaves(translated).keys())
                self.assertTrue(all(isinstance(value, str) and value.strip()
                                    for value in leaves(translated).values()))
                if language == 'en':
                    self.assertEqual(base, translated)

    def test_all_runtime_labels_have_german_translations(self):
        for path in ROOT.glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == '_t'):
                    label = ast.literal_eval(node.args[0])
                    with self.subTest(file=path.name, label=label):
                        self.assertIn(label, GERMAN)

    def test_language_variants_and_fallback(self):
        for language, expected in [('en', 'Ready'), ('en-GB', 'Ready'), ('fr', 'Ready'),
                                   (None, 'Ready'), ('', 'Ready'), ('pl-PL', 'Gotowe'),
                                   ('PL_pl', 'Gotowe'), ('de-DE', 'Bereit'), ('DE_at', 'Bereit')]:
            with self.subTest(language=language):
                self.assertEqual(translate(language, 'Ready', 'Gotowe'), expected)
        self.assertEqual(translate('de', 'New label', 'Nowa etykieta'), 'New label')

    def test_controller_and_dashboard_languages(self):
        for language, ready, diagnostics, volume in [
            ('en', 'Ready', 'Diagnostics', 'Volume'),
            ('pl', 'Gotowe', 'Diagnostyka', 'Głośność'),
            ('de', 'Bereit', 'Diagnose', 'Lautstärke'),
            ('es', 'Ready', 'Diagnostics', 'Volume'),
        ]:
            with self.subTest(language=language):
                hass = SimpleNamespace(config=SimpleNamespace(language=language))
                controller = RadioController(hass, SimpleNamespace(options={}))
                self.assertEqual(controller.short_status, ready)
                dashboard = RadioDashboard(hass, 'Radio', 'test-entry', None)._config()
                self.assertEqual(dashboard['views'][1]['title'], diagnostics)
                self.assertIn(volume, json.dumps(dashboard, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
