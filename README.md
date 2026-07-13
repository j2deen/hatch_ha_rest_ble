# Hatch Rest (BLE) — Home Assistant integration

Local control of the **1st-generation Hatch Baby Rest** night light + sound machine
over Bluetooth Low Energy — **no cloud, no Hatch account, works through ESPHome
Bluetooth proxies**.

This integration was reverse-engineered from the Hatch Sleep Android app (v6.24.1)
and cross-checked against the community's prior work
([Marcus-L](https://github.com/Marcus-L/m4rcus.HatchBaby.Rest),
[kjoconnor/pyhatchbabyrest](https://github.com/kjoconnor/pyhatchbabyrest)).

> Repository: <https://github.com/j2deen/hatch_ha_rest_ble>

## ⚠️ Device compatibility

This only works with the **original Rest (1st-gen)** — the one that exposes a real
local BLE control protocol.

| Model | Local BLE control? | Notes |
|---|---|---|
| **Rest (1st-gen)** | ✅ **Yes** — this integration | |
| Rest+ | ⚠️ Partial | Has a richer BLE service; not implemented here |
| Restore / Restore 2 / 3 / iQ | ❌ No | Cloud/WiFi only (AWS IoT MQTT); BLE is setup-only |
| Rest Mini / Rest 2nd-gen / Grow / Sleep Clock | ❌ No | Cloud/WiFi only |

For the cloud-only models, use the cloud integration
[`dahlb/ha_hatch`](https://github.com/dahlb/ha_hatch) instead — Bluetooth proxies
cannot control them because the devices simply don't accept control over BLE.

## Features

One device with four entities:

| Entity | What it does |
|---|---|
| **Light** | RGB colour, brightness, and a `rainbow` effect (the device's gradient mode). Turning the light off dims it to zero — sound keeps playing. |
| **Switch** | Master power — turns the whole device (light *and* sound) on/off. |
| **Select** | Sound / white-noise track (Ocean, Rain, White Noise, …, or Off). |
| **Number** | Volume (0–100 %). |

- Auto-discovery via the HA Bluetooth integration (matches manufacturer ID `1076`).
  All Hatch products share that ID and advertise nothing model-specific, so the
  config flow connects and verifies the Rest control characteristic before adding
  a device — cloud-only models are rejected with a pointer to `dahlb/ha_hatch`.
- Fully local (`local_polling`) over a persistent BLE connection — see
  [Polling & responsiveness](#polling--responsiveness).
- The Rest accepts multiple simultaneous BLE connections, so the Hatch phone app
  keeps working alongside Home Assistant.

## Installation

### HACS (recommended)
1. HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/j2deen/hatch_ha_rest_ble`, category **Integration**
3. Install **Hatch Rest (BLE)**, then restart Home Assistant
4. The Rest should be auto-discovered (Settings → Devices & Services). If not,
   add it manually via **+ Add Integration → Hatch Rest (BLE)**.

### Manual
Copy `custom_components/hatch_rest_ble/` into your HA `config/custom_components/`
directory and restart.

## Polling & responsiveness

The 1st-gen Rest does **not** push state notifications over BLE (verified on
hardware), so this integration polls the device — by default **every 30 seconds**
over its persistent connection.

What that means in practice:

- **Changes made in Home Assistant appear immediately.** Every command is
  confirmed by reading the device back (~1 s), so the poll interval does not
  affect HA-initiated control at all.
- **Changes made outside Home Assistant** (the Hatch phone app, or the buttons on
  the device) show up in HA within one poll interval — up to 30 s by default.

You can change the interval in **Settings → Devices & Services → Hatch Rest
(BLE) → Configure** (10–300 s). When to bother:

- **Lower it (10–15 s)** if your household actively uses the phone app or the
  device buttons and you have automations reacting to the device's state — e.g.
  "when the sound machine turns on, dim the hallway lights". Each poll is a
  single small GATT read on an already-open connection, so even 10 s is a light
  load for a Bluetooth adapter or ESPHome proxy.
- **Raise it (60–300 s)** if HA is the only thing controlling the device, or if
  the proxy serving the Rest is congested with many other BLE devices and you
  want to minimise traffic. HA-side control stays instant regardless.
- **Leave it at 30 s** otherwise — it's a sensible middle ground.

## Offline behaviour

It's fine to unplug the Rest or take it travelling. The integration never blocks
Home Assistant startup on an absent device:

- Setup completes instantly; if the device can't be reached, its entities show
  **unavailable** rather than delaying HA.
- While the device is away, polls fail fast (a presence check, not a connection
  timeout), and HA marks the entities unavailable as soon as the Bluetooth stack
  loses the device's advertisements.
- When it's plugged back in, the first advertisement triggers an immediate
  refresh — entities typically recover within a few seconds, no restart needed.

## Requirements

- Home Assistant 2025.3 or newer (the integration icon requires 2026.3+, which
  serves brand images bundled in the integration's `brand/` folder)
- A Bluetooth adapter on the HA host **or** an ESPHome Bluetooth proxy in range of
  the Rest (the proxy must allow active connections, which is the default).

## Protocol reference

GATT service `02240001-5efd-47eb-9c1a-de53f7a2b232`:

| Characteristic | UUID | Use |
|---|---|---|
| TX (write) | `02240002-5efd-47eb-9c1a-de53f7a2b232` | ASCII commands |
| Feedback (read/notify) | `02260002-5efd-47eb-9c1a-de53f7a2b232` | current state |

Commands (UTF-8 ASCII written to TX):

| Action | Format | Example |
|---|---|---|
| Power | `SI{:02x}` | `SI01` = on |
| Colour + brightness | `SC{r}{g}{b}{i}` (each `{:02x}`, 0–255) | `SCff0000ff` = red, full |
| Sound | `SN{:02x}` | `SN05` = Ocean |
| Volume | `SV{:02x}` (0–255) | `SV80` |

Setting the colour to `(254, 254, 254)` = `SCfefefe{i}` enables rainbow mode.

Feedback packet layout (delimited by ASCII `C`/`S`/`P`):

```
idx:  5    6   7   8   9    10   11    12   13   14
      'C'  R   G   B   bri  'S'  snd   vol  'P'  flags
```

Power is **inverted** in the flags byte: the device is ON when `flags & 0xC0 == 0`.

## Credits

- BLE protocol originally documented by Marcus-L and the `pyhatchbabyrest` project.
- This integration: a clean, Bluetooth-proxy-native HA implementation.
