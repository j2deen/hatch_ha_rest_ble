"""Constants for the Hatch Rest (BLE) integration."""

from __future__ import annotations

DOMAIN = "hatch_rest_ble"

# Manufacturer ID advertised by the 1st-gen Hatch Rest (0x0434).
MANUFACTURER_ID = 1076

# BLE GATT characteristics (service 02240001-5efd-47eb-9c1a-de53f7a2b232).
CHAR_TX = "02240002-5efd-47eb-9c1a-de53f7a2b232"  # write commands here
CHAR_FEEDBACK = "02260002-5efd-47eb-9c1a-de53f7a2b232"  # read/notify state here

# Setting the color to (254, 254, 254) puts the lamp into "rainbow" / gradient mode.
COLOR_RAINBOW = (254, 254, 254)
EFFECT_RAINBOW = "rainbow"

# Sound id -> friendly name. Ids match the on-device track table; gaps are intentional
# (the firmware skips a few ids). Derived from the Hatch Rest BLE protocol.
SOUNDS: dict[int, str] = {
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
SOUND_NAME_TO_ID: dict[str, int] = {name: sid for sid, name in SOUNDS.items()}
