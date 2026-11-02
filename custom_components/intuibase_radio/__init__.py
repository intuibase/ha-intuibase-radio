"""Polish Internet Radio controller for Home Assistant media players."""

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_CREATE_DASHBOARD,
    CONF_DASHBOARD_NAME,
    DEFAULT_DASHBOARD_NAME,
    DOMAIN,
    ENTITY_IDS,
    PLATFORMS,
)
from .controller import RadioController
from .dashboard import RadioDashboard

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create the controller, its entities and its dashboard."""
    if entry.title != "IntuiBase Radio":
        hass.config_entries.async_update_entry(entry, title="IntuiBase Radio")
    controller = RadioController(hass, entry)
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data[entry.entry_id] = controller
    if not domain_data.get("_frontend_registered"):
        resource_url = "/intuibase_radio/internet-radio-card.js?v=0.9.0"
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    "/intuibase_radio/internet-radio-card.js",
                    str(Path(__file__).parent / "www" / "internet-radio-card.js"),
                    cache_headers=False,
                )
            ]
        )
        resources = hass.data[LOVELACE_DATA].resources
        await resources.async_get_info()
        existing_resource = next(
            (
                item
                for item in resources.async_items()
                if item.get("url", "").startswith(
                    (
                        "/intuibase_radio/internet-radio-card.js",
                        "/internet_radio/internet-radio-card.js",
                    )
                )
            ),
            None,
        )
        if existing_resource is None:
            await resources.async_create_item(
                {"res_type": "module", "url": resource_url}
            )
        elif existing_resource.get("url") != resource_url:
            await resources.async_update_item(
                existing_resource["id"],
                {"res_type": "module", "url": resource_url},
            )
        domain_data["_frontend_registered"] = True
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, DOMAIN)},
        name="IntuiBase Radio",
        manufacturer="Radio Browser",
        model="Internet Radio Controller",
    )
    if device.name != "IntuiBase Radio":
        device_registry.async_update_device(device.id, name="IntuiBase Radio")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entity_registry = er.async_get(hass)
    for (platform, key), target_entity_id in ENTITY_IDS.items():
        current_entity_id = entity_registry.async_get_entity_id(
            platform, DOMAIN, f"intuibase_radio_{key}"
        )
        if (
            current_entity_id
            and current_entity_id != target_entity_id
            and entity_registry.async_get(target_entity_id) is None
        ):
            entity_registry.async_update_entity(
                current_entity_id, new_entity_id=target_entity_id
            )
    if entry.options.get(CONF_CREATE_DASHBOARD, True):
        media_player_entity_id = ENTITY_IDS[("media_player", "media_player")]
        dashboard = RadioDashboard(
            hass,
            entry.options.get(CONF_DASHBOARD_NAME, DEFAULT_DASHBOARD_NAME),
            entry.entry_id,
            media_player_entity_id,
        )
        await dashboard.async_start()
        controller.dashboard = dashboard

    @callback
    def state_changed(event) -> None:
        entity_id = event.data.get("entity_id", "")
        if entity_id.startswith("media_player."):
            controller.refresh_players()

    controller.unsubscribe = hass.bus.async_listen(EVENT_STATE_CHANGED, state_changed)
    controller.refresh_players()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload all radio entities and remove its sidebar panel."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        controller = hass.data[DOMAIN].pop(entry.entry_id)
        if controller.unsubscribe:
            controller.unsubscribe()
        if controller.dashboard:
            await controller.dashboard.async_stop()
    return unloaded
