"""Config flow for EasyLevel."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DEVICE_NAME_PREFIX, DOMAIN

_LOGGER = logging.getLogger(__name__)


class EasyLevelConfigFlow(ConfigFlow, domain=DOMAIN):
    """
    Handle a config flow for EasyLevel.

    The flow is triggered either:
    - Automatically via Bluetooth discovery (manifest bluetooth filter matches CARATI*)
    - Manually by the user via Settings → Integrations → Add Integration
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialise."""
        self._discovered_devices: dict[str, str] = {}  # address → name
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    # ── Automatic Bluetooth discovery ─────────────────────────────────────────

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """
        Handle a device discovered automatically by Home Assistant's BT stack.

        This is called when HA sees an advertisement matching local_name: CARATI*
        from manifest.json.
        """
        _LOGGER.debug(
            "EasyLevel: BT discovery — name=%s  address=%s",
            discovery_info.name,
            discovery_info.address,
        )

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
        """Confirm adding the discovered device."""
        assert self._discovery_info is not None

        if user_input is not None:
            return self._async_create_entry_from_discovery(self._discovery_info)

        name = self._discovery_info.name or self._discovery_info.address
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": name},
        )

    # ── Manual setup ──────────────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual setup — show list of discovered CARATI devices."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            name = self._discovered_devices.get(address, address)
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=name,
                data={CONF_ADDRESS: address},
            )

        # Scan current BLE advertisements for CARATI devices
        self._discovered_devices = {}
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.name and info.name.upper().startswith(DEVICE_NAME_PREFIX.upper()):
                self._discovered_devices[info.address] = info.name

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_schema(),
        )

    def _build_schema(self):
        """Build device selection schema."""
        import voluptuous as vol

        options = {
            addr: f"{name} ({addr})"
            for addr, name in self._discovered_devices.items()
        }
        return vol.Schema({vol.Required(CONF_ADDRESS): vol.In(options)})

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _async_create_entry_from_discovery(
        self, info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        name = info.name or info.address
        return self.async_create_entry(
            title=name,
            data={CONF_ADDRESS: info.address},
        )
