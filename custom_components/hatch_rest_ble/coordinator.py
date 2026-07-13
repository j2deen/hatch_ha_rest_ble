"""Data update coordinator for the Hatch Rest (BLE) integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothServiceInfoBleak,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_POLL_INTERVAL, DOMAIN
from .hatch import HatchRestClient, HatchRestState

_LOGGER = logging.getLogger(__name__)

# Hardware-verified: the Rest does NOT push feedback notifications, so polling
# is the only way to see changes made outside HA (e.g. from the Hatch app).
# The connection stays open, so each poll is a single cheap GATT read.


class HatchRestCoordinator(DataUpdateCoordinator[HatchRestState]):
    """Coordinate connection and state for a single Hatch Rest."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: HatchRestClient,
        address: str,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ) -> None:
        """Set up the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {address}",
            update_interval=timedelta(seconds=poll_interval),
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
        # Fail fast when the device isn't advertising (unplugged / moved away)
        # instead of burning ~45s of doomed connection attempts per poll.
        if not bluetooth.async_address_present(
            self.hass, self.address, connectable=True
        ):
            raise UpdateFailed(f"{self.address} is not in Bluetooth range")
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

    @callback
    def async_device_seen(
        self, service_info: BluetoothServiceInfoBleak, _change: BluetoothChange
    ) -> None:
        """Handle an advertisement: recover promptly if we were offline."""
        self.client.set_ble_device(service_info.device)
        if not self.last_update_success or self.data is None:
            # Debounced by the coordinator; makes the device come back within
            # seconds of reappearing instead of waiting for the next poll.
            self.hass.async_create_task(self.async_request_refresh())

    @callback
    def async_device_unavailable(
        self, _service_info: BluetoothServiceInfoBleak
    ) -> None:
        """Handle all adapters losing the device: mark unavailable now."""
        self.async_set_update_error(
            UpdateFailed(f"{self.address} is no longer in Bluetooth range")
        )

    async def async_shutdown(self) -> None:
        """Disconnect and unregister on unload."""
        self._unregister()
        await self.client.stop()
        await super().async_shutdown()
