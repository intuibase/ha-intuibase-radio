"""Validate a stable release tag and extract its documented changes."""

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'custom_components/intuibase_radio/manifest.json'
CHANGELOG = ROOT / 'docs/CHANGELOG.md'
TAG_PATTERN = re.compile(r'v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', re.ASCII)
HEADING_PATTERN = re.compile(r'^## \[([^\]\r\n]+)\](?:[^\r\n]*)$', re.MULTILINE)


def extract_notes(tag: str, version: str, changelog: str) -> str:
    """Reject mismatches, absent entries and empty release notes."""
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError('Expected a stable version tag such as v0.3.5')
    if tag[1:] != version:
        raise ValueError(f'Tag {tag} does not match manifest version {version}')
    headings = list(HEADING_PATTERN.finditer(changelog))
    matches = [heading for heading in headings if heading.group(1) == version]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one ## [{version}] entry in docs/CHANGELOG.md')
    heading = matches[0]
    # Stop at any level-two heading, including sections not using version brackets.
    next_heading = re.search(r'^##(?:\s|$)', changelog[heading.end():], re.MULTILINE)
    end = heading.end() + next_heading.start() if next_heading else len(changelog)
    notes = changelog[heading.end():end].strip()
    # Subheadings, comments and blank list markers alone are not release notes.
    content = re.sub(r'<!--.*?-->', '', notes, flags=re.DOTALL)
    content = re.sub(r'^#{1,6}\s.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*[-*+]\s*$', '', content, flags=re.MULTILINE).strip()
    if not content:
        raise ValueError(f'Changelog entry for {version} has no release notes')
    return notes + '\n'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
        notes = extract_notes(args.tag, manifest['version'], CHANGELOG.read_text(encoding='utf-8'))
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f'Release validation failed: {error}\n')
    args.output.write_text(notes, encoding='utf-8')
    print(f'Validated {args.tag}; release notes written to {args.output}')


if __name__ == '__main__':
    main()
