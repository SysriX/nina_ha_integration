"""Buttons: Wake-on-LAN, reachability check and the HASS.Agent commands (shutdown, restart, lock …)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import NetInventoryError
from .entity import NetInventoryEntity, add_dynamic


class WakeButton(NetInventoryEntity, ButtonEntity):
    _attr_translation_key = "wake"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator, device_id: int) -> None:
        super().__init__(coordinator, device_id, "wake", "button")

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.wake(self.device_id)
        except NetInventoryError as err:
            raise HomeAssistantError(str(err)) from err


class CheckButton(NetInventoryEntity, ButtonEntity):
    _attr_translation_key = "check"
    _attr_icon = "mdi:lan-pending"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_id: int) -> None:
        super().__init__(coordinator, device_id, "check", "button")

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.check(self.device_id)
        except NetInventoryError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()


class CommandButton(NetInventoryEntity, ButtonEntity):
    def __init__(self, coordinator, device_id: int, b: dict) -> None:
        super().__init__(coordinator, device_id, f"cmd_{b['schluessel']}", "button", suffix=b.get("kategorie") or b.get("anzeige") or b["schluessel"])
        self.schluessel = b["schluessel"]
        self._attr_name = b.get("anzeige") or b["schluessel"]
        self._attr_icon = b.get("icon") or "mdi:console"

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
        except NetInventoryError as err:
            raise HomeAssistantError(str(err)) from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coord = entry.runtime_data

    def factory(dev_id: int, dev: dict):
        ents = [CheckButton(coord, dev_id)]
        if dev.get("wol"):
            ents.append(WakeButton(coord, dev_id))
        for b in (dev.get("agent") or {}).get("befehle", []):
            if b.get("art") in ("button", "lock"):
                ents.append(CommandButton(coord, dev_id, b))
        return ents

    add_dynamic(coord, async_add_entities, factory, entry.runtime_data.unsubs)
