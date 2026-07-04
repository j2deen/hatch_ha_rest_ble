"""Data update coordinator for the Hatch Rest (BLE) integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .hatch import HatchRestClient, HatchRestState

_LOGGER = logging.getLogger(__name__)

# The device pushes state via notifications; this is a slow safety-net poll.
UPDATE_INTERVAL = timedelta(seconds=60)


class HatchRestCoordinator(DataUpdateCoordinator[HatchRestState]):
    """Coordinate connection and state for a single Hatch Rest."""

    def __init__(
        self, hass: HomeAssistant, client: HatchRestClient, address: str
    ) -> None:
        """Set up the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {address}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.address = address
        self._unregister = client.register_callback(self._handle_pushed_state)

    @callback
    def _handle_pushed_state(self, state: HatchRestState) -> None:
        """Receive state pushed from notifications/commands and fan it out."""
        self.async_set_updated_data(state)

    async def _async_update_data(self) -> HatchRestState:
        """Refresh the BLEDevice from HA's bluetooth stack and poll state."""
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is not None:
            self.client.set_ble_device(ble_device)
        try:
            # notify=False: the coordinator fans out the returned state itself.
            return await self.client.update(notify=False)
        except Exception as err:  # noqa: BLE001 - surface any BLE error as UpdateFailed
            raise UpdateFailed(f"Error communicating with {self.address}: {err}") from err

    async def async_shutdown(self) -> None:
        """Disconnect and unregister on unload."""
        self._unregister()
        await self.client.stop()
        await super().async_shutdown()
