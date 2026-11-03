"""Base entity for the radio controller."""

from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN


class RadioEntity(Entity):
    """An entity belonging to the single radio controller device."""

    _attr_has_entity_name = True

    def __init__(self, controller, key: str) -> None:
        self.controller = controller
        self._attr_unique_id = f"intuibase_radio_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, DOMAIN)},
            name="IntuiBase Radio",
            manufacturer="Radio Browser",
            model="Internet Radio Controller",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.controller.add_listener(self.async_write_ha_state))
