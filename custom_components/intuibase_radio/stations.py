"""Convert the editable station catalogue to and from configuration text."""

from .const import CONF_STATION_ORDER, CONF_STATIONS, STATIONS


def ordered_stations(options) -> dict[str, str]:
    """Keep catalogue order independent of JSON object key sorting."""
    stations = dict(options.get(CONF_STATIONS, STATIONS))
    order = options.get(CONF_STATION_ORDER)
    if order is None:
        # Older entries persisted only a mapping. For an extended built-in
        # catalogue recover the default order without dropping custom entries.
        order = list(STATIONS) if STATIONS.keys() <= stations.keys() else []
    return {
        name: stations[name]
        for name in dict.fromkeys([*order, *stations])
        if name in stations
    }


def format_stations(stations: dict[str, str]) -> str:
    """Show one station per line, keeping distinct search phrases."""
    return "\n".join(
        name if name == query else f"{name} = {query}"
        for name, query in stations.items()
    )


def parse_stations(value: str) -> dict[str, str]:
    """Require a nonempty catalogue with unique names and search phrases."""
    stations: dict[str, str] = {}
    names: set[str] = set()
    for line in value.splitlines():
        if not line.strip():
            continue
        name, separator, query = line.partition("=")
        name = name.strip()
        query = query.strip() if separator else name
        if not name or not query or name.casefold() in names:
            raise ValueError("Each station needs a unique name and a search phrase")
        names.add(name.casefold())
        stations[name] = query
    if not stations:
        raise ValueError("At least one station is required")
    return stations
