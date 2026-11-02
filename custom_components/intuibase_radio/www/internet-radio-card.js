const RADIO_TRANSLATIONS = {
  "en": {
    "stations": "Stations",
    "hint": "Click: select • Double-click: play",
    "station_help": "Click to select. Double-click to play.",
    "missing": "Entity not found:",
    "connection": "Connection status",
    "previous": "Fallback: previous stream",
    "next": "Fallback: next stream",
    "ready": "Ready",
    "not_playing": "Not playing",
    "volume": "Volume",
    "volume_hint": "Drag, scroll or use the arrow keys",
    "station_required": "A station select entity is required",
    "status_required": "A radio status entity is required",
    "volume_required": "A volume number entity is required",
    "playing": "Playing",
    "buffering": "Buffering",
    "paused": "Paused",
    "idle": "Idle",
    "off": "Off",
    "unknown": "Unknown",
    "unavailable": "Unavailable"
  },
  "pl": {
    "stations": "Stacje",
    "hint": "Kliknij: wybierz • Dwuklik: graj",
    "station_help": "Kliknij, aby wybrać. Kliknij dwa razy, aby odtworzyć.",
    "missing": "Brak encji:",
    "connection": "Status połączenia",
    "previous": "Awaryjnie: poprzedni stream",
    "next": "Awaryjnie: następny stream",
    "ready": "Gotowe",
    "not_playing": "Nie odtwarzam",
    "volume": "Głośność",
    "volume_hint": "Przeciągnij, przewiń lub użyj strzałek",
    "station_required": "Wymagana jest encja select stacji",
    "status_required": "Wymagana jest encja statusu radia",
    "volume_required": "Wymagana jest encja number głośności",
    "playing": "Odtwarzanie",
    "buffering": "Buforowanie",
    "paused": "Pauza",
    "idle": "Bezczynny",
    "off": "Wyłączony",
    "unknown": "Nieznany",
    "unavailable": "Niedostępny"
  },
  "de": {
    "stations": "Sender",
    "hint": "Klicken: auswählen • Doppelklicken: wiedergeben",
    "station_help": "Zum Auswählen klicken. Zur Wiedergabe doppelklicken.",
    "missing": "Entität nicht gefunden:",
    "connection": "Verbindungsstatus",
    "previous": "Alternative: vorheriger Stream",
    "next": "Alternative: nächster Stream",
    "ready": "Bereit",
    "not_playing": "Keine Wiedergabe",
    "volume": "Lautstärke",
    "volume_hint": "Ziehen, scrollen oder Pfeiltasten verwenden",
    "station_required": "Eine Senderauswahl-Entität ist erforderlich",
    "status_required": "Eine Radio-Statusentität ist erforderlich",
    "volume_required": "Eine Lautstärke-Entität vom Typ number ist erforderlich",
    "playing": "Wiedergabe",
    "buffering": "Puffern",
    "paused": "Pausiert",
    "idle": "Inaktiv",
    "off": "Aus",
    "unknown": "Unbekannt",
    "unavailable": "Nicht verfügbar"
  }
};

function radioLanguage(hass) {
  const language = (hass?.language || "en").toLowerCase().replace(/_/g, "-").split("-")[0];
  return RADIO_TRANSLATIONS[language] ? language : "en";
}

function radioText(hass, key) {
  return RADIO_TRANSLATIONS[radioLanguage(hass)][key] ?? RADIO_TRANSLATIONS.en[key] ?? key;
}

