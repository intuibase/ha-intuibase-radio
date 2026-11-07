// Minimal DOM fixture exercises the shipped cards without browser dependencies.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor() {
    this.children = [];
    this.attributes = {};
    this.style = { setProperty() {} };
    this.classList = { add() {} };
  }
  attachShadow() { this.shadowRoot = new Element(); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(name, listener) { (this.listeners ??= {})[name] = listener; }
  querySelector() { return null; }
}
const cards = new Map();
const context = vm.createContext({
  HTMLElement: Element,
  document: { createElement: () => new Element() },
  customElements: { define: (name, card) => cards.set(name, card) },
  window: {}, setTimeout, clearTimeout,
});
vm.runInContext(fs.readFileSync(path.join(__dirname,
  '../custom_components/intuibase_radio/www/internet-radio-card.js'), 'utf8'), context);
function card(type, config = {}) {
  const result = new (cards.get(type))();
  result.setConfig({ entity: 'test.radio', ...config });
  return result;
}
const state = { state: 'BBC', attributes: { options: ['BBC', 'Radio 357'] } };
function hass(language, entity = state) {
  return { language, states: entity ? { 'test.radio': entity } : {} };
}

test('transport buttons track availability and never send disabled actions', () => {
  const transport = card('intuibase-radio-transport', { name: 'PAUSE', icon: 'mdi:pause' });
  let presses = 0;
  const update = (entity) => {
    transport.hass = { ...hass('en', entity), callService(domain, service, data) {
      assert.equal(domain, 'button');
      assert.equal(service, 'press');
      assert.equal(data.entity_id, 'test.radio');
      presses++;
    } };
  };
  assert.equal(transport.button.disabled, true);
  for (const entity of [null, { state: 'unavailable' }]) {
    update(entity);
    assert.equal(transport.button.disabled, true);
    transport.button.listeners.click();
  }
  assert.equal(presses, 0);
  for (const value of ['unknown', '2026-11-07T12:00:00+00:00']) {
    update({ state: value });
    assert.equal(transport.button.disabled, false);
    transport.button.listeners.click();
  }
  assert.equal(presses, 2);
  update({ state: 'unavailable' });
  assert.equal(transport.button.disabled, true);
});

test('frontend translations have matching keys', () => {
  assert.equal(vm.runInContext(`Object.values(RADIO_TRANSLATIONS).every(labels =>
    JSON.stringify(Object.keys(labels).sort()) === JSON.stringify(Object.keys(RADIO_TRANSLATIONS.en).sort()))`, context), true);
});
test('station list switches languages even when options stay the same', () => {
  const stations = card('intuibase-radio-stations');
  assert.equal(stations.header.textContent, 'Stations');
  for (const [language, title, help] of [
    ['pl-PL', 'Stacje', 'Kliknij'], ['de_DE', 'Sender', 'Zum Auswählen'],
    ['fr', 'Stations', 'Click to select'],
  ]) {
    stations.hass = hass(language);
    assert.equal(stations.header.textContent, title);
    assert.ok(stations.list.children[0].title.startsWith(help));
  }
  stations.hass = hass('de', null);
  assert.equal(stations.list.textContent, 'Entität nicht gefunden: test.radio');
  stations.hass = hass('de');
  assert.equal(stations.list.children.length, 2);
});
test('custom station titles are preserved', () => {
  const stations = card('intuibase-radio-stations', { title: 'My stations' });
  stations.hass = hass('de');
  assert.equal(stations.header.textContent, 'My stations');
});
test('status labels, button tooltips and accessible names are translated', () => {
  const status = card('intuibase-radio-status');
  status.hass = hass('de', null);
  assert.equal(status.statusLabel.textContent, 'Verbindungsstatus');
  assert.equal(status.value.textContent, 'Bereit');
  assert.equal(status.previousButton.attributes['aria-label'], 'Alternative: vorheriger Stream');
  status.hass = hass('pl', null);
  assert.equal(status.statusLabel.textContent, 'Status połączenia');
  assert.equal(status.nextButton.title, 'Awaryjnie: następny stream');
  status.hass = hass('fr', null);
  assert.equal(status.statusLabel.textContent, 'Connection status');
});
test('artwork playback states and empty states use the profile language', () => {
  const artwork = card('intuibase-radio-artwork');
  artwork.hass = hass('de', { attributes: { player_state: 'paused' } });
  assert.equal(artwork.label.textContent, 'Keine Wiedergabe');
  assert.equal(artwork.station.textContent, 'Pausiert');
  artwork.hass = hass('pl', { attributes: { player_state: 'playing', playing_station: 'BBC' } });
  assert.equal(artwork.label.textContent, 'BBC');
  assert.equal(artwork.station.textContent, 'Odtwarzanie');
});
test('volume title, help and slider accessible name switch languages', () => {
  const volume = card('intuibase-volume-knob');
  volume.hass = hass('de');
  assert.equal(volume.title.textContent, 'Lautstärke');
  assert.equal(volume.hint.textContent, 'Ziehen, scrollen oder Pfeiltasten verwenden');
  assert.equal(volume.knob.attributes['aria-label'], 'Lautstärke');
  volume.hass = hass('fr');
  assert.equal(volume.title.textContent, 'Volume');
});

test('now playing updates with an unchanged image and supports programme titles', () => {
  const artwork = card('intuibase-radio-artwork');
  const attributes = { playing_station: 'BBC', player_state: 'playing',
    station_image_url: 'https://images.test/bbc.png', media_title: 'Song',
    media_artist: 'Artist', media_album_name: 'Album' };
  artwork.hass = hass('pl', { attributes });
  assert.equal(artwork.nowPlayingHeading.textContent, 'Teraz na antenie');
  assert.equal(artwork.nowPlayingTitle.textContent, 'Song');
  assert.equal(artwork.nowPlayingDetail.textContent, 'Artist · Album');
  assert.equal(artwork.nowPlaying.style.display, 'block');
  artwork.hass = hass('de', { attributes: { ...attributes, media_title: '<b>Evening programme</b>',
    media_artist: null, media_album_name: null } });
  assert.equal(artwork.nowPlayingHeading.textContent, 'Jetzt auf Sendung');
  assert.equal(artwork.nowPlayingTitle.textContent, '<b>Evening programme</b>');
  assert.equal(artwork.nowPlayingDetail.textContent, '');
  artwork.hass = hass('en', { attributes: { ...attributes, media_title: null } });
  assert.equal(artwork.nowPlaying.style.display, 'none');
  assert.equal(artwork.nowPlayingTitle.textContent, '');
});
