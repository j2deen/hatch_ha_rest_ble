"""Select platform: choose the active sound / track."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HatchRestConfigEntry
from .const import SOUND_NAME_TO_ID, SOUNDS
from .entity import HatchRestEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HatchRestConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sound selector."""
    async_add_entities([HatchRestSoundSelect(entry.runtime_data)])


class HatchRestSoundSelect(HatchRestEntity, SelectEntity):
    """Pick the active sound / white-noise track."""

    _attr_translation_key = "sound"
    _attr_icon = "mdi:music-note"
    _attr_options = list(SOUNDS.values())

    def __init__(self, coordinator) -> None:
        """Initialise unique id."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_sound"

    @property
    def current_option(self) -> str | None:
        """Return the currently selected sound name."""
        return SOUNDS.get(self.data.sound_id)

    async def async_select_option(self, option: str) -> None:
        """Change the active sound."""
        sound_id = SOUND_NAME_TO_ID[option]
        await self.client.set_sound(sound_id)
