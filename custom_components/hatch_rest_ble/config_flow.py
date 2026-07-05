"""Config flow for the Hatch Rest (BLE) integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback

from .const import (
    CHAR_TX,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MANUFACTURER_ID,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)


def _is_hatch_rest(info: BluetoothServiceInfoBleak) -> bool:
    """Return True if an advertisement looks like a Hatch device.

    All Hatch products share manufacturer id 1076 and advertise nothing that
    distinguishes the BLE-controllable 1st-gen Rest from cloud-only models,
    so the flow probes the GATT table before creating an entry.
    """
    return MANUFACTURER_ID in info.manufacturer_data


class HatchRestConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hatch Rest (BLE)."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HatchRestOptionsFlow:
        """Return the options flow (poll interval)."""
        return HatchRestOptionsFlow()

    def __init__(self) -> None:
        """Initialise the flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered: dict[str, str] = {}

    async def _async_verify(self, address: str) -> str | None:
        """Connect and check the device exposes the Rest control characteristic.

        Returns None when the device is a controllable Rest, otherwise an
        abort reason ("cannot_connect" or "not_supported").
        """
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, address, connectable=True
        )
        if ble_device is None:
            return "cannot_connect"
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                ble_device.name or address,
            )
        except Exception:  # noqa: BLE001 - any connect failure ends the flow
            return "cannot_connect"
        try:
            supported = client.services.get_characteristic(CHAR_TX) is not None
        except Exception:  # noqa: BLE001
            supported = False
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001 - best effort
                pass
        return None if supported else "not_supported"

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a device discovered via the Bluetooth integration."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding a discovered device."""
        assert self._discovery_info is not None
        name = self._discovery_info.name or self._discovery_info.address
        if user_input is not None:
            if (reason := await self._async_verify(self._discovery_info.address)):
                return self.async_abort(reason=reason)
            return self.async_create_entry(title=name, data={})

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": name},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the manual / picker step."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            if (reason := await self._async_verify(address)):
                return self.async_abort(reason=reason)
            return self.async_create_entry(
                title=self._discovered.get(address, address), data={}
            )

        current_addresses = self._async_current_ids()
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current_addresses or info.address in self._discovered:
                continue
            if _is_hatch_rest(info):
                self._discovered[info.address] = info.name or info.address

        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{name} ({address})"
                            for address, name in self._discovered.items()
                        }
                    )
                }
            ),
        )


class HatchRestOptionsFlow(OptionsFlow):
    """Options: tune how often the device is polled."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and save the options form."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL),
                    )
                }
            ),
        )
