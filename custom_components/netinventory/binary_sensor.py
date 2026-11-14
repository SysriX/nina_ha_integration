"""Binary sensors: device online, HASS.Agent online, HASS.Agent binary sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from .entity import NetInventoryEntity, add_dynamic

_CLASSES = {c.value for c in BinarySensorDeviceClass}


class OnlineSensor(NetInventoryEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, device_id: int, key: str) -> None:
        super().__init__(coordinator, device_id, key, "binary_sensor")
        self._attr_translation_key = key
        if key == "agent_online":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        if self.key == "agent_online":
            return bool(self.agent.get("online"))
        return bool(self.dev.get("online"))

    @property
    def extra_state_attributes(self):
        d = self.dev
        if self.key == "agent_online":
            return {"version": self.agent.get("version"), "system": self.agent.get("modell"), "last_data": self.agent.get("zuletzt")}
        return {"ip": d.get("ip"), "mac": d.get("mac"), "last_online": d.get("zuletzt_online"), "wake_on_lan": d.get("wol")}


class AgentBinarySensor(NetInventoryEntity, BinarySensorEntity):
    def __init__(self, coordinator, device_id: int, s: dict) -> None:
        super().__init__(coordinator, device_id, f"agent_{s['schluessel']}", "binary_sensor", suffix=s.get("anzeige") or s["schluessel"])
        self.schluessel = s["schluessel"]
        self._attr_name = s.get("anzeige") or s["schluessel"]
        dc = s.get("device_class") or ""
        self._attr_device_class = BinarySensorDeviceClass(dc) if dc in _CLASSES else None
        self._attr_icon = s.get("icon") or None

    @property
    def _s(self) -> dict:
        return next((x for x in self.agent.get("sensoren", []) if x["schluessel"] == self.schluessel), {})

    @property
    def available(self) -> bool:
        return super().available and bool(self._s) and bool(self.agent.get("online"))

    @property
    def is_on(self) -> bool | None:
        v = str(self._s.get("wert") or "").strip().lower()
        if v in ("", "unknown", "none"):
            return None
        return v in ("on", "true", "1", "yes", "an")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coord = entry.runtime_data

    def factory(dev_id: int, dev: dict):
        ents = [OnlineSensor(coord, dev_id, "online")]
        ag = dev.get("agent")
        if ag:
            ents.append(OnlineSensor(coord, dev_id, "agent_online"))
            ents += [AgentBinarySensor(coord, dev_id, s) for s in ag.get("sensoren", []) if s.get("art") == "binary_sensor"]
        return ents

    add_dynamic(coord, async_add_entities, factory, entry.runtime_data.unsubs)