class IntuiBaseRadioStations extends HTMLElement {
  setConfig(config) {
    if (!config.entity) {
      throw new Error(radioText(this._hass, "station_required"));
    }
    this.config = config;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      const style = document.createElement("style");
      style.textContent = `
        ha-card { overflow: hidden; }
        .header { padding: 16px 16px 10px; font-size: 20px; font-weight: 500; }
        .stations {
          max-height: var(--radio-list-height, 360px);
          overflow-y: auto;
          padding: 0 10px 12px;
          scrollbar-width: thin;
        }
        .list-hint { color: var(--secondary-text-color); font-size: 12px; padding: 0 16px 12px; }
        button {
          align-items: center;
          background: transparent;
          border: 0;
          border-radius: 12px;
          color: var(--primary-text-color);
          cursor: pointer;
          display: flex;
          font: inherit;
          gap: 12px;
          min-height: 46px;
          padding: 8px 12px;
          text-align: left;
          width: 100%;
        }
        button:hover { background: var(--secondary-background-color); }
        button.selected {
          background: color-mix(in srgb, var(--primary-color) 18%, transparent);
          color: var(--primary-color);
          font-weight: 600;
        }
        ha-icon { flex: 0 0 auto; }
      `;
      this.shadowRoot.append(style);
      this.card = document.createElement("ha-card");
      this.header = document.createElement("div");
      this.header.className = "header";
      this.list = document.createElement("div");
      this.list.className = "stations";
      this.hint = document.createElement("div");
      this.hint.className = "list-hint";
      this.hint.textContent = radioText(this._hass, "hint");
      this.card.append(this.header, this.list, this.hint);
      this.shadowRoot.append(this.card);
    }
    this.header.textContent = config.title || radioText(this._hass, "stations");
    this.style.setProperty("--radio-list-height", config.max_height || "360px");
  }

  set hass(hass) {
    this._hass = hass;
    this.header.textContent = this.config.title || radioText(hass, "stations");
    this.hint.textContent = radioText(hass, "hint");
    const state = hass.states[this.config.entity];
    if (!state) {
      this._signature = null;
      this.list.textContent = `${radioText(hass, "missing")} ${this.config.entity}`;
      return;
    }
    const options = state.attributes.options || [];
    const signature = `${radioLanguage(hass)}|${state.state}|${options.join("\u0000")}`;
    if (signature === this._signature) return;
    this._signature = signature;
    this.list.replaceChildren();
    for (const option of options) {
      const button = document.createElement("button");
      button.title = radioText(hass, "station_help");
      if (option === state.state) button.classList.add("selected");
      const icon = document.createElement("ha-icon");
      icon.setAttribute("icon", option === state.state ? "mdi:radio" : "mdi:radio-tower");
      const label = document.createElement("span");
      label.textContent = option;
      button.append(icon, label);
      button.addEventListener("click", () =>
        this._hass.callService("select", "select_option", {
          entity_id: this.config.entity,
          option,
        })
      );
      button.addEventListener("dblclick", async () => {
        await this._hass.callService("select", "select_option", {
          entity_id: this.config.entity,
          option,
        });
        if (this.config.play_button) {
          await this._hass.callService("button", "press", {
            entity_id: this.config.play_button,
          });
        }
      });
      this.list.append(button);
    }
    this.list.querySelector(".selected")?.scrollIntoView({ block: "nearest" });
  }

  getCardSize() {
    return 6;
  }
}

customElements.define("intuibase-radio-stations", IntuiBaseRadioStations);

class IntuiBaseRadioStatus extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error(radioText(this._hass, "status_required"));
    this.config = config;
    if (this.shadowRoot) return;
    this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = `
      ha-card {
        align-items: center;
        display: flex;
        gap: 10px;
        min-height: 58px;
        padding: 7px 10px 7px 14px;
      }
      .status { flex: 1 1 auto; min-width: 0; }
      .label {
        color: var(--secondary-text-color);
        font-size: 11px;
        letter-spacing: .04em;
        text-transform: uppercase;
      }
      .value {
        font-size: 17px;
        font-weight: 500;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .emergency { align-items: center; display: flex; gap: 4px; }
      button {
        align-items: center;
        background: transparent;
        border: 0;
        border-radius: 50%;
        color: var(--secondary-text-color);
        cursor: pointer;
        display: flex;
        height: 36px;
        justify-content: center;
        padding: 0;
        width: 36px;
      }
      button:hover {
        background: var(--secondary-background-color);
        color: var(--primary-color);
      }
      button:active { transform: scale(.92); }
      ha-icon { --mdc-icon-size: 22px; }
    `;
    const card = document.createElement("ha-card");
    const status = document.createElement("div");
    status.className = "status";
    const label = document.createElement("div");
    label.className = "label";
    this.statusLabel = label;
    label.textContent = config.title || radioText(this._hass, "connection");
    this.value = document.createElement("div");
    this.value.className = "value";
    status.append(label, this.value);
    const emergency = document.createElement("div");
    emergency.className = "emergency";
    this.previousButton = this._button(
      "mdi:skip-previous", radioText(this._hass, "previous"), config.previous_button
    );
    this.nextButton = this._button(
      "mdi:skip-next", radioText(this._hass, "next"), config.next_button
    );
    emergency.append(this.previousButton, this.nextButton);
    card.append(status, emergency);
    this.shadowRoot.append(style, card);
  }

  _button(iconName, title, entityId) {
    const button = document.createElement("button");
    button.type = "button";
    button.title = title;
    button.setAttribute("aria-label", title);
    const icon = document.createElement("ha-icon");
    icon.setAttribute("icon", iconName);
    button.append(icon);
    button.addEventListener("click", () => {
      if (entityId) this._hass?.callService("button", "press", { entity_id: entityId });
    });
    return button;
  }

  set hass(hass) {
    this._hass = hass;
    this.statusLabel.textContent = this.config.title || radioText(hass, "connection");
    const previousTitle = radioText(hass, "previous");
    const nextTitle = radioText(hass, "next");
    this.previousButton.title = previousTitle;
    this.previousButton.setAttribute("aria-label", previousTitle);
    this.nextButton.title = nextTitle;
    this.nextButton.setAttribute("aria-label", nextTitle);
    const state = hass.states[this.config.entity];
    this.value.textContent = state?.attributes?.short_status || state?.state || radioText(hass, "ready");
    this.value.title = this.value.textContent;
  }

  getCardSize() { return 1; }
}

