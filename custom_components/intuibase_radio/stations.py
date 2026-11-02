"""Convert the editable station catalogue to and from configuration text."""


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
