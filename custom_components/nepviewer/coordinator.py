"""Data coordinator for NEPViewer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import NepViewerApi, NepViewerAuthError, NepViewerError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_kwh(value: Any, unit: Any) -> float | None:
    """Normalise an energy value to kWh (API switches units for big numbers)."""
    v = _num(value)
    if v is None:
        return None
    u = str(unit or "kWh").strip().lower()
    if u == "mwh":
        return v * 1000
    if u == "gwh":
        return v * 1_000_000
    if u == "wh":
        return v / 1000
    return v


def to_w(value: Any, unit: Any) -> float | None:
    v = _num(value)
    if v is None:
        return None
    u = str(unit or "W").strip().lower()
    if u == "kw":
        return v * 1000
    if u == "mw":
        return v * 1_000_000
    return v


def _ts(value: Any, tz: tzinfo) -> datetime | None:
    """Convert NEP's timestamp to an aware datetime.

    NEP encodes the plant's *local* wall-clock time as if it were UTC
    (e.g. a report at 17:12 Warsaw time comes back as 17:12 UTC), so the
    epoch is read as a naive time and then placed in the plant's timezone.
    """
    v = _num(value)
    if not v:
        return None
    naive = datetime.fromtimestamp(v, tz=timezone.utc).replace(tzinfo=None)
    return naive.replace(tzinfo=tz)


def site_timezone(raw_site: dict[str, Any]) -> tzinfo:
    """Plant timezone from the API if present, otherwise HA's timezone."""
    name = raw_site.get("timezone") or raw_site.get("timeZone")
    if isinstance(name, str) and name:
        if (tz := dt_util.get_time_zone(name)) is not None:
            return tz
    return dt_util.get_default_time_zone()


@dataclass
class NepModule:
    """One PV input (panel) of a microinverter."""

    sn: str
    addr: int
    power: float | None
    energy_today: float | None
    energy_total: float | None


@dataclass
class NepInverter:
    sn: str
    sid: str
    model: str
    version: str
    alias: str
    online: bool
    status: str
    alert_code: str
    alert: str
    last_update: datetime | None
    modules: dict[int, NepModule] = field(default_factory=dict)
    history: dict[str, Any] | None = None  # latest point of today's history

    @property
    def power(self) -> float:
        return sum(m.power or 0 for m in self.modules.values())

    @property
    def energy_today(self) -> float:
        return round(sum(m.energy_today or 0 for m in self.modules.values()), 3)

    @property
    def energy_total(self) -> float:
        return round(sum(m.energy_total or 0 for m in self.modules.values()), 3)


@dataclass
class NepSite:
    sid: str
    name: str
    inverters: dict[str, NepInverter] = field(default_factory=dict)

    @property
    def power(self) -> float:
        return sum(i.power for i in self.inverters.values())

    @property
    def energy_today(self) -> float:
        return round(sum(i.energy_today for i in self.inverters.values()), 3)

    @property
    def energy_total(self) -> float:
        return round(sum(i.energy_total for i in self.inverters.values()), 3)


@dataclass
class NepData:
    sites: dict[str, NepSite] = field(default_factory=dict)

    def inverter(self, sn: str) -> NepInverter | None:
        for site in self.sites.values():
            if sn in site.inverters:
                return site.inverters[sn]
        return None


def parse_inverter(sid: str, raw: dict[str, Any], tz: tzinfo) -> NepInverter:
    sn = str(raw.get("sn", "")).upper()
    inv = NepInverter(
        sn=sn,
        sid=sid,
        model=raw.get("modelName") or "",
        version=raw.get("version") or "",
        alias=raw.get("alias") or "",
        online=raw.get("status") == 0,
        status=raw.get("statusTitle") or "",
        alert_code=raw.get("alertCode") or "",
        alert=raw.get("alertTitle") or "",
        last_update=None,
    )
    latest = 0.0
    for m in raw.get("modules") or []:
        addr = int(m.get("addr") or 0)
        inv.modules[addr] = NepModule(
            sn=sn,
            addr=addr,
            power=to_w(m.get("now"), m.get("nowUnit")),
            energy_today=to_kwh(m.get("todayPower"), m.get("todayPowerUnit")),
            energy_total=to_kwh(m.get("totalPower"), m.get("totalPowerUnit")),
        )
        latest = max(latest, _num(m.get("lastUpdateTime")) or 0)
    inv.last_update = _ts(latest, tz)
    return inv


class NepViewerCoordinator(DataUpdateCoordinator[NepData]):
    """Polls all plants / inverters / panels on the account."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: NepViewerApi) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        # sn -> (last_update timestamp the history was fetched for, latest point)
        self._history_cache: dict[str, tuple[datetime, dict[str, Any] | None]] = {}

    async def _async_update_data(self) -> NepData:
        try:
            raw_sites = await self.api.get_sites()
            data = NepData()
            for rs in raw_sites:
                sid = rs.get("sid")
                if not sid:
                    continue
                site = NepSite(sid=sid, name=rs.get("siteName") or sid)
                tz = site_timezone(rs)
                for raw_inv in await self.api.get_site_modules(sid):
                    inv = parse_inverter(sid, raw_inv, tz)
                    if inv.sn:
                        site.inverters[inv.sn] = inv
                data.sites[sid] = site
        except NepViewerAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NepViewerError as err:
            raise UpdateFailed(str(err)) from err

        today = dt_util.now().date()
        for site in data.sites.values():
            for inv in site.inverters.values():
                inv.history = await self._latest_history(inv, today)
        return data

    async def _latest_history(self, inv: NepInverter, today) -> dict[str, Any] | None:
        """Latest detailed reading (temp, AC V, Hz, DC V/A) — only if from today.

        Fetched only when the cloud has a newer report than last time,
        so idle/offline inverters cost no extra requests.
        """
        if inv.last_update is None or dt_util.as_local(inv.last_update).date() != today:
            self._history_cache.pop(inv.sn, None)
            return None
        cached = self._history_cache.get(inv.sn)
        if cached and cached[0] == inv.last_update:
            return cached[1]
        try:
            points = await self.api.get_device_history(inv.sid, inv.sn, today.isoformat())
        except NepViewerError as err:
            _LOGGER.debug("History for %s failed: %s", inv.sn, err)
            return cached[1] if cached else None
        point = points[-1] if points else None
        self._history_cache[inv.sn] = (inv.last_update, point)
        return point