customElements.define("intuibase-radio-status", IntuiBaseRadioStatus);

class IntuiBaseRadioArtwork extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error(radioText(this._hass, "status_required"));
    this.config = config;
    if (this.shadowRoot) return;
    this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = `
      ha-card { overflow: hidden; }
      .artwork {
        align-items: center;
        background: var(--secondary-background-color);
        display: flex;
        justify-content: center;
        min-height: 250px;
        padding: 16px;
        position: relative;
      }
      img {
        height: 250px;
        max-width: 100%;
        object-fit: contain;
        width: 100%;
      }
      .fallback {
        color: var(--secondary-text-color);
        display: none;
      }
      .fallback ha-icon { --mdc-icon-size: 112px; }
      .caption {
        align-items: flex-end;
        background: linear-gradient(transparent, rgba(0, 0, 0, .78));
        bottom: 0;
        box-sizing: border-box;
        color: white;
        display: flex;
        gap: 16px;
        justify-content: space-between;
        left: 0;
        padding: 34px 16px 14px;
        position: absolute;
        right: 0;
      }
      .label {
        font-size: 16px;
        font-weight: 500;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .station {
        color: rgba(255, 255, 255, .82);
        font-size: 14px;
        flex: 0 0 auto;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    `;
    const card = document.createElement("ha-card");
    const artwork = document.createElement("div");
    artwork.className = "artwork";
    this.image = document.createElement("img");
    this.image.alt = "";
    this.fallback = document.createElement("div");
    this.fallback.className = "fallback";
    const fallbackIcon = document.createElement("ha-icon");
    fallbackIcon.setAttribute("icon", "mdi:radio");
    this.fallback.append(fallbackIcon);
    const caption = document.createElement("div");
    caption.className = "caption";
    this.label = document.createElement("div");
    this.label.className = "label";
    this.label.textContent = "";
    this.station = document.createElement("div");
    this.station.className = "station";
    caption.append(this.label, this.station);
    artwork.append(this.image, this.fallback, caption);
    card.append(artwork);
    this.shadowRoot.append(style, card);
    this.image.addEventListener("error", () => this._showFallback());
  }

  set hass(hass) {
    const state = hass.states[this.config.entity];
    this._hass = hass;
    const station = state?.attributes?.playing_station || radioText(hass, "not_playing");
    const playerState = state?.attributes?.player_state || "idle";
    const imageUrl = state?.attributes?.station_image_url || "";
    this.label.textContent = station;
    this.label.title = station;
    this.station.textContent = radioText(hass, playerState);
    if (imageUrl === this._imageUrl) return;
    this._imageUrl = imageUrl;
    if (!imageUrl) {
      this._showFallback();
      return;
    }
    this.image.style.display = "block";
    this.fallback.style.display = "none";
    this.image.src = imageUrl;
  }

  _showFallback() {
    this.image.style.display = "none";
    this.fallback.style.display = "block";
  }

  getCardSize() { return 5; }
}

customElements.define("intuibase-radio-artwork", IntuiBaseRadioArtwork);

