"""Sensors for NEPViewer: plant totals, per-inverter and per-panel (PV input)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import NepViewerConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import NepInverter, NepModule, NepSite, NepViewerCoordinator


@dataclass(frozen=True, kw_only=True)
class NepSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Any], Any]


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
        key="energy_total", translation_key="energy_total", value_fn=lambda s: s.energy_total, **ENERGY
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
        key="energy_total", translation_key="pv_energy_total", value_fn=lambda m: m.energy_total, **ENERGY
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: NepViewerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[SensorEntity] = []
        for site in coordinator.data.sites.values():
            for desc in SITE_SENSORS:
                uid = f"{site.sid}_{desc.key}"
                if uid not in known:
                    known.add(uid)
                    new.append(NepSiteSensor(coordinator, site.sid, desc, uid))
            for inv in site.inverters.values():
                for desc in INVERTER_SENSORS:
                    uid = f"{inv.sn}_{desc.key}"
                    if uid not in known:
                        known.add(uid)
                        new.append(NepInverterSensor(coordinator, inv.sn, desc, uid))
                for mod in inv.modules.values():
                    for desc in MODULE_SENSORS:
                        uid = f"{inv.sn}_pv{mod.addr}_{desc.key}"
                        if uid not in known:
                            known.add(uid)
                            new.append(NepModuleSensor(coordinator, inv.sn, mod.addr, desc, uid))
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


class NepSiteSensor(_NepEntity):
    def __init__(self, coordinator, sid: str, desc, uid) -> None:
        super().__init__(coordinator, desc, uid)
        self._sid = sid
        site = coordinator.data.sites[sid]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, sid)},
            name=f"NEP {site.name}",
            manufacturer=MANUFACTURER,
            model="PV plant",
        )

    def _source(self) -> NepSite | None:
        return self.coordinator.data.sites.get(self._sid)


class NepInverterSensor(_NepEntity):
    def __init__(self, coordinator, sn: str, desc, uid) -> None:
        super().__init__(coordinator, desc, uid)
        self._sn = sn
        inv = coordinator.data.inverter(sn)
        self._attr_device_info = _inverter_device(inv)

    def _source(self) -> NepInverter | None:
        return self.coordinator.data.inverter(self._sn)


class NepModuleSensor(_NepEntity):
    def __init__(self, coordinator, sn: str, addr: int, desc, uid) -> None:
        super().__init__(coordinator, desc, uid)
        self._sn = sn
        self._addr = addr
        self._attr_translation_placeholders = {"pv": str(addr)}
        self._attr_device_info = _inverter_device(coordinator.data.inverter(sn))

    def _source(self) -> NepModule | None:
        inv = self.coordinator.data.inverter(self._sn)
        return inv.modules.get(self._addr) if inv else None


def _inverter_device(inv: NepInverter) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, inv.sn)},
        name=inv.alias or f"{inv.model or 'NEP'} {inv.sn}",
        manufacturer=MANUFACTURER,
        model=inv.model or None,
        sw_version=inv.version or None,
        serial_number=inv.sn,
        via_device=(DOMAIN, inv.sid),
    )
