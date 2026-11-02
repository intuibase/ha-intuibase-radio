# IntuiBase Radio for Home Assistant

IntuiBase Radio is a standalone Home Assistant custom integration for playing
internet radio stations on available `media_player` entities.

The integration does not store stream URLs permanently. When a station is
selected, it searches the global [Radio Browser](https://www.radio-browser.info/)
directory, ranks the results, removes duplicate URLs, and tries the streams in
order. Searches and ranking are not restricted by country. API requests use the
Radio Browser network endpoint with a direct-server fallback and IPv4 transport.

## Features

- editable list of Polish and international stations and search phrases;
- global, dynamic Radio Browser stream lookup;
- automatic discovery of `media_player` entities supporting `play_media`;
- remembered output selection and configurable player exclusions;
- native Home Assistant media-player entity;
- station and output selection;
- play, resume, pause, and stop controls;
- manual previous/next stream fallback controls;
- volume control;
- optional integration-managed Lovelace dashboard;
- station artwork from the Radio Browser `favicon` field;
- connection history containing the attempt number, URL, and error;
- automatic fallback after a playback error, 30 seconds without a connection,
  or 60 seconds of buffering without playback;
- English default interface with Polish and German translations;
- local Home Assistant integration branding.

## Requirements

- Home Assistant with at least one integration exposing a `media_player` entity;
- internet access from Home Assistant for Radio Browser queries;
- network access from the target player to the selected stream URL.

The integration was developed and tested with Home Assistant 2026.9.2.

## Installation

1. Copy the complete `intuibase_radio` directory to:

   ```text
   <config>/custom_components/intuibase_radio
   ```

2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration**.
4. Search for **IntuiBase Radio**.
5. Choose whether to create a dashboard, its name (default: `Radio`), and any
   media players that should be hidden.

No `configuration.yaml` entry is required.

## Dashboard

The optional dashboard provides:

- an always-visible, scrollable station list;
- single-click selection and double-click playback;
- target media-player selection;
- current station artwork;
- play, resume, pause, and stop controls;
- a full-width volume slider;
- a compact connection status card with small previous/next stream fallback
  buttons;
- a separate diagnostics tab with detailed connection history and the native
  `media-control` card.

The dashboard is managed by the integration. Manual changes can be overwritten
when the integration is reloaded or Home Assistant is restarted.

The station list and compact status are local custom cards shipped with the
integration. They are registered automatically; HACS is not required.

Dashboard settings can be changed later through **Settings → Devices & services
→ IntuiBase Radio → Configure**.

## Interface languages

English is the default and the fallback for unsupported languages. Polish and
German translations cover setup, integration options, entity names, dashboard
labels, card hints and playback messages.

- Home Assistant translates forms and entity labels using the user's language.
- Custom radio cards use the language selected in the user's Home Assistant profile.
- Playback messages and generated dashboard labels use the Home Assistant system
  language. Reload the integration after changing the system language to rebuild
  the dashboard.
- Station names and a custom dashboard name stay as entered.

## Playback flow

The **Play station** action:

1. searches Radio Browser globally using the configured station phrase;
2. ranks exact and close name matches, preferring HTTPS when relevance is
   otherwise equal;
3. sets the selected volume on the target player;
4. calls `media_player.play_media` with the direct URL and media type `music`;
5. tries the next unique stream URL after an error or timeout.

The **Resume** action only resumes the existing media session by calling
`media_player.media_play`.

## Station catalogue

Edit the station list in **Settings → Devices & services → IntuiBase Radio
→ Configure**, or during initial setup. Enter one station per line:

```text
Radio 357
Polskie Radio Jedynka = Jedynka
BBC Radio 6 Music
```

A plain name is also its Radio Browser search phrase (`query`). Use
`Display name = search phrase` when they should differ. Add, remove or reorder
lines to change the station list. Blank lines are ignored; station names must
be unique (case-insensitive), and at least one station is required.

Saving options automatically reloads the integration and updates the dashboard,
station selector and media-player sources. Existing installations keep the
built-in catalogue until a custom list is saved. A fixed stream URL and edits
to `const.py` are not required.

## Entities

The integration creates stable, English entity IDs using the
`intuibase_radio_*` prefix:

- `media_player.intuibase_radio_player`;
- `select.intuibase_radio_station`;
- `select.intuibase_radio_play_on`;
- `number.intuibase_radio_volume`;
- `button.intuibase_radio_play_station`;
- `button.intuibase_radio_resume`;
- `button.intuibase_radio_pause`;
- `button.intuibase_radio_stop`;
- `button.intuibase_radio_previous_stream`;
- `button.intuibase_radio_next_stream`;
- `sensor.intuibase_radio_status`.

Existing installations are migrated to these IDs during setup. Update any
external automations that refer to the former entity IDs.

The status sensor exposes attributes including `station`, `media_player`,
`stream_url`, `stream_attempt`, `stream_attempt_count`, `station_image_url`, and
`activity_log`.

## Google Cast and stereo pairs

Google Cast may expose both individual speakers and a separate stereo-pair
entity. Volume control can work on an individual speaker even when
`play_media` is accepted only by the pair entity, for example:

```text
media_player.kitchen_pair
```

Home Assistant identifies a Cast group by the `Google Cast Group` model but does
not expose a reliable membership relationship for this use case. Individual
players are therefore not hidden automatically; exclude them in the integration
options when necessary.

An error mentioning `CastMediaPlayerEntity._quick_play` comes from Home
Assistant's internal Google Cast implementation. IntuiBase Radio still calls the
standard `media_player.play_media` action.

## Diagnostics

Use the **Diagnostics** dashboard tab to inspect the current stream, attempt
number, and complete activity history. If playback fails:

1. verify that the correct Cast pair or group is selected;
2. open the reported `stream_url` in a browser;
3. inspect `activity_log` in **Developer tools → States**;
4. check the Home Assistant log for
   `custom_components.intuibase_radio.controller`;
5. test the station phrase directly against Radio Browser.

If a stream works in a browser but Cast rejects it, the issue may be related to
the target Cast entity, stereo grouping, codec, redirects, or URL handling by
the Default Media Receiver.

## Privacy and networking

Home Assistant sends the selected station name to the public Radio Browser API.
The target media player then connects directly to the broadcaster's stream.
IntuiBase Radio does not proxy audio through its own server.
