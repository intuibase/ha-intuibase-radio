"""Runtime labels use the HA system language, falling back to English."""

GERMAN = {
    "Selected": "Ausgewählt",
    "Ready": "Bereit",
    "No media players": "Keine Medienplayer",
    "Searching for streams…": "Streams werden gesucht…",
    "Connecting to stream": "Verbindung zum Stream wird hergestellt",
    "Error: no media player": "Fehler: kein Medienplayer",
    "Playing stream": "Stream wird wiedergegeben",
    "Error: media player unavailable": "Fehler: Medienplayer nicht verfügbar",
    "Connecting": "Verbindung wird hergestellt",
    "Buffering stream": "Stream wird gepuffert",
    "No media_player available": "Kein Medienplayer verfügbar",
    "Playing": "Wiedergabe",
    "No media player with play_media support": "Kein Medienplayer mit play_media-Unterstützung verfügbar",
    "The selected media player is unavailable": "Der ausgewählte Medienplayer ist nicht verfügbar",
    "Searching for streams": "Streams werden gesucht",
    "Playback error": "Wiedergabefehler",
    "Radio Browser is unavailable": "Radio Browser ist nicht verfügbar",
    "No streams found for": "Keine Streams gefunden für",
    "The station did not return a stream URL": "Der Sender hat keine Stream-URL zurückgegeben",
    "Buffering": "Puffern",
    "Search error": "Suchfehler",
    "buffering": "beim Puffern",
    "connection": "beim Verbindungsaufbau",
    "Stream error": "Stream-Fehler",
    "Buffering…": "Stream wird gepuffert…",
    "Manually selected stream error": "Fehler beim manuell ausgewählten Stream",
    "streams worked": "Streams funktionierte",
    "Error": "Fehler",
    "Paused": "Pausiert",
    "Stopped": "Gestoppt",
    "after": "nach",
    "None of": "Keiner der",
    "Failed attempt": "Fehlgeschlagener Versuch",
    "Diagnostics": "Diagnose",
    "Connection status": "Verbindungsstatus",
    "Choose a station": "Sender auswählen",
    "Play on": "Wiedergeben auf",
    "Controls": "Steuerung",
    "Volume": "Lautstärke",
    "PLAY STATION": "SENDER STARTEN",
    "PAUSE": "PAUSE",
    "RESUME": "FORTSETZEN",
    "STOP": "STOPP",
    "Station": "Sender",
    "Attempt": "Versuch",
    "Attempt history": "Versuchsverlauf",
    "No events": "Keine Ereignisse",
    "Media player": "Medienplayer",
    "Timeout": "Zeitüberschreitung"
}


def translate(language: str | None, english: str, polish: str) -> str:
    """Resolve supported language variants such as pl-PL and de_DE."""
    language = (language or "en").lower().replace("_", "-").split("-", 1)[0]
    if language == "pl":
        return polish
    if language == "de":
        return GERMAN.get(english, english)
    return english
