# NEPViewer for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/arielszeloch/ha-nepviewer/actions/workflows/validate.yml/badge.svg)](https://github.com/arielszeloch/ha-nepviewer/actions/workflows/validate.yml)

Custom Home Assistant integration for **NEP microinverters** (e.g. BDM-600, BDM-800) monitored through the **NEPViewer** cloud (`user.nepviewer.com`).

It logs in with your NEPViewer account and **discovers every plant, microinverter and PV input automatically** — no SNs or plant IDs to type in. Inverters added to NEPViewer later show up in HA on their own.

> Unofficial. Not affiliated with Northern Electric & Power. It uses the same cloud API as the NEPViewer web app, which may change without notice.

## Entities

| Device | Sensors |
|---|---|
| **Plant** | Power (W), Energy today (kWh), Energy total (kWh) — sums over all inverters |
| **Microinverter** | Power, Energy today, Energy total, Temperature, AC voltage, AC frequency, DC voltage, DC current, Status, Alert, Last report |
| **Each PV input (panel)** | PV1/PV2… power, energy today, energy total |

Energy sensors use `state_class: total_increasing`, so they work in the **Energy dashboard** (use *Energy total* of the plant or of each inverter).

Temperature / AC / DC readings come from the inverter's latest report of the current day; they are `unknown` while an inverter hasn't reported today (night, offline).

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/arielszeloch/ha-nepviewer`, category **Integration**.
2. Search for **NEPViewer** in HACS and download it.
3. Restart Home Assistant.

### Manual

Copy `custom_components/nepviewer` into your HA `config/custom_components/` folder and restart.

## Configuration

**Settings → Devices & services → Add integration → NEPViewer**, then enter your NEPViewer e-mail and password.

Options: polling interval (default 120 s, min 60 s). Inverters upload to the cloud roughly every 10 minutes, so polling faster than ~60 s gains nothing.

If the password changes, HA will ask you to re-authenticate.

### Tip: use a dedicated account

You can use your regular NEPViewer login, but NEPViewer allows only one active session per account. Logging in with the same credentials in the mobile app (or on the website) will sign the integration out, and the integration will in turn sign the app out when it logs back in.

**Recommended workaround:** create a separate NEPViewer account dedicated to Home Assistant and share your PV plant with it. Then use that account's credentials in the integration, and keep your own account for the app.

## How it works

Per poll: one request lists plants, one request per plant returns all inverters with per-input power/energy. Detailed readings (temperature, voltages) are fetched per inverter only when that inverter has sent a new report.

## Troubleshooting

Enable debug logging:

```yaml
logger:
  logs:
    custom_components.nepviewer: debug
```

---

### PL — skrót

Integracja HA dla mikroinwerterów NEP przez chmurę NEPViewer. Instalacja przez HACS (repozytorium niestandardowe → Integracja), potem *Dodaj integrację → NEPViewer* i logowanie kontem NEPViewer. Wszystkie instalacje, mikroinwertery i wejścia PV wykrywane są automatycznie.

## License

MIT
# NEPViewer for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/arielszeloch/ha-nepviewer/actions/workflows/validate.yml/badge.svg)](https://github.com/arielszeloch/ha-nepviewer/actions/workflows/validate.yml)

Custom Home Assistant integration for **NEP microinverters** (e.g. BDM-600, BDM-800) monitored through the **NEPViewer** cloud (`user.nepviewer.com`).

It logs in with your NEPViewer account and **discovers every plant, microinverter and PV input automatically** — no SNs or plant IDs to type in. Inverters added to NEPViewer later show up in HA on their own.

> Unofficial. Not affiliated with Northern Electric & Power. It uses the same cloud API as the NEPViewer web app, which may change without notice.

## Entities

| Device | Sensors |
|---|---|
| **Plant** | Power (W), Energy today (kWh), Energy total (kWh) — sums over all inverters |
| **Microinverter** | Power, Energy today, Energy total, Temperature, AC voltage, AC frequency, DC voltage, DC current, Status, Alert, Last report |
| **Each PV input (panel)** | PV1/PV2… power, energy today, energy total |

Energy sensors use `state_class: total_increasing`, so they work in the **Energy dashboard** (use *Energy total* of the plant or of each inverter).

Temperature / AC / DC readings come from the inverter's latest report of the current day; they are `unknown` while an inverter hasn't reported today (night, offline).

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/arielszeloch/ha-nepviewer`, category **Integration**.
2. Search for **NEPViewer** in HACS and download it.
3. Restart Home Assistant.

### Manual

Copy `custom_components/nepviewer` into your HA `config/custom_components/` folder and restart.

## Configuration

**Settings → Devices & services → Add integration → NEPViewer**, then enter your NEPViewer e-mail and password.

Options: polling interval (default 120 s, min 60 s). Inverters upload to the cloud roughly every 10 minutes, so polling faster than ~60 s gains nothing.

If the password changes, HA will ask you to re-authenticate.

## How it works

Per poll: one request lists plants, one request per plant returns all inverters with per-input power/energy. Detailed readings (temperature, voltages) are fetched per inverter only when that inverter has sent a new report.

## Troubleshooting

Enable debug logging:

```yaml
logger:
  logs:
    custom_components.nepviewer: debug
```

---

### PL — skrót

Integracja HA dla mikroinwerterów NEP przez chmurę NEPViewer. Instalacja przez HACS (repozytorium niestandardowe → Integracja), potem *Dodaj integrację → NEPViewer* i logowanie kontem NEPViewer. Wszystkie instalacje, mikroinwertery i wejścia PV wykrywane są automatycznie.

## License

MIT
