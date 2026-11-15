"""Constants for NINA."""
from __future__ import annotations

DOMAIN = "nina_inventory"
PLATFORMS = ["binary_sensor", "button", "sensor", "switch"]

CONF_TOKEN = "token"
CONF_SSL = "ssl"
CONF_VERIFY_SSL = "verify_ssl"
CONF_INTERVAL = "scan_interval"
CONF_TYPES = "types"
CONF_ONLY_AGENT = "only_agent"
CONF_REMOVE_STALE = "remove_stale"

DEFAULT_PORT = 8080
DEFAULT_INTERVAL = 15

# Fallback labels for older containers (1.0) that do not deliver their type list
TYPES_FALLBACK = {
    "pc": "PC", "laptop": "Laptop", "server": "Server", "vm": "Virtuelle Maschine", "nas": "NAS",
    "netzwerk": "Switch / Access-Point", "router": "Router / Firewall", "drucker": "Drucker",
    "telefon": "Telefon / Smartphone", "tablet": "Tablet", "tv": "TV / Medien", "kamera": "Kamera",
    "iot": "IoT / Smart Home", "konsole": "Spielkonsole", "sonstiges": "Sonstiges", "unbekannt": "Unbekannt",
}

ATTR_COMMAND = "command"
ATTR_VALUE = "value"
ATTR_NETWORK_ID = "network_id"
SERVICE_WAKE = "wake"
SERVICE_COMMAND = "command"
SERVICE_SCAN = "scan"
SERVICE_REFRESH = "refresh"
