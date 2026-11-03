# Changelog

All notable changes to IntuiBase Radio are documented here in English.
The release workflow copies the matching version section into GitHub Release notes.

## [Unreleased]

### Added

- Song/programme title, artist and album in the artwork card and native
  media-player entity, independently for each output session.
- Optional ICY `StreamTitle` probes when the player has no metadata, with shared
  per-URL caching, bounded reads, expiry and cancellation on source changes.
- Independent playback sessions and automatic stream recovery for each output
  device, including simultaneous playback of different stations.
- Retry the current URL before trying alternative station streams; use bounded
  recovery rounds and refresh the station's URLs after unsuccessful rounds.
- Relinquish automatic recovery when another source such as Spotify takes over,
  on explicit stop/pause, or when playback identity cannot be established.
- A `play_station` action accepting an output entity and station together, without
  relying on the dashboard's shared selection entities.
- Per-device playback session diagnostics in the radio status sensor.

### Fixed

- Persist station order separately from the station mapping so JSON key sorting
  cannot alphabetize user lists after a restart. Restore the built-in order for
  legacy catalogues extended with custom stations, keeping those additions.
- Include the shipped JavaScript content hash in the frontend resource URL so
  updated cards are fetched even when the integration version is unchanged.
- Identify the integration when fetching favicons so hosts such as Wikimedia do
  not reject station artwork requests from an anonymous HTTP client.
- Choose a working station favicon across Radio Browser results instead of
  displaying a broken image belonging to the selected audio stream.
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
