"""Polls the NINA container."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NinaApi, NinaAuthError, NinaError
from .const import CONF_INTERVAL, CONF_ONLY_AGENT, CONF_TYPES, DEFAULT_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class NinaCoordinator(DataUpdateCoordinator[dict[int, dict]]):
    """data = {device_id: device dict} (already filtered by the entry options)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: NinaApi, instance: str) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(seconds=int(entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL))))
        self.api = api
        self.instance = instance
        self.unsubs: list = []
        self.info: dict = {}

    def included(self, d: dict) -> bool:
        types = self.config_entry.options.get(CONF_TYPES) or []
        if types and not set(types) & set(d.get("typen") or [d.get("typ")]):
            return False
        if self.config_entry.options.get(CONF_ONLY_AGENT) and not d.get("agent"):
            return False
        return True

    async def _async_update_data(self) -> dict[int, dict]:
        try:
            res = await self.api.devices()
        except NinaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NinaError as err:
            raise UpdateFailed(str(err)) from err
        return {d["id"]: d for d in res.get("geraete", []) if self.included(d)}
