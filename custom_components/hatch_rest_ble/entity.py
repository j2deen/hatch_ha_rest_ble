"""Base entity for the Hatch Rest (BLE) integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HatchRestCoordinator
from .hatch import HatchRestState


class HatchRestEntity(CoordinatorEntity[HatchRestCoordinator]):
    """Common base for all Hatch Rest entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HatchRestCoordinator) -> None:
        """Initialise shared device info and the client handle."""
        super().__init__(coordinator)
        self.client = coordinator.client
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            identifiers={(DOMAIN, coordinator.address)},
            manufacturer="Hatch Baby",
            model="Rest (1st gen)",
            name=(entry.title if entry else None) or coordinator.client.name,
        )

    @property
    def available(self) -> bool:
        """Unavailable until the device has been read at least once."""
        return super().available and self.coordinator.data is not None

    @property
    def data(self) -> HatchRestState:
        """Return the current device state snapshot."""
        data = self.coordinator.data
        if data is None:
            # Only reachable from service calls issued while the device has
            # never been read (state properties are skipped when unavailable).
            raise HomeAssistantError(
                "The Hatch Rest has not been reachable yet; "
                "make sure it is plugged in and in range"
            )
        return data
