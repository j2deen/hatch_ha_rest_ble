"""Number platform: sound volume."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HatchRestConfigEntry
from .entity import HatchRestEntity

# The device stores volume as a 0-255 byte; we present it to the user as 0-100 %.
_DEVICE_MAX = 255


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HatchRestConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the volume control."""
    async_add_entities([HatchRestVolumeNumber(entry.runtime_data)])


class HatchRestVolumeNumber(HatchRestEntity, NumberEntity):
    """Sound volume as a percentage."""

    _attr_translation_key = "volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator) -> None:
        """Initialise unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_volume"

    @property
    def native_value(self) -> float:
        """Return the volume as a percentage."""
        return round(self.data.volume / _DEVICE_MAX * 100)

    async def async_set_native_value(self, value: float) -> None:
        """Set the volume from a percentage."""
        await self.client.set_volume(round(value / 100 * _DEVICE_MAX))