class IntuiBaseVolumeKnob extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error(radioText(this._hass, "volume_required"));
    this.config = config;
    if (this.shadowRoot) return;
    this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = `
      ha-card { padding: 16px; text-align: center; }
      .title { font-size: 18px; font-weight: 500; margin-bottom: 12px; }
      .knob {
        --angle: -40.5deg;
        background: radial-gradient(circle at 42% 35%, var(--card-background-color), var(--secondary-background-color));
        border: 3px solid color-mix(in srgb, var(--primary-color) 55%, var(--divider-color));
        border-radius: 50%;
        box-shadow: 0 7px 18px rgba(0,0,0,.22), inset 0 0 0 7px var(--card-background-color);
        cursor: grab;
        height: 150px;
        margin: 0 auto;
        outline: none;
        position: relative;
        touch-action: none;
        width: 150px;
      }
      .knob:active { cursor: grabbing; }
      .knob:focus-visible { box-shadow: 0 0 0 3px var(--primary-color), 0 7px 18px rgba(0,0,0,.22); }
      .needle {
        background: var(--primary-color);
        border-radius: 3px;
        height: 55px;
        left: calc(50% - 2px);
        position: absolute;
        top: 18px;
        transform: rotate(var(--angle));
        transform-origin: 2px 57px;
        width: 4px;
      }
      .center {
        background: var(--primary-color);
        border-radius: 50%;
        height: 14px;
        left: calc(50% - 7px);
        position: absolute;
        top: calc(50% - 7px);
        width: 14px;
      }
      .value { color: var(--primary-color); font-size: 26px; font-weight: 600; margin-top: 10px; }
      .hint { color: var(--secondary-text-color); font-size: 12px; }
    `;
    this.card = document.createElement("ha-card");
    const title = document.createElement("div");
    title.className = "title";
    this.title = title;
    title.textContent = config.title || radioText(this._hass, "volume");
    this.knob = document.createElement("div");
    this.knob.className = "knob";
    this.knob.tabIndex = 0;
    this.knob.setAttribute("role", "slider");
    this.knob.setAttribute("aria-valuemin", "0");
    this.knob.setAttribute("aria-valuemax", "100");
    this.needle = document.createElement("div");
    this.needle.className = "needle";
    const center = document.createElement("div");
    center.className = "center";
    this.knob.append(this.needle, center);
    this.valueLabel = document.createElement("div");
    this.valueLabel.className = "value";
    const hint = document.createElement("div");
    hint.className = "hint";
    this.hint = hint;
    hint.textContent = radioText(this._hass, "volume_hint");
    this.card.append(title, this.knob, this.valueLabel, hint);
    this.shadowRoot.append(style, this.card);

    this.knob.addEventListener("pointerdown", (event) => {
      this._dragging = true;
      this.knob.setPointerCapture(event.pointerId);
      this._setFromPointer(event);
    });
    this.knob.addEventListener("pointermove", (event) => {
      if (this._dragging) this._setFromPointer(event);
    });
    this.knob.addEventListener("pointerup", (event) => {
      this._dragging = false;
      this._setFromPointer(event, true);
    });
    this.knob.addEventListener("wheel", (event) => {
      event.preventDefault();
      this._setValue(this._value + (event.deltaY < 0 ? 2 : -2), true);
    }, { passive: false });
    this.knob.addEventListener("keydown", (event) => {
      if (!["ArrowUp", "ArrowRight", "ArrowDown", "ArrowLeft"].includes(event.key)) return;
      event.preventDefault();
      this._setValue(this._value + (["ArrowUp", "ArrowRight"].includes(event.key) ? 1 : -1), true);
    });
  }

  set hass(hass) {
    this._hass = hass;
    this.title.textContent = this.config.title || radioText(hass, "volume");
    this.hint.textContent = radioText(hass, "volume_hint");
    this.knob.setAttribute("aria-label", radioText(hass, "volume"));
    if (this._dragging) return;
    const state = hass.states[this.config.entity];
    if (!state) return;
    this._render(Number(state.state));
  }

  _setFromPointer(event, immediate = false) {
    const rect = this.knob.getBoundingClientRect();
    const dx = event.clientX - (rect.left + rect.width / 2);
    const dy = event.clientY - (rect.top + rect.height / 2);
    let angle = Math.atan2(dx, -dy) * 180 / Math.PI;
    if (angle > 135) angle = 135;
    if (angle < -135) angle = -135;
    this._setValue((angle + 135) / 270 * 100, immediate);
  }

  _setValue(value, immediate = false) {
    value = Math.max(0, Math.min(100, Math.round(value)));
    this._render(value);
    clearTimeout(this._sendTimer);
    if (immediate) this._send(value);
    else this._sendTimer = setTimeout(() => this._send(value), 120);
  }

  _render(value) {
    if (!Number.isFinite(value)) value = 0;
    this._value = value;
    const angle = -135 + value * 2.7;
    this.knob.style.setProperty("--angle", `${angle}deg`);
    this.knob.setAttribute("aria-valuenow", String(Math.round(value)));
    this.valueLabel.textContent = `${Math.round(value)}%`;
  }

  _send(value) {
    this._hass?.callService("number", "set_value", {
      entity_id: this.config.entity,
      value,
    });
  }

  getCardSize() { return 5; }
}

customElements.define("intuibase-volume-knob", IntuiBaseVolumeKnob);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "intuibase-radio-stations",
  name: "IntuiBase Radio Stations",
  description: "Scrollable IntuiBase Radio station list",
});
window.customCards.push({
  type: "intuibase-radio-status",
  name: "IntuiBase Radio Status",
  description: "Compact connection status with stream fallback controls",
});
window.customCards.push({
  type: "intuibase-radio-artwork",
  name: "IntuiBase Radio Artwork",
  description: "Station artwork with the current station name",
});
window.customCards.push({
  type: "intuibase-volume-knob",
  name: "IntuiBase Volume Knob",
  description: "Interactive volume knob",
});
