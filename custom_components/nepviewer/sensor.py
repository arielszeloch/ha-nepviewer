"""Sensors for NEPViewer: plant totals, per-inverter and per-panel (PV input)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import inspect
import logging
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NepViewerConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import NepInverter, NepModule, NepSite, NepViewerCoordinator

_LOGGER = logging.getLogger(__name__)

# HA 2026.8+ links child devices by registry id (`via_device_id`); the
# identifier-tuple `via_device` is deprecated and removed in 2027.8.
_HAS_VIA_DEVICE_ID = (
    "via_device_id" in inspect.signature(dr.DeviceRegistry.async_get_or_create).parameters
)


@dataclass(frozen=True, kw_only=True)
class NepSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Any], Any]
    # Lifetime counter: never allowed to go backwards (see NepTotalMixin).
    monotonic: bool = False


POWER = dict(
    native_unit_of_measurement=UnitOfPower.WATT,
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
)
ENERGY = dict(
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    suggested_display_precision=2,
)


def _hist(key: str) -> Callable[[NepInverter], Any]:
    return lambda inv: (inv.history or {}).get(key)


SITE_SENSORS: tuple[NepSensorDescription, ...] = (
    NepSensorDescription(key="power", translation_key="power", value_fn=lambda s: s.power, **POWER),
    NepSensorDescription(
        key="energy_today", translation_key="energy_today", value_fn=lambda s: s.energy_today, **ENERGY
    ),
    NepSensorDescription(
        key="energy_total", translation_key="energy_total", value_fn=lambda s: s.energy_total,
        monotonic=True, **ENERGY
    ),
)

INVERTER_SENSORS: tuple[NepSensorDescription, ...] = (
    *SITE_SENSORS,
    NepSensorDescription(
        key="status", translation_key="status", value_fn=lambda i: i.status,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    NepSensorDescription(
        key="alert", translation_key="alert", value_fn=lambda i: i.alert,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    NepSensorDescription(
        key="last_update", translation_key="last_update", value_fn=lambda i: i.last_update,
        device_class=SensorDeviceClass.TIMESTAMP, entity_category=EntityCategory.DIAGNOSTIC,
    ),
    NepSensorDescription(
        key="temperature", translation_key="temperature", value_fn=_hist("temperature"),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT,
    ),
    NepSensorDescription(
        key="ac_voltage", translation_key="ac_voltage", value_fn=_hist("acVoltage"),
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT,
    ),
    NepSensorDescription(
        key="ac_frequency", translation_key="ac_frequency", value_fn=_hist("frequency"),
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY, state_class=SensorStateClass.MEASUREMENT,
    ),
    NepSensorDescription(
        key="dc_voltage", translation_key="dc_voltage", value_fn=_hist("voltage"),
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT,
    ),
    NepSensorDescription(
        key="dc_current", translation_key="dc_current", value_fn=_hist("current"),
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT,
    ),
)

MODULE_SENSORS: tuple[NepSensorDescription, ...] = (
    NepSensorDescription(key="power", translation_key="pv_power", value_fn=lambda m: m.power, **POWER),
    NepSensorDescription(
        key="energy_today", translation_key="pv_energy_today", value_fn=lambda m: m.energy_today, **ENERGY
    ),
    NepSensorDescription(
        key="energy_total", translation_key="pv_energy_total", value_fn=lambda m: m.energy_total,
        monotonic=True, **ENERGY
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: NepViewerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()
    device_reg = dr.async_get(hass)

    @callback
    def _add_new() -> None:
        new: list[SensorEntity] = []
        for site in coordinator.data.sites.values():
            # Register the plant device first so inverters can link to its id.
            site_device = device_reg.async_get_or_create(
                config_entry_id=entry.entry_id, **_site_device(site)
            )
            for desc in SITE_SENSORS:
                uid = f"{site.sid}_{desc.key}"
                if uid not in known:
                    known.add(uid)
                    new.append(_cls(NepSiteSensor, desc)(coordinator, site.sid, desc, uid))
            for inv in site.inverters.values():
                inv_device = _inverter_device(inv, site_device.id)
                for desc in INVERTER_SENSORS:
                    uid = f"{inv.sn}_{desc.key}"
                    if uid not in known:
                        known.add(uid)
                        new.append(
                            _cls(NepInverterSensor, desc)(coordinator, inv.sn, desc, uid, inv_device)
                        )
                for mod in inv.modules.values():
                    for desc in MODULE_SENSORS:
                        uid = f"{inv.sn}_pv{mod.addr}_{desc.key}"
                        if uid not in known:
                            known.add(uid)
                            new.append(
                                _cls(NepModuleSensor, desc)(
                                    coordinator, inv.sn, mod.addr, desc, uid, inv_device
                                )
                            )
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class _NepEntity(CoordinatorEntity[NepViewerCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: NepSensorDescription

    def __init__(self, coordinator: NepViewerCoordinator, desc: NepSensorDescription, uid: str) -> None:
        super().__init__(coordinator)
        self.entity_description = desc
        self._attr_unique_id = uid

    def _source(self) -> Any:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        return super().available and self._source() is not None

    @property
    def native_value(self) -> Any:
        src = self._source()
        return None if src is None else self.entity_description.value_fn(src)


class NepTotalMixin(RestoreSensor):
    """Lifetime energy counter that never goes backwards.

    The cloud sometimes returns a lower total (PV input counters lag, or are
    missing/0 outside production hours). With state_class total_increasing
    HA would record any big drop as a meter reset and add the whole lifetime
    again to the statistics, so a lower reading keeps the last good value.
    The last value is restored across restarts.
    """

    _last_total: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            try:
                self._last_total = float(last.native_value)
            except (TypeError, ValueError):
                self._last_total = None

    @property
    def native_value(self) -> Any:
        value = super().native_value
        if value is None:
            # No usable reading this cycle: a lifetime counter keeps its value.
            return self._last_total
        if self._last_total is not None and value < self._last_total:
            _LOGGER.debug(
                "%s: ignoring lower total %s (keeping %s)", self.entity_id, value, self._last_total
            )
            return self._last_total
        self._last_total = value
        return value


_TOTAL_CLASSES: dict[type, type] = {}


def _cls(base: type, desc: NepSensorDescription) -> type:
    """Entity class for a description: monotonic totals get NepTotalMixin."""
    if not desc.monotonic:
        return base
    if base not in _TOTAL_CLASSES:
        _TOTAL_CLASSES[base] = type(f"{base.__name__}Total", (NepTotalMixin, base), {})
    return _TOTAL_CLASSES[base]


def _site_device(site: NepSite) -> dict[str, Any]:
    return dict(
        identifiers={(DOMAIN, site.sid)},
        name=f"NEP {site.name}",
        manufacturer=MANUFACTURER,
        model="PV plant",
    )


class NepSiteSensor(_NepEntity):
    def __init__(self, coordinator, sid: str, desc, uid) -> None:
        super().__init__(coordinator, desc, uid)
        self._sid = sid
        self._attr_device_info = DeviceInfo(**_site_device(coordinator.data.sites[sid]))

    def _source(self) -> NepSite | None:
        return self.coordinator.data.sites.get(self._sid)


class NepInverterSensor(_NepEntity):
    def __init__(self, coordinator, sn: str, desc, uid, device_info: DeviceInfo) -> None:
        super().__init__(coordinator, desc, uid)
        self._sn = sn
        self._attr_device_info = device_info

    def _source(self) -> NepInverter | None:
        return self.coordinator.data.inverter(self._sn)


class NepModuleSensor(_NepEntity):
    def __init__(self, coordinator, sn: str, addr: int, desc, uid, device_info: DeviceInfo) -> None:
        super().__init__(coordinator, desc, uid)
        self._sn = sn
        self._addr = addr
        self._attr_translation_placeholders = {"pv": str(addr)}
        self._attr_device_info = device_info

    def _source(self) -> NepModule | None:
        inv = self.coordinator.data.inverter(self._sn)
        return inv.modules.get(self._addr) if inv else None


def _inverter_device(inv: NepInverter, site_device_id: str) -> DeviceInfo:
    info: dict[str, Any] = dict(
        identifiers={(DOMAIN, inv.sn)},
        name=inv.alias or f"{inv.model or 'NEP'} {inv.sn}",
        manufacturer=MANUFACTURER,
        model=inv.model or None,
        sw_version=inv.version or None,
        serial_number=inv.sn,
    )
    if _HAS_VIA_DEVICE_ID:
        info["via_device_id"] = site_device_id
    else:
        info["via_device"] = (DOMAIN, inv.sid)
    return DeviceInfo(**info)
