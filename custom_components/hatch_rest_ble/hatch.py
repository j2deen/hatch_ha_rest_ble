"""BLE client and wire protocol for the 1st-gen Hatch Rest.

The Rest exposes two custom GATT characteristics:

* ``CHAR_TX``       - write ASCII commands here.
* ``CHAR_FEEDBACK`` - read / subscribe for the device's current state.

Commands are short ASCII strings written as UTF-8 bytes:

    SI{:02x}                       power (01 = on, 00 = off)
    SC{r:02x}{g:02x}{b:02x}{i:02x} colour (rgb) + brightness, each 0-255
    SN{:02x}                       sound / track id
    SV{:02x}                       volume, 0-255

The feedback packet is a fixed layout delimited by ASCII section markers
``C`` (0x43), ``S`` (0x53) and ``P`` (0x50)::

    idx:  5   6   7   8   9   10  11   12   13  14
          'C' R   G   B   bri 'S' snd  vol  'P' flags

Power is encoded inverted in the flags byte: the lamp is ON when
``flags & 0xC0 == 0``.

This module is HA-agnostic apart from importing ``bleak`` / ``bleak_retry_connector``,
both of which Home Assistant bundles with the ``bluetooth`` integration.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BleakNotFoundError,
    establish_connection,
)

from .const import CHAR_FEEDBACK, CHAR_TX, COLOR_RAINBOW, SOUNDS

_LOGGER = logging.getLogger(__name__)

# Number of feedback bytes we require before trusting a packet.
_MIN_PACKET_LEN = 15
_CONNECT_ATTEMPTS = 3
# Settle time after a write before the device reflects the new value in its
# feedback characteristic. The Rest is inconsistent below ~1s, so we wait 1s
# for the confirming read. (Notifications, when available, update sooner.)
_WRITE_SETTLE = 1.0


@dataclass(frozen=True)
class HatchRestState:
    """Immutable snapshot of the device state parsed from a feedback packet."""

    power: bool = False
    red: int = 0
    green: int = 0
    blue: int = 0
    brightness: int = 0
    sound_id: int = 0
    volume: int = 0

    @property
    def color(self) -> tuple[int, int, int]:
        """Return the RGB tuple."""
        return (self.red, self.green, self.blue)

    @property
    def is_rainbow(self) -> bool:
        """Return True when the lamp is in rainbow / gradient mode."""
        return self.color == COLOR_RAINBOW

    @property
    def sound_name(self) -> str:
        """Return the friendly sound name (or a generic label for unknown ids)."""
        return SOUNDS.get(self.sound_id, f"Unknown ({self.sound_id})")


StateCallback = Callable[[HatchRestState], None]


class HatchRestParseError(Exception):
    """Raised when the feedback characteristic returns an unparseable packet."""


class HatchRestClient:
    """Maintains a connection to a Hatch Rest and translates commands/state."""

    def __init__(self, ble_device: BLEDevice) -> None:
        """Initialise with the BLEDevice resolved from Home Assistant."""
        self._ble_device = ble_device
        self._client: BleakClientWithServiceCache | None = None
        self._state = HatchRestState()
        self._callbacks: list[StateCallback] = []
        self._operation_lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()

    # -- properties ---------------------------------------------------------

    @property
    def address(self) -> str:
        """Return the device MAC address."""
        return self._ble_device.address

    @property
    def name(self) -> str:
        """Return a human readable name for the device."""
        return self._ble_device.name or self._ble_device.address

    @property
    def state(self) -> HatchRestState:
        """Return the last known state."""
        return self._state

    # -- wiring -------------------------------------------------------------

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Update the BLEDevice (the proxy/adapter path may change over time)."""
        self._ble_device = ble_device

    def register_callback(self, callback: StateCallback) -> Callable[[], None]:
        """Register a listener invoked whenever fresh state is available."""
        self._callbacks.append(callback)

        def _unregister() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return _unregister

    def _notify_listeners(self) -> None:
        for callback in list(self._callbacks):
            callback(self._state)

    # -- connection ---------------------------------------------------------

    async def _ensure_connected(self) -> BleakClientWithServiceCache:
        """Connect (once) and subscribe to feedback notifications."""
        if self._client is not None and self._client.is_connected:
            return self._client

        async with self._connect_lock:
            if self._client is not None and self._client.is_connected:
                return self._client

            _LOGGER.debug("%s: connecting", self.name)
            client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self.name,
                self._on_disconnected,
                use_services_cache=True,
                max_attempts=_CONNECT_ATTEMPTS,
                ble_device_callback=lambda: self._ble_device,
            )
            self._client = client
            try:
                await client.start_notify(CHAR_FEEDBACK, self._on_notification)
            except (NotImplementedError, ValueError) as err:
                # Some proxy/adapter combinations cannot subscribe; we fall back
                # to polling via update().
                _LOGGER.debug("%s: notifications unavailable (%s)", self.name, err)
            return client

    def _on_disconnected(self, _client: BleakClientWithServiceCache) -> None:
        _LOGGER.debug("%s: disconnected", self.name)
        self._client = None

    def _on_notification(
        self, _char: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if self._parse(bytes(data)):
            self._notify_listeners()

    async def stop(self) -> None:
        """Disconnect and release the connection."""
        async with self._connect_lock:
            if self._client is not None and self._client.is_connected:
                try:
                    await self._client.disconnect()
                except Exception:  # noqa: BLE001 - best effort on teardown
                    _LOGGER.debug("%s: error during disconnect", self.name, exc_info=True)
            self._client = None

    # -- state parsing ------------------------------------------------------

    def _parse(self, data: bytes) -> bool:
        """Parse a feedback packet into ``self._state``. Returns True on success."""
        if len(data) < _MIN_PACKET_LEN:
            _LOGGER.debug("%s: short feedback packet: %s", self.name, data.hex())
            return False
        # Validate the section delimiters; a mismatch means a malformed/partial read.
        if not (data[5] == 0x43 and data[10] == 0x53 and data[13] == 0x50):
            _LOGGER.debug("%s: unexpected feedback layout: %s", self.name, data.hex())
            return False

        self._state = HatchRestState(
            power=not bool(data[14] & 0xC0),
            red=data[6],
            green=data[7],
            blue=data[8],
            brightness=data[9],
            sound_id=data[11],
            volume=data[12],
        )
        return True

    async def update(self, notify: bool = True) -> HatchRestState:
        """Read the feedback characteristic and refresh state.

        ``notify=False`` skips the listener fan-out for callers that consume
        the returned state directly (the coordinator's poll), so listeners
        aren't invoked twice for one refresh.
        """
        client = await self._ensure_connected()
        async with self._operation_lock:
            data = await client.read_gatt_char(CHAR_FEEDBACK)
        if not self._parse(bytes(data)):
            raise HatchRestParseError(
                f"unparseable feedback packet: {bytes(data).hex()}"
            )
        if notify:
            self._notify_listeners()
        return self._state

    # -- commands -----------------------------------------------------------

    async def _send(self, command: str) -> None:
        """Write a command, let the device settle, then refresh state."""
        client = await self._ensure_connected()
        _LOGGER.debug("%s: sending %s", self.name, command)
        async with self._operation_lock:
            await client.write_gatt_char(CHAR_TX, command.encode("ascii"), response=True)
        await asyncio.sleep(_WRITE_SETTLE)
        await self.update()

    async def set_power(self, on: bool) -> None:
        """Turn the whole device on or off."""
        await self._send("SI{:02x}".format(1 if on else 0))

    async def set_color(self, red: int, green: int, blue: int) -> None:
        """Set the lamp colour, keeping the current brightness."""
        await self.set_color_brightness(red, green, blue, self._state.brightness)

    async def set_brightness(self, brightness: int) -> None:
        """Set the lamp brightness (0-255), keeping the current colour."""
        red, green, blue = self._state.color
        await self.set_color_brightness(red, green, blue, brightness)

    async def set_color_brightness(
        self, red: int, green: int, blue: int, brightness: int
    ) -> None:
        """Set colour and brightness together in a single command."""
        await self._send(
            "SC{:02x}{:02x}{:02x}{:02x}".format(
                _clamp(red), _clamp(green), _clamp(blue), _clamp(brightness)
            )
        )

    async def set_rainbow(self, brightness: int | None = None) -> None:
        """Enable rainbow / gradient mode at the given (or current) brightness."""
        level = self._state.brightness if brightness is None else brightness
        await self.set_color_brightness(*COLOR_RAINBOW, level or 255)

    async def set_sound(self, sound_id: int) -> None:
        """Select the active sound / track."""
        await self._send("SN{:02x}".format(_clamp(sound_id)))

    async def set_volume(self, volume: int) -> None:
        """Set the volume (0-255)."""
        await self._send("SV{:02x}".format(_clamp(volume)))


def _clamp(value: int) -> int:
    """Clamp an integer into the 0-255 byte range."""
    return max(0, min(255, int(value)))


__all__ = [
    "HatchRestClient",
    "HatchRestParseError",
    "HatchRestState",
    "BleakNotFoundError",
]
