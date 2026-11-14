"""Config flow: automatic discovery via zeroconf (_netinventory._tcp) or manual host/port + API key."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (BooleanSelector, NumberSelector, NumberSelectorConfig, NumberSelectorMode,
                                            SelectSelector, SelectSelectorConfig, SelectSelectorMode, TextSelector,
                                            TextSelectorConfig, TextSelectorType)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import NetInventoryApi, NetInventoryAuthError, NetInventoryError
from .const import (CONF_INTERVAL, CONF_ONLY_AGENT, CONF_REMOVE_STALE, CONF_SSL, CONF_TOKEN, CONF_TYPES, CONF_VERIFY_SSL,
                    DEFAULT_INTERVAL, DEFAULT_PORT, DOMAIN, TYPES)

_PW = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def _check(hass, data: dict) -> dict:
    api = NetInventoryApi(async_get_clientsession(hass, verify_ssl=data.get(CONF_VERIFY_SSL, True)), data[CONF_HOST],
                          int(data[CONF_PORT]), data[CONF_TOKEN], data.get(CONF_SSL, False), data.get(CONF_VERIFY_SSL, True))
    return await api.info()


class NetInventoryConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._found: dict[str, Any] = {}

    async def _try(self, data: dict, errors: dict) -> dict | None:
        try:
            return await _check(self.hass, data)
        except NetInventoryAuthError:
            errors["base"] = "invalid_auth"
        except NetInventoryError:
            errors["base"] = "cannot_connect"
        return None

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            info = await self._try(user_input, errors)
            if info:
                await self.async_set_unique_id(info["id"])
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST], CONF_PORT: user_input[CONF_PORT]})
                return self.async_create_entry(title=info.get("name") or "NetInventory", data=user_input)
        d = user_input or {}
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=d.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=d.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required(CONF_TOKEN): _PW,
            vol.Optional(CONF_SSL, default=d.get(CONF_SSL, False)): bool,
            vol.Optional(CONF_VERIFY_SSL, default=d.get(CONF_VERIFY_SSL, True)): bool,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        props = discovery_info.properties or {}
        inst = props.get("id")
        if not inst:
            return self.async_abort(reason="no_id")
        host = str(discovery_info.ip_address)
        await self.async_set_unique_id(inst)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: discovery_info.port})
        self._found = {CONF_HOST: host, CONF_PORT: discovery_info.port, "name": props.get("name") or "NetInventory"}
        self.context["title_placeholders"] = {"name": self._found["name"], "host": host}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {CONF_HOST: self._found[CONF_HOST], CONF_PORT: self._found[CONF_PORT], CONF_TOKEN: user_input[CONF_TOKEN],
                    CONF_SSL: False, CONF_VERIFY_SSL: True}
            info = await self._try(data, errors)
            if info:
                return self.async_create_entry(title=info.get("name") or self._found["name"], data=data)
        return self.async_show_form(step_id="zeroconf_confirm", data_schema=vol.Schema({vol.Required(CONF_TOKEN): _PW}),
                                    errors=errors, description_placeholders={"name": self._found["name"],
                                                                             "url": f"http://{self._found[CONF_HOST]}:{self._found[CONF_PORT]}"})

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, CONF_TOKEN: user_input[CONF_TOKEN]}
            if await self._try(data, errors):
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_TOKEN): _PW}), errors=errors)

    async def async_step_reconfigure(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            data = {**entry.data, **user_input}
            if not data.get(CONF_TOKEN):
                data[CONF_TOKEN] = entry.data[CONF_TOKEN]
            info = await self._try(data, errors)
            if info:
                await self.async_set_unique_id(info["id"])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data=data)
        d = entry.data
        return self.async_show_form(step_id="reconfigure", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_HOST, default=d[CONF_HOST]): str,
            vol.Required(CONF_PORT, default=d[CONF_PORT]): int,
            vol.Optional(CONF_TOKEN, default=""): _PW,
            vol.Optional(CONF_SSL, default=d.get(CONF_SSL, False)): bool,
            vol.Optional(CONF_VERIFY_SSL, default=d.get(CONF_VERIFY_SSL, True)): bool,
        }))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NetInventoryOptionsFlow()


class NetInventoryOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        o = self.config_entry.options
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_INTERVAL, default=o.get(CONF_INTERVAL, DEFAULT_INTERVAL)):
                NumberSelector(NumberSelectorConfig(min=5, max=600, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="s")),
            vol.Optional(CONF_TYPES, default=o.get(CONF_TYPES, [])):
                SelectSelector(SelectSelectorConfig(options=[{"value": k, "label": v} for k, v in TYPES.items()],
                                                    multiple=True, mode=SelectSelectorMode.DROPDOWN)),
            vol.Optional(CONF_ONLY_AGENT, default=o.get(CONF_ONLY_AGENT, False)): BooleanSelector(),
            vol.Optional(CONF_REMOVE_STALE, default=o.get(CONF_REMOVE_STALE, True)): BooleanSelector(),
        }))
