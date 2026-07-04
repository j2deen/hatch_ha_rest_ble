"""Base entity for the Hatch Rest (BLE) integration."""

from __future__ import annotations

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
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            identifiers={(DOMAIN, coordinator.address)},
            manufacturer="Hatch Baby",
            model="Rest (1st gen)",
            name=coordinator.client.name,
        )

    @property
    def data(self) -> HatchRestState:
        """Return the current device state snapshot."""
        return self.coordinator.data
