#!/usr/bin/env python3
"""Standalone Bleak test tool for the 1st-gen Hatch Baby Rest.

This talks to the Rest DIRECTLY from whatever computer you run it on, using that
machine's own Bluetooth radio. It does NOT go through Home Assistant or your
ESPHome proxies -- it's a way to prove the device + protocol work before you trust
the Home Assistant integration. The device must be in Bluetooth range of THIS
computer while the script runs.

Quick start:
    python3 -m pip install bleak
    python3 scripts/hatch_ble_test.py scan
    python3 scripts/hatch_ble_test.py status
    python3 scripts/hatch_ble_test.py on
    python3 scripts/hatch_ble_test.py color 255 0 0       # red
    python3 scripts/hatch_ble_test.py brightness 128
    python3 scripts/hatch_ble_test.py sound 5             # 5 = Ocean
    python3 scripts/hatch_ble_test.py volume 100          # 0-255
    python3 scripts/hatch_ble_test.py watch               # live state stream
    python3 scripts/hatch_ble_test.py off

Most commands auto-discover the first Hatch Rest they see. If you have more than
one (or discovery is flaky), pass --address:
    python3 scripts/hatch_ble_test.py status --address AA:BB:CC:DD:EE:FF

Note: on macOS, Bluetooth "addresses" are CoreBluetooth UUIDs, not MAC addresses;
just copy whatever `scan` prints.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

# --- protocol constants (same as the HA integration) ------------------------

CHAR_TX = "02240002-5efd-47eb-9c1a-de53f7a2b232"  # write ASCII commands here
CHAR_FEEDBACK = "02260002-5efd-47eb-9c1a-de53f7a2b232"  # read/notify state here
MANUFACTURER_ID = 1076  # 0x0434, advertised by the Hatch Rest

SOUNDS = {
    0: "Off",
    2: "Water Stream",
    3: "White Noise",
    4: "Dryer",
    5: "Ocean",
    6: "Wind",
    7: "Rain",
    9: "Bird",
    10: "Crickets",
    11: "Brahms",
    13: "Twinkle",
    14: "Rock-a-bye",
}


# --- helpers ----------------------------------------------------------------


def parse_feedback(data: bytes) -> dict | None:
    """Decode a feedback packet into a readable dict, or None if malformed.

    Layout (delimited by ASCII 'C'=0x43, 'S'=0x53, 'P'=0x50):
        idx:  5    6   7   8   9    10   11    12   13   14
              'C'  R   G   B   bri  'S'  snd   vol  'P'  flags
    Power is inverted: the lamp is ON when (flags & 0xC0) == 0.
    """
    if len(data) < 15:
        return None
    if not (data[5] == 0x43 and data[10] == 0x53 and data[13] == 0x50):
        return None
    sound_id = data[11]
    return {
        "power": not bool(data[14] & 0xC0),
        "rgb": (data[6], data[7], data[8]),
        "brightness": data[9],
        "sound_id": sound_id,
        "sound": SOUNDS.get(sound_id, f"Unknown ({sound_id})"),
        "volume": data[12],
        "raw": data.hex(),
    }


def print_state(state: dict | None) -> None:
    """Pretty-print a decoded state dict."""
    if state is None:
        print("  <could not parse feedback packet>")
        return
    r, g, b = state["rgb"]
    print(f"  power:      {'ON' if state['power'] else 'off'}")
    print(f"  color:      rgb({r}, {g}, {b})" + ("  [rainbow mode]" if state["rgb"] == (254, 254, 254) else ""))
    print(f"  brightness: {state['brightness']}/255")
    print(f"  sound:      {state['sound']} (id {state['sound_id']})")
    print(f"  volume:     {state['volume']}/255")
    print(f"  raw:        {state['raw']}")


async def discover(timeout: float) -> list[tuple[BLEDevice, object]]:
    """Return (device, advertisement) pairs that look like a Hatch Rest."""
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    hits = []
    for device, adv in found.values():
        if MANUFACTURER_ID in adv.manufacturer_data:
            hits.append((device, adv))
    return hits


async def resolve_target(address: str | None, timeout: float) -> str | BLEDevice:
    """Figure out what to connect to: an explicit address, or auto-discover."""
    if address:
        return address
    print(f"Scanning {timeout:.0f}s for a Hatch Rest...", file=sys.stderr)
    hits = await discover(timeout)
    if not hits:
        sys.exit("No Hatch Rest found. Is it powered on and in range of this computer?")
    device, adv = hits[0]
    print(f"Using {device.name or 'Hatch Rest'} ({device.address}, RSSI {adv.rssi})", file=sys.stderr)
    return device


async def send(client: BleakClient, command: str) -> None:
    """Write one ASCII command to the TX characteristic."""
    print(f"  -> {command}")
    await client.write_gatt_char(CHAR_TX, command.encode("ascii"), response=True)
    # The Rest needs ~1s to reflect a write in its feedback characteristic;
    # 0.25s often reads back the *previous* state (the command still applies).
    await asyncio.sleep(1.0)  # let the device settle before we read it back


async def read_state(client: BleakClient) -> dict | None:
    """Read and decode the current state."""
    data = await client.read_gatt_char(CHAR_FEEDBACK)
    return parse_feedback(bytes(data))


# --- commands ---------------------------------------------------------------


async def cmd_scan(args: argparse.Namespace) -> None:
    """List nearby Hatch Rest devices."""
    print(f"Scanning {args.timeout:.0f}s...")
    hits = await discover(args.timeout)
    if not hits:
        print("No Hatch Rest devices found.")
        return
    for device, adv in hits:
        print(f"  {device.address}  name={device.name!r}  rssi={adv.rssi}")
        print(f"    advertised service UUIDs: {adv.service_uuids or '(none)'}")


async def _with_client(args: argparse.Namespace, action) -> None:
    """Resolve the target, connect, run `action(client)`, then show state."""
    target = await resolve_target(args.address, args.timeout)
    async with BleakClient(target) as client:
        print(f"Connected to {client.address}")
        await action(client)
        print("State:")
        print_state(await read_state(client))


async def cmd_status(args: argparse.Namespace) -> None:
    await _with_client(args, lambda client: asyncio.sleep(0))


async def cmd_on(args: argparse.Namespace) -> None:
    await _with_client(args, lambda c: send(c, "SI{:02x}".format(1)))


async def cmd_off(args: argparse.Namespace) -> None:
    await _with_client(args, lambda c: send(c, "SI{:02x}".format(0)))


async def cmd_color(args: argparse.Namespace) -> None:
    async def action(client: BleakClient) -> None:
        state = await read_state(client) or {"brightness": 255}
        bri = state["brightness"] or 255
        await send(client, "SC{:02x}{:02x}{:02x}{:02x}".format(args.r, args.g, args.b, bri))

    await _with_client(args, action)


async def cmd_brightness(args: argparse.Namespace) -> None:
    async def action(client: BleakClient) -> None:
        state = await read_state(client) or {"rgb": (255, 255, 255)}
        r, g, b = state["rgb"]
        await send(client, "SC{:02x}{:02x}{:02x}{:02x}".format(r, g, b, args.value))

    await _with_client(args, action)


async def cmd_sound(args: argparse.Namespace) -> None:
    await _with_client(args, lambda c: send(c, "SN{:02x}".format(args.value)))


async def cmd_volume(args: argparse.Namespace) -> None:
    await _with_client(args, lambda c: send(c, "SV{:02x}".format(args.value)))


async def cmd_raw(args: argparse.Namespace) -> None:
    """Send an arbitrary ASCII command (advanced/debugging)."""
    await _with_client(args, lambda c: send(c, args.command))


async def cmd_watch(args: argparse.Namespace) -> None:
    """Subscribe to notifications and print state as it changes."""
    target = await resolve_target(args.address, args.timeout)
    async with BleakClient(target) as client:
        print(f"Connected to {client.address}. Watching for changes (Ctrl+C to stop)...")

        def on_notify(_char, data: bytearray) -> None:
            print("Update:")
            print_state(parse_feedback(bytes(data)))

        await client.start_notify(CHAR_FEEDBACK, on_notify)
        print("Initial state:")
        print_state(await read_state(client))
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass


# --- argument parsing -------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bleak test tool for the 1st-gen Hatch Rest")
    parser.add_argument("--address", help="BLE address/UUID (default: auto-discover)")
    parser.add_argument("--timeout", type=float, default=10.0, help="scan timeout seconds (default 10)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="list nearby Hatch Rest devices").set_defaults(func=cmd_scan)
    sub.add_parser("status", help="show current state").set_defaults(func=cmd_status)
    sub.add_parser("on", help="power on").set_defaults(func=cmd_on)
    sub.add_parser("off", help="power off").set_defaults(func=cmd_off)
    sub.add_parser("watch", help="stream live state updates").set_defaults(func=cmd_watch)

    p_color = sub.add_parser("color", help="set RGB color (0-255 each)")
    p_color.add_argument("r", type=int)
    p_color.add_argument("g", type=int)
    p_color.add_argument("b", type=int)
    p_color.set_defaults(func=cmd_color)

    p_bri = sub.add_parser("brightness", help="set brightness (0-255)")
    p_bri.add_argument("value", type=int)
    p_bri.set_defaults(func=cmd_brightness)

    p_sound = sub.add_parser("sound", help="set sound by id (e.g. 5=Ocean)")
    p_sound.add_argument("value", type=int)
    p_sound.set_defaults(func=cmd_sound)

    p_vol = sub.add_parser("volume", help="set volume (0-255)")
    p_vol.add_argument("value", type=int)
    p_vol.set_defaults(func=cmd_volume)

    p_raw = sub.add_parser("raw", help="send a raw ASCII command, e.g. SI01")
    p_raw.add_argument("command")
    p_raw.set_defaults(func=cmd_raw)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        asyncio.run(args.func(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
