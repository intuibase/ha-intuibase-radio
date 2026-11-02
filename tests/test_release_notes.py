"""Release validation must fail before any GitHub Release is published."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.release_notes import extract_notes


class ReleaseNotesTests(unittest.TestCase):
    def test_extracts_only_the_matching_version(self):
        changelog = ('# Changelog\n\n## [Unreleased]\n- Future work\n\n'
                     '## [0.3.5] - 2026-11-02\n\n### Added\n\n- English, Polish and German.\n\n'
                     '## [0.3.4]\n\n- Older changes.\n')
        self.assertEqual(extract_notes('v0.3.5', '0.3.5', changelog),
                         '### Added\n\n- English, Polish and German.\n')

    def test_rejects_a_mismatching_manifest(self):
        with self.assertRaisesRegex(ValueError, 'does not match'):
            extract_notes('v0.3.6', '0.3.5', '## [0.3.6]\n- Changes')

    def test_rejects_invalid_tags(self):
        for tag in ['0.3.5', 'v0.3', 'v00.3.5', 'v0.3.5-beta.1', 'v0.3.5\n', 'v0.3.5;echo bad']:
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, 'stable version tag'):
                extract_notes(tag, '0.3.5', '## [0.3.5]\n- Changes')

    def test_requires_an_exact_version_heading(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            extract_notes('v0.3.5', '0.3.5', '## [0.3.50]\n- Wrong version')

    def test_rejects_duplicate_entries(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            extract_notes('v0.3.5', '0.3.5', '## [0.3.5]\n- First\n## [0.3.5]\n- Second')

    def test_rejects_empty_notes(self):
        for body in ['', '\n### Added\n', '\n<!-- TODO -->\n', '\n### Added\n-\n']:
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, 'no release notes'):
                extract_notes('v0.3.5', '0.3.5', '## [0.3.5]\n' + body)

    def test_stops_at_other_top_level_sections(self):
        self.assertEqual(extract_notes('v0.3.5', '0.3.5',
                                      '## [0.3.5]\n- Changes\n## Maintainers\nDo not include'),
                         '- Changes\n')

    def test_current_manifest_has_release_notes(self):
        version = json.loads((ROOT / 'custom_components/intuibase_radio/manifest.json').read_text())['version']
        notes = extract_notes(f'v{version}', version, (ROOT / 'docs/CHANGELOG.md').read_text())
        self.assertIn('### Added', notes)
        self.assertNotIn('[Unreleased]', notes)


if __name__ == '__main__':
    unittest.main()
