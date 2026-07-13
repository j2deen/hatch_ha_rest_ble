"""The Hatch Rest (BLE) integration."""

from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
from .coordinator import HatchRestCoordinator
from .hatch import HatchRestClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]

type HatchRestConfigEntry = ConfigEntry[HatchRestCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: HatchRestConfigEntry
) -> bool:
    """Set up Hatch Rest (BLE) from a config entry."""
    address = entry.unique_id
    assert address is not None

    # May be None when the device is unplugged / out of range; setup proceeds
    # anyway and the entities stay unavailable until it can be reached.
    ble_device = bluetooth.async_ble_device_from_address(
        hass, address, connectable=True
    )

    client = HatchRestClient(address, ble_device)
    coordinator = HatchRestCoordinator(
        hass,
        client,
        address,
        poll_interval=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
    )

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    # React to the device (re)appearing: refresh within seconds instead of
    # waiting for the next scheduled poll.
    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            coordinator.async_device_seen,
            BluetoothCallbackMatcher(address=address, connectable=True),
            BluetoothScanningMode.PASSIVE,
        )
    )
    # React to the device disappearing: mark entities unavailable promptly.
    entry.async_on_unload(
        bluetooth.async_track_unavailable(
            hass, coordinator.async_device_unavailable, address, connectable=True
        )
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # First refresh runs in the background so HA startup is never blocked on a
    # slow/absent BLE device; entities become available when it succeeds.
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), f"{entry.title} first refresh"
    )
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: HatchRestConfigEntry
) -> None:
    """Reload the entry so a changed poll interval takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: HatchRestConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
