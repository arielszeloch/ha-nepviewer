"""Pure parsing helpers for NEPViewer API values (no Home Assistant imports).

Kept separate so they can be unit tested without Home Assistant installed.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


def num(value: Any) -> float | None:
    """Float from an API value (numbers often come as strings), or None."""
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def to_kwh(value: Any, unit: Any) -> float | None:
    """Normalise an energy value to kWh (the API switches units for big numbers)."""
    v = num(value)
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
    """Normalise a power value to W."""
    v = num(value)
    if v is None:
        return None
    u = str(unit or "W").strip().lower()
    if u == "kw":
        return v * 1000
    if u == "mw":
        return v * 1_000_000
    return v


def period_energy(production: dict[str, Any], period: str) -> float | None:
    """Energy of one period from site/overview `statisticsProduction`, in kWh.

    `yesterday` comes in Wh with an empty unit (e.g. "200" + "" = 0.2 kWh,
    which is what the NEPViewer app shows); other periods carry their unit.
    """
    value = production.get(period)
    unit = production.get(f"{period}Unit")
    if period == "yesterday" and not str(unit or "").strip():
        unit = "Wh"
    return to_kwh(value, unit)


def _scaled(value: Any, unit: Any) -> float | None:
    """Values like "4.46" + "km(*1000)" -> 4460."""
    v = num(value)
    if v is None:
        return None
    if "(*1000)" in str(unit or "").replace(" ", ""):
        return v * 1000
    return v


@dataclass
class SiteOverview:
    """Plant-level statistics from v2/site/overview."""

    energy_yesterday: float | None = None
    energy_month: float | None = None
    energy_year: float | None = None
    co2_kg: float | None = None
    trees: float | None = None
    car_km: float | None = None
    oil_bbl: float | None = None


def parse_overview(data: dict[str, Any] | None) -> SiteOverview | None:
    """Parse a v2/site/overview response; None if it has no production data."""
    if not isinstance(data, dict):
        return None
    production = data.get("statisticsProduction")
    if not isinstance(production, dict):
        return None
    benefit = data.get("benefit") if isinstance(data.get("benefit"), dict) else {}

    co2 = _scaled(benefit.get("co2"), benefit.get("co2Unit"))
    co2_unit = str(benefit.get("co2Unit") or "kg").strip().lower()
    if co2 is not None and co2_unit.startswith("t"):
        co2 *= 1000

    return SiteOverview(
        energy_yesterday=period_energy(production, "yesterday"),
        energy_month=period_energy(production, "month"),
        energy_year=period_energy(production, "year"),
        co2_kg=co2,
        trees=_scaled(benefit.get("tree"), benefit.get("treeUnit")),
        car_km=_scaled(benefit.get("car"), benefit.get("carUnit")),
        oil_bbl=_scaled(benefit.get("oil"), benefit.get("oilUnit")),
    )


@dataclass
class DailyEnergyCounter:
    """Lifetime energy of one PV input, accumulated from its daily energy.

    The cloud has no real lifetime counter per PV input: its per-module
    `totalPower` is the inverter total split by each input's share of
    today's energy, so it jumps up and down. This counter adds up the
    increments of the input's `todayPower` instead.

    `day` is the date the daily value belongs to (the input's last report);
    a new day starts counting from 0. Decreases within a day are ignored.
    Days with no update at all (e.g. HA switched off) are not counted.
    """

    total: float = 0.0
    day: str | None = None  # ISO date of `seen`
    seen: float = 0.0  # last daily value counted for `day`

    def update(self, day: str | None, today: float | None) -> bool:
        """Count a new daily reading; True if the total changed."""
        if day is None or today is None or today < 0:
            return False
        if day != self.day:
            if self.day is not None and day < self.day:
                return False  # stale report from an older day
            self.day, self.seen = day, 0.0
        if today <= self.seen:
            return False
        self.total = round(self.total + today - self.seen, 4)
        self.seen = today
        return True

    def as_dict(self) -> dict[str, Any]:
        return {"total": self.total, "day": self.day, "seen": self.seen}

    @classmethod
    def from_dict(cls, data: Any) -> DailyEnergyCounter | None:
        if not isinstance(data, dict):
            return None
        total, seen = num(data.get("total")), num(data.get("seen"))
        day = data.get("day")
        if total is None or seen is None or not (day is None or isinstance(day, str)):
            return None
        return cls(total=total, day=day, seen=seen)
