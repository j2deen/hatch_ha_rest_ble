"""Light platform: the Hatch Rest night light (RGB + brightness + rainbow)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HatchRestConfigEntry
from .const import EFFECT_RAINBOW
from .entity import HatchRestEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HatchRestConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the night light."""
    async_add_entities([HatchRestLight(entry.runtime_data)])


class HatchRestLight(HatchRestEntity, LightEntity):
    """The RGB night light. Turning it off dims to zero but leaves sound playing."""

    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = [EFFECT_RAINBOW]
    _attr_name = None  # use the device name for the primary entity

    def __init__(self, coordinator) -> None:
        """Initialise unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_light"

    @property
    def is_on(self) -> bool:
        """The light is on when the device is powered and brightness is non-zero."""
        return self.data.power and self.data.brightness > 0

    @property
    def brightness(self) -> int:
        """Return brightness (0-255), matching the device's native range."""
        return self.data.brightness

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        """Return the current RGB colour."""
        return self.data.color

    @property
    def effect(self) -> str | None:
        """Return the active effect, if any."""
        return EFFECT_RAINBOW if self.data.is_rainbow else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on, applying colour/brightness/effect as requested."""
        # Ensure the device is powered; otherwise the lamp ignores colour commands.
        if not self.data.power:
            await self.client.set_power(True)

        if kwargs.get(ATTR_EFFECT) == EFFECT_RAINBOW:
            await self.client.set_rainbow(kwargs.get(ATTR_BRIGHTNESS))
            return

        rgb = kwargs.get(ATTR_RGB_COLOR, self.data.color)
        if rgb == (0, 0, 0):
            # A stored black colour would leave the lamp dark while reporting on.
            rgb = (255, 255, 255)
        brightness = kwargs.get(ATTR_BRIGHTNESS, self.data.brightness or 255)
        await self.client.set_color_brightness(rgb[0], rgb[1], rgb[2], brightness)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off by dimming to zero (sound keeps playing)."""
        await self.client.set_brightness(0)
