"""Buttons: Wake-on-LAN, reachability check and the HASS.Agent commands (shutdown, restart, lock …)."""
from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import NinaError
from .const import DOMAIN
from .entity import NinaEntity, add_dynamic, slug

# HASS.Agent command keys / categories → HA device class (restart and update get the matching icon and meaning)
_DEVICE_CLASS = {"restart": ButtonDeviceClass.RESTART, "reboot": ButtonDeviceClass.RESTART, "update": ButtonDeviceClass.UPDATE}
# containers before 2.4.0 do not announce their tasks: only the scan exists there
_TASKS_FALLBACK = [{"schluessel": "scan", "name": "Netzwerk-Scan", "icon": "mdi:lan-pending"}]


class WakeButton(NinaEntity, ButtonEntity):
    _attr_translation_key = "wake"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator, device_id: int) -> None:
        super().__init__(coordinator, device_id, "wake", "button")

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.wake(self.device_id)
        except NinaError as err:
            raise HomeAssistantError(str(err)) from err


class CheckButton(NinaEntity, ButtonEntity):
    _attr_translation_key = "check"
    _attr_icon = "mdi:lan-pending"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_id: int) -> None:
        super().__init__(coordinator, device_id, "check", "button")

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.check(self.device_id)
        except NinaError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()


class CommandButton(NinaEntity, ButtonEntity):
    def __init__(self, coordinator, device_id: int, b: dict) -> None:
        super().__init__(coordinator, device_id, f"cmd_{b['schluessel']}", "button", suffix=b.get("kategorie") or b.get("anzeige") or b["schluessel"])
        self.schluessel = b["schluessel"]
        self._attr_name = b.get("anzeige") or b["schluessel"]
        self._attr_icon = b.get("icon") or "mdi:console"
        key = b["schluessel"].lower()
        self._attr_device_class = _DEVICE_CLASS.get(key) or _DEVICE_CLASS.get((b.get("kategorie") or "").lower())
        if self._attr_device_class and not b.get("icon"):
            self._attr_icon = None

    @property
    def available(self) -> bool:
        return super().available and any(x["schluessel"] == self.schluessel for x in self.agent.get("befehle", []))

    @property
    def extra_state_attributes(self):
        b = next((x for x in self.agent.get("befehle", []) if x["schluessel"] == self.schluessel), {})
        return {"agent_key": self.schluessel, "category": b.get("kategorie") or None, "agent_online": self.agent.get("online")}

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.command(self.device_id, self.schluessel)
        except NinaError as err:
            raise HomeAssistantError(str(err)) from err


class TaskButton(CoordinatorEntity, ButtonEntity):
    """Button on the NINA device itself: network scan, OPNsense query, agent sync."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, t: dict) -> None:
        super().__init__(coordinator)
        self.task = t["schluessel"]
        info = coordinator.info or {}
        self._attr_name = t.get("name") or self.task
        self._attr_icon = t.get("icon") or "mdi:play"
        self._attr_unique_id = f"{coordinator.instance}_hub_{self.task}"
        self.entity_id = f"button.haus_net_nina_{slug(self.task)}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.instance}_hub")},
            name=info.get("name") or "NINA", manufacturer="SysriX", model="NINA Network Inventory Assistant",
            sw_version=info.get("version"), configuration_url=coordinator.api.base)

    async def async_press(self) -> None:
        try:
            if self.task == "scan" and not (self.coordinator.info or {}).get("aufgaben"):
                await self.coordinator.api.scan()
            else:
                res = await self.coordinator.api.task(self.task)
                if not res.get("ok", True):
                    raise HomeAssistantError(str(res.get("ergebnis")))
        except NinaError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coord = entry.runtime_data
    async_add_entities([TaskButton(coord, t) for t in (coord.info.get("aufgaben") or _TASKS_FALLBACK)])

    def factory(dev_id: int, dev: dict):
        ents = [CheckButton(coord, dev_id)]
        if dev.get("wol"):
            ents.append(WakeButton(coord, dev_id))
        for b in (dev.get("agent") or {}).get("befehle", []):
            if b.get("art") != "switch":
                ents.append(CommandButton(coord, dev_id, b))
        return ents

    add_dynamic(coord, async_add_entities, factory, entry.runtime_data.unsubs)
