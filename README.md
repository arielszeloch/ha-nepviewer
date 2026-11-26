# NEPViewer for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/arielszeloch/ha-nepviewer/actions/workflows/validate.yml/badge.svg)](https://github.com/arielszeloch/ha-nepviewer/actions/workflows/validate.yml)

Custom Home Assistant integration for **NEP microinverters** (e.g. BDM-600, BDM-800) monitored through the **NEPViewer** cloud (`user.nepviewer.com`).

It logs in with your NEPViewer account and **discovers every plant, microinverter and PV input automatically** — no SNs or plant IDs to type in. Inverters added to NEPViewer later show up in HA on their own.

> Unofficial. Not affiliated with Northern Electric & Power. It uses the same cloud API as the NEPViewer web app, which may change without notice.

## Entities

| Device | Sensors |
|---|---|
| **Plant** | Power (W), Energy today, Energy total (sums over all inverters); Energy yesterday, Energy this month, Energy this year, CO2 avoided (kg); disabled by default: Trees equivalent, Car distance equivalent (km), Oil saved (bbl) |
| **Microinverter** | Power, Energy today, Energy total, Temperature, AC voltage, AC frequency, DC voltage, DC current, Status, Alert, Last report |
| **Each PV input (panel)** | PV1/PV2… power, energy today, energy total |

Energy sensors use `state_class: total_increasing`, so they work in the **Energy dashboard** (use *Energy total* of the plant or of each inverter). Lifetime totals never go backwards: a lower or missing reading from the cloud keeps the last valid value, so long-term statistics get no fake meter resets. *Energy this month / this year* use `state_class: total` with a `last_reset` at the start of the period.

**PV input energy total** is counted by Home Assistant from that input's *energy today*, starting when the sensor was created (or when you updated to 0.2.1). The NEPViewer cloud has no real lifetime counter per PV input: its per-input total is just the inverter total split by each input's share of today's energy, so it jumps up and down. Days when Home Assistant is not running are not counted; the inverter and plant totals are always the cloud's own counters.

Temperature / AC / DC readings come from the inverter's latest report of the current day; they are `unknown` while an inverter hasn't reported today (night, offline).

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/arielszeloch/ha-nepviewer`, category **Integration**.
2. Search for **NEPViewer** in HACS and download it.
3. Restart Home Assistant.

### Manual

Copy `custom_components/nepviewer` into your HA `config/custom_components/` folder and restart.

The integration ships its own icon and logo (`custom_components/nepviewer/brand/`); they are shown in Home Assistant 2026.3 or newer.

## Configuration

**Settings → Devices & services → Add integration → NEPViewer**, then enter your NEPViewer e-mail and password.

Options: polling interval (default 120 s, min 60 s). Inverters upload to the cloud roughly every 10 minutes, so polling faster than ~60 s gains nothing.

If the password changes, HA will ask you to re-authenticate.

### Tip: use a dedicated account

You can use your regular NEPViewer login, but NEPViewer allows only one active session per account. Logging in with the same credentials in the mobile app (or on the website) will sign the integration out, and the integration will in turn sign the app out when it logs back in.

**Recommended workaround:** create a separate NEPViewer account dedicated to Home Assistant and share your PV plant with it. Then use that account's credentials in the integration, and keep your own account for the app.

## How it works

Per poll: one request lists plants (with each inverter's lifetime total), one request per plant returns all inverters with per-input power/energy, and one request per plant returns the plant statistics (yesterday / month / year, environmental benefits). Detailed readings (temperature, voltages) are fetched per inverter only when that inverter has sent a new report.

## Languages

English, Polish, German, Portuguese (Brazil).

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

## Development

Parsing helpers have unit tests that run without Home Assistant:

```sh
python -m unittest discover -s tests -v
```

## License

MIT. The NEP name and logo are trademarks of Northern Electric & Power Co., Ltd. and are used only to identify the devices this integration works with.
