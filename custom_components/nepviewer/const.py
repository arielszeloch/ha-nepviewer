"""Constants for the NEPViewer integration."""

DOMAIN = "nepviewer"
MANUFACTURER = "Northern Electric & Power (NEP)"

API_BASE = "https://api.nepviewer.net/"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 120  # s; inverters report to the cloud every ~10 min
MIN_SCAN_INTERVAL = 60
