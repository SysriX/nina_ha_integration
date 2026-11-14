"""Base entity, device info and dynamic entity creation."""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, TYPES
from .coordinator import NetInventoryCoordinator

_UML = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower().translate(_UML)).strip("_")
    return s or "x"


def device_identifier(coordinator: NetInventoryCoordinator, device_id: int) -> tuple[str, str]:
    return (DOMAIN, f"{coordinator.instance}_{device_id}")


class NetInventoryEntity(CoordinatorEntity[NetInventoryCoordinator]):
    """An entity that belongs to one NetInventory device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NetInventoryCoordinator, device_id: int, key: str, platform: str,
                 suffix: str | None = None) -> None:
        super().__init__(coordinator)
        self.device_id = device_id
        self.key = key
        self._attr_unique_id = f"{coordinator.instance}_{device_id}_{key}"
        d = self.dev
        # entity_id following the house naming scheme: <room>_net_<device>_<function>
        self.entity_id = f"{platform}.{slug(d.get('raum') or 'haus')}_net_{slug(d.get('name'))}_{slug(suffix or key)}"
        host = coordinator.api.base
        self._attr_device_info = DeviceInfo(
            identifiers={device_identifier(coordinator, device_id)},
            # no MAC connection on purpose: it would merge with (and rename) devices of other integrations
            name=d.get("name"),
            manufacturer=d.get("hersteller") or None,
            model=d.get("modell") or TYPES.get(d.get("typ"), d.get("typ")),
            sw_version=(d.get("agent") or {}).get("version") or None,
            hw_version=d.get("betriebssystem") or None,
            serial_number=d.get("seriennummer") or None,
            suggested_area=d.get("standort") or None,
            configuration_url=f"{host}/#geraet?id={device_id}",
        )

    @property
    def dev(self) -> dict:
        return self.coordinator.data.get(self.device_id) or {}

    @property
    def agent(self) -> dict:
        return self.dev.get("agent") or {}

    @property
    def available(self) -> bool:
        return super().available and self.device_id in (self.coordinator.data or {})


def add_dynamic(coordinator: NetInventoryCoordinator, async_add_entities,
                factory: Callable[[int, dict], Iterable[Entity]], unsub_list: list) -> None:
    """Create entities for all devices now and whenever new devices/sensors appear."""
    known: set[str] = set()

    @callback
    def _check() -> None:
        new = []
        for dev_id, dev in (coordinator.data or {}).items():
            for ent in factory(dev_id, dev):
                if ent.unique_id not in known:
                    known.add(ent.unique_id)
                    new.append(ent)
        if new:
            async_add_entities(new)

    _check()
    unsub_list.append(coordinator.async_add_listener(_check))
