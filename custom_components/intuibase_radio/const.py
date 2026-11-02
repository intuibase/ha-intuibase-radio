"""Constants and the curated Polish station catalogue."""

from homeassistant.const import Platform

DOMAIN = "intuibase_radio"
PLATFORMS = [
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]
CONF_CREATE_DASHBOARD = "create_dashboard"
CONF_DASHBOARD_NAME = "dashboard_name"
CONF_TARGET_PLAYER = "target_player"
CONF_EXCLUDED_PLAYERS = "excluded_players"
CONF_STATIONS = "stations"
DEFAULT_DASHBOARD_NAME = "Radio"

# Stable entity IDs used by the integration-managed dashboard. Existing entries
# are migrated to these IDs during setup; unique IDs remain unchanged.
ENTITY_IDS = {
    ("button", "play_station"): "button.intuibase_radio_play_station",
    ("button", "resume"): "button.intuibase_radio_resume",
    ("button", "pause"): "button.intuibase_radio_pause",
    ("button", "stop"): "button.intuibase_radio_stop",
    ("button", "previous_stream"): "button.intuibase_radio_previous_stream",
    ("button", "next_stream"): "button.intuibase_radio_next_stream",
    ("media_player", "media_player"): "media_player.intuibase_radio_player",
    ("number", "volume"): "number.intuibase_radio_volume",
    ("select", "station"): "select.intuibase_radio_station",
    ("select", "player"): "select.intuibase_radio_play_on",
    ("sensor", "status"): "sensor.intuibase_radio_status",
}

RADIO_BROWSER_URLS = (
    "https://all.api.radio-browser.info/json/stations/search",
    "https://de1.api.radio-browser.info/json/stations/search",
)

# Display name -> Radio Browser search phrase.  URLs are intentionally not stored:
# broadcasters change them regularly and Radio Browser resolves playlists for us.
STATIONS = {
    "Polskie Radio Jedynka": "Jedynka",
    "Polskie Radio Dwójka": "Dwójka",
    "Polskie Radio Trójka": "Trójka",
    "Polskie Radio Czwórka": "Czwórka",
    "Radio Gdańsk": "Radio Gdańsk",
    "Radio Nowy Świat": "Radio Nowy Świat",
    "Polskie Radio 24": "Polskie Radio 24",
    "Radio 357": "Radio 357",
    "RMF FM": "RMF FM",
    "RMF Classic": "RMF Classic",
    "Radio ZET": "Radio ZET",
    "TOK FM": "TOK FM",
    "Antyradio": "Antyradio",
    "Eska": "Radio Eska",
    "Eska ROCK": "Eska Rock",
    "Złote Przeboje": "Radio Złote Przeboje",
    "VOX FM": "VOX FM",
    "Radio WAWA": "Radio WAWA",
    "Chillizet": "Chillizet",
    "Meloradio": "Meloradio",
    "NTS Radio 1": "NTS Radio 1",
    "NTS Radio 2": "NTS Radio 2",
    "BBC Radio 3": "BBC Radio 3",
    "BBC Radio 6 Music": "BBC Radio 6 Music",
    "Refuge Worldwide": "Refuge Worldwide",
    "Cashmere Radio": "Cashmere Radio",
    "SomaFM Groove Salad": "SomaFM Groove Salad",
    "SomaFM Beat Blender": "SomaFM Beat Blender",
    "SomaFM Black Rock": "SomaFM Black Rock",
    "KCRW Live": "KCRW Live",

}
