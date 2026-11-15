"""Sensors: network data per device and the (pattern-classified) HASS.Agent sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .entity import NinaEntity, add_dynamic

_DEVICE_CLASSES = {c.value for c in SensorDeviceClass}
_STATE_CLASSES = {c.value for c in SensorStateClass}


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


class InfoSensor(NinaEntity, SensorEntity):
    """ip, mac, user, logged-in user, last online, network."""

    def __init__(self, coordinator, device_id: int, key: str) -> None:
        super().__init__(coordinator, device_id, key, "sensor")
        self._attr_translation_key = key
        if key in ("ip", "mac", "network", "last_online"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if key == "last_online":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = {"ip": "mdi:ip-network", "mac": "mdi:ethernet", "user": "mdi:account-tie",
                           "logged_in_user": "mdi:account", "network": "mdi:lan"}.get(key)

    @property
    def native_value(self):
        d = self.dev
        if self.key == "last_online":
            # While online keep the value (no new state on every poll); it moves when the device goes offline
            if d.get("online") and getattr(self, "_last", None):
                return self._last
            self._last = dt_util.parse_datetime(d.get("zuletzt_online") or "")
            return self._last
        v = {"ip": d.get("ip"), "mac": d.get("mac"), "user": d.get("benutzer"), "logged_in_user": d.get("angemeldet"),
             "network": d.get("netzwerk")}.get(self.key)
        return v or None

    @property
    def extra_state_attributes(self):
        if self.key != "ip":
            return None
        d = self.dev
        return {"hostname": d.get("hostname"), "network": d.get("netzwerk"), "type": d.get("typ"), "types": d.get("typen") or [d.get("typ")],
                "type_names": d.get("typ_namen") or [d.get("typ_name")], "manufacturer": d.get("hersteller"), "model": d.get("modell"),
                "location": d.get("standort"), "inventory_number": d.get("inventarnummer"), "tags": d.get("tags"),
                **{f"extra_{k}": v for k, v in (d.get("extra") or {}).items()}}


class AgentSensor(NinaEntity, SensorEntity):
    """One HASS.Agent sensor, classified by the name patterns of the container."""

    def __init__(self, coordinator, device_id: int, s: dict) -> None:
        super().__init__(coordinator, device_id, f"agent_{s['schluessel']}", "sensor", suffix=s.get("anzeige") or s["schluessel"])
        self.schluessel = s["schluessel"]
        self._attr_name = s.get("anzeige") or s["schluessel"]
        dc = s.get("device_class") or ""
        self._attr_device_class = SensorDeviceClass(dc) if dc in _DEVICE_CLASSES else None
        sc = s.get("state_class") or ""
        self._attr_state_class = SensorStateClass(sc) if sc in _STATE_CLASSES else None
        self._attr_native_unit_of_measurement = s.get("einheit") or None
        self._attr_icon = s.get("icon") or None
        self._numeric = bool(self._attr_state_class or self._attr_native_unit_of_measurement) and \
            self._attr_device_class not in (SensorDeviceClass.TIMESTAMP, SensorDeviceClass.ENUM)

    @property
    def _s(self) -> dict:
        return next((x for x in self.agent.get("sensoren", []) if x["schluessel"] == self.schluessel), {})

    @property
    def available(self) -> bool:
        return super().available and bool(self._s) and bool(self.agent.get("online"))

    @property
    def native_value(self):
        v = self._s.get("wert")
        if v in (None, "", "unknown", "unavailable", "None"):
            return None
        if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
            return dt_util.parse_datetime(str(v))
        if self._numeric:
            n = _num(v)
            return n
        return str(v)[:255]

    @property
    def extra_state_attributes(self):
        s = self._s
        attrs = dict(list((s.get("attribute") or {}).items())[:40])
        attrs.update(agent_key=self.schluessel, category=s.get("kategorie") or None)
        return attrs


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coord = entry.runtime_data

    def factory(dev_id: int, dev: dict):
        keys = ["ip", "mac", "network", "user", "last_online"] + (["logged_in_user"] if dev.get("agent") else [])
        ents = [InfoSensor(coord, dev_id, k) for k in keys]
        for s in (dev.get("agent") or {}).get("sensoren", []):
            if s.get("art", "sensor") == "sensor":
                ents.append(AgentSensor(coord, dev_id, s))
        return ents

    add_dynamic(coord, async_add_entities, factory, entry.runtime_data.unsubs)

