"""Radio volume control."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import RadioEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([RadioVolume(hass.data[DOMAIN][entry.entry_id])])


class RadioVolume(RadioEntity, NumberEntity):
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, controller) -> None:
        super().__init__(controller, "volume")

    @property
    def native_value(self) -> float:
        return round(self.controller.volume * 100)

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.set_volume(value / 100)
