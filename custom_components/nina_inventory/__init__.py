"""NINA – network / IT device inventory (container) in Home Assistant.

Each device of the inventory becomes a Home Assistant device with online status, IP/MAC, user, the
HASS.Agent sensors (classified by name patterns in the container) and buttons for Wake-on-LAN and the
HASS.Agent commands. Services for automations: nina_inventory.wake, nina_inventory.command, nina_inventory.scan.
"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NinaApi, NinaAuthError, NinaError
from .const import (ATTR_COMMAND, ATTR_NETWORK_ID, ATTR_VALUE, CONF_REMOVE_STALE, CONF_SSL, CONF_TOKEN, CONF_VERIFY_SSL,
                    DOMAIN, PLATFORMS, SERVICE_COMMAND, SERVICE_REFRESH, SERVICE_SCAN, SERVICE_WAKE)
from .coordinator import NinaCoordinator

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type NinaConfigEntry = ConfigEntry[NinaCoordinator]


async def async_setup(hass: HomeAssistant, config) -> bool:
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NinaConfigEntry) -> bool:
    d = entry.data
    api = NinaApi(async_get_clientsession(hass, verify_ssl=d.get(CONF_VERIFY_SSL, True)), d[CONF_HOST], d[CONF_PORT],
                          d[CONF_TOKEN], d.get(CONF_SSL, False), d.get(CONF_VERIFY_SSL, True))
    try:
        info = await api.info()
    except NinaAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except NinaError as err:
        raise ConfigEntryNotReady(str(err)) from err
    coord = NinaCoordinator(hass, entry, api, info["id"])
    await coord.async_config_entry_first_refresh()
    entry.runtime_data = coord
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if entry.options.get(CONF_REMOVE_STALE, True):
        _remove_stale_devices(hass, entry, coord)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NinaConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        for u in entry.runtime_data.unsubs:
            u()
    return ok


async def async_remove_config_entry_device(hass: HomeAssistant, entry: NinaConfigEntry, device: dr.DeviceEntry) -> bool:
    """Allow deleting a device in HA when it is no longer delivered by the container."""
    coord = entry.runtime_data
    for dom, ident in device.identifiers:
        if dom == DOMAIN and ident.startswith(coord.instance + "_"):
            try:
                if int(ident.rsplit("_", 1)[1]) in (coord.data or {}):
                    return False
            except ValueError:
                pass
    return True


def _remove_stale_devices(hass: HomeAssistant, entry: ConfigEntry, coord: NinaCoordinator) -> None:
    reg = dr.async_get(hass)
    present = {f"{coord.instance}_{i}" for i in (coord.data or {})}
    for dev in dr.async_entries_for_config_entry(reg, entry.entry_id):
        idents = [i for dom, i in dev.identifiers if dom == DOMAIN]
        if idents and not any(i in present for i in idents):
            _LOGGER.info("Removing device %s (no longer in NINA)", dev.name)
            reg.async_update_device(dev.id, remove_config_entry_id=entry.entry_id)


# ------------------------------------------------------------------ services
def _targets(hass: HomeAssistant, call: ServiceCall) -> list[tuple[NinaCoordinator, int]]:
    ids = call.data.get(ATTR_DEVICE_ID) or []
    if isinstance(ids, str):
        ids = [ids]
    if not ids:
        raise ServiceValidationError("No device selected (device_id)")
    reg = dr.async_get(hass)
    entries = {e.entry_id: e for e in hass.config_entries.async_loaded_entries(DOMAIN)}
    out = []
    for did in ids:
        dev = reg.async_get(did)
        if not dev:
            raise ServiceValidationError(f"Unknown device {did}")
        hit = None
        for eid in dev.config_entries:
            e = entries.get(eid)
            if not e:
                continue
            coord: NinaCoordinator = e.runtime_data
            for dom, ident in dev.identifiers:
                if dom == DOMAIN and ident.startswith(coord.instance + "_"):
                    hit = (coord, int(ident.rsplit("_", 1)[1]))
        if not hit:
            raise ServiceValidationError(f"{dev.name} is not a NINA device")
        out.append(hit)
    return out


def _register_services(hass: HomeAssistant) -> None:
    async def wake(call: ServiceCall):
        res = {}
        for coord, gid in _targets(hass, call):
            try:
                res[str(gid)] = await coord.api.wake(gid)
            except NinaError as err:
                raise HomeAssistantError(str(err)) from err
        return {"results": res} if call.return_response else None

    async def command(call: ServiceCall):
        res = {}
        for coord, gid in _targets(hass, call):
            try:
                res[str(gid)] = await coord.api.command(gid, call.data[ATTR_COMMAND], call.data.get(ATTR_VALUE))
            except NinaError as err:
                raise HomeAssistantError(str(err)) from err
            await coord.async_request_refresh()
        return {"results": res} if call.return_response else None

    async def scan(call: ServiceCall):
        out = []
        for e in hass.config_entries.async_loaded_entries(DOMAIN):
            try:
                out.append(await e.runtime_data.api.scan(call.data.get(ATTR_NETWORK_ID)))
            except NinaError as err:
                raise HomeAssistantError(str(err)) from err
            await e.runtime_data.async_request_refresh()
        return {"results": out} if call.return_response else None

    async def refresh(call: ServiceCall) -> None:
        for e in hass.config_entries.async_loaded_entries(DOMAIN):
            await e.runtime_data.async_request_refresh()

    dev_schema = {vol.Required(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string])}
    hass.services.async_register(DOMAIN, SERVICE_WAKE, wake, schema=vol.Schema(dev_schema), supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_COMMAND, command, schema=vol.Schema({
        **dev_schema, vol.Required(ATTR_COMMAND): cv.string, vol.Optional(ATTR_VALUE): cv.string}),
        supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_SCAN, scan, schema=vol.Schema({vol.Optional(ATTR_NETWORK_ID): cv.positive_int}),
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, refresh)
