"""Switch platform: master power for the Hatch Rest."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HatchRestConfigEntry
from .entity import HatchRestEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HatchRestConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the power switch."""
    async_add_entities([HatchRestPowerSwitch(entry.runtime_data)])


class HatchRestPowerSwitch(HatchRestEntity, SwitchEntity):
    """Master on/off for the device (stops both light and sound)."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_translation_key = "power"

    def __init__(self, coordinator) -> None:
        """Initialise unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_power"

    @property
    def is_on(self) -> bool:
        """Return whether the device is powered on."""
        return self.data.power

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Power the device on."""
        await self.client.set_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Power the device off."""
        await self.client.set_power(False)
