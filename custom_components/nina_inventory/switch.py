"""Switches: HASS.Agent commands of type switch."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import NinaError
from .entity import NinaEntity, add_dynamic


class CommandSwitch(NinaEntity, SwitchEntity):
    def __init__(self, coordinator, device_id: int, b: dict) -> None:
        super().__init__(coordinator, device_id, f"cmd_{b['schluessel']}", "switch", suffix=b.get("anzeige") or b["schluessel"])
        self.schluessel = b["schluessel"]
        self._attr_name = b.get("anzeige") or b["schluessel"]
        self._attr_icon = b.get("icon") or "mdi:toggle-switch"

    @property
    def _b(self) -> dict:
        return next((x for x in self.agent.get("befehle", []) if x["schluessel"] == self.schluessel), {})

    @property
    def available(self) -> bool:
        return super().available and bool(self._b)

    @property
    def is_on(self) -> bool | None:
        z = str(self._b.get("zustand") or "").lower()
        return None if not z else z in ("on", "true", "1", "an")

    async def _send(self, on: bool) -> None:
        try:
            await self.coordinator.api.command(self.device_id, self.schluessel, "on" if on else "off")
        except NinaError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        await self._send(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._send(False)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coord = entry.runtime_data

    def factory(dev_id: int, dev: dict):
        return [CommandSwitch(coord, dev_id, b) for b in (dev.get("agent") or {}).get("befehle", []) if b.get("art") == "switch"]

    add_dynamic(coord, async_add_entities, factory, entry.runtime_data.unsubs)
