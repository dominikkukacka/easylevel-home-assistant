"""Config flow and options flow for EasyLevel."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback

from .const import (
    CONF_POLL_INTERVAL,
    CONF_POLLING_ENABLED,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POLLING_ENABLED,
    DEVICE_NAME_PREFIX,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class EasyLevelConfigFlow(ConfigFlow, domain=DOMAIN):
    """
    Handle a config flow for EasyLevel.

    Triggered either:
    - Automatically via Bluetooth discovery (manifest matches CARATI*)
    - Manually by the user via Settings → Integrations → Add Integration
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialise."""
        self._discovered_devices: dict[str, str] = {}  # address → name
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    # ── Options flow hook ─────────────────────────────────────────────────────

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EasyLevelOptionsFlow:
        """Return the options flow handler."""
        return EasyLevelOptionsFlow(config_entry)

    # ── Automatic Bluetooth discovery ─────────────────────────────────────────

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle auto-discovery by HA's BT stack."""
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
        """Confirm adding the auto-discovered device."""
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
        """Show list of visible CARATI devices for manual setup."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            name = self._discovered_devices.get(address, address)
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=name,
                data={CONF_ADDRESS: address},
            )

        self._discovered_devices = {}
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.name and info.name.upper().startswith(DEVICE_NAME_PREFIX.upper()):
                self._discovered_devices[info.address] = info.name

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        options = {
            addr: f"{name} ({addr})"
            for addr, name in self._discovered_devices.items()
        }
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(options)}),
        )

    # ── Helper ────────────────────────────────────────────────────────────────

    def _async_create_entry_from_discovery(
        self, info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        return self.async_create_entry(
            title=info.name or info.address,
            data={CONF_ADDRESS: info.address},
        )


class EasyLevelOptionsFlow(OptionsFlow):
    """
    Options flow — lets the user configure polling after initial setup.

    Accessible via:
      Settings → Devices & Services → EasyLevel → Configure
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise with current options."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and handle the options form."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Pre-fill with current values (or defaults for first time)
        current_enabled = self._config_entry.options.get(
            CONF_POLLING_ENABLED, DEFAULT_POLLING_ENABLED
        )
        current_interval = self._config_entry.options.get(
            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_POLLING_ENABLED, default=current_enabled): bool,
                vol.Required(CONF_POLL_INTERVAL, default=current_interval): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL),
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "min_interval": str(MIN_POLL_INTERVAL),
                "max_interval": str(MAX_POLL_INTERVAL),
            },
        )
