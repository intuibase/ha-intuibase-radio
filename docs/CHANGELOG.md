# Changelog

All notable changes to IntuiBase Radio are documented here in English.
The release workflow copies the matching version section into GitHub Release notes.

## [Unreleased]

### Fixed

- Refresh the selected output player's volume when switching destinations so the
  volume slider reflects that device's current level.
- Keep the volume slider available and retain its value if the selected device
  does not report a volume level, including Cast devices in the off state.
- Ignore outdated selections and completed volume writes when switching quickly
  between devices.
- Preserve the destination device's volume when starting a station instead of
  sending the controller's previously remembered level.

## [0.3.5] - 2026-11-02

### Added

- Editable station names and Radio Browser search phrases in integration options.
- Station entries using either a plain name or `Display name = search phrase`.
- English, Polish and German interface translations, with English as the fallback.
- A built-in dashboard with station selection, output player selection, playback
  controls, artwork, volume and connection diagnostics.
- HACS custom repository metadata, installation instructions and an Open in HACS button.
- English dashboard and configuration screenshots in the README.
- Automated tests for configuration, playback queries, translations and frontend cards.
- A tag-triggered release workflow that validates the version, runs tests and
  publishes release notes from this changelog.

### Compatibility

- Tested with Home Assistant 2026.9.2.
- Installation through an authenticated HACS instance has not yet been tested.
