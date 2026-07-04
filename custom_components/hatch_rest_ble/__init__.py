"""The Hatch Rest (BLE) integration."""

from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

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

    ble_device = bluetooth.async_ble_device_from_address(
        hass, address, connectable=True
    )
    if ble_device is None:
        raise ConfigEntryNotReady(
            f"Could not find Hatch Rest with address {address}. "
            "Make sure it is powered and in range of a Bluetooth adapter or proxy."
        )

    client = HatchRestClient(ble_device)
    coordinator = HatchRestCoordinator(hass, client, address)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        # Don't leak a live connection (the Rest only accepts one) into the
        # retry; the next attempt builds a fresh client.
        await client.stop()
        raise

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: HatchRestConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
