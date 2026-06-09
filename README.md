# ThermVate — Open-Source AI HVAC Orchestrator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Pre-Alpha](https://img.shields.io/badge/Status-Pre--Alpha-red)]()

**ThermVate** is an equipment-agnostic AI layer for residential HVAC. It learns your home's thermal dynamics room-by-room, predicts occupancy, and optimizes heating/cooling schedules — without cloud dependence, vendor lock-in, or replacing your existing equipment.

> *The AI adapts to the building. Not the other way around.*

---

## Why ThermVate?

- **42% of residential energy** goes to HVAC — and most homes run on dumb schedules or cloud-dependent "smart" thermostats that treat the whole house as one zone
- **Industrial BAS intelligence exists** (JCI, Siemens, Distech) but never made it to residential — ThermVate bridges that gap
- **Your equipment already has the data** — BACnet MS/TP ports, Modbus RTU, or simple 24V thermostat wires — ThermVate speaks whatever your system speaks
- **Fully open source** — MIT licensed, no black boxes, you control your data

## Quick Start

```bash
# Prerequisites: RPi 5 (4GB+) or NUC with Python 3.11+
git clone https://github.com/<your-org>/thermvate.git
cd thermvate
pip install -r orchestrator/requirements.txt

# Configure your equipment interface in config.yaml
# Deploy ESP32 sensor nodes (see firmware/)
# Start the orchestrator
python orchestrator/src/main.py
```

## Architecture (4-Layer Stack)

```
┌─────────────────────────────────────────────┐
│              AI ORCHESTRATOR                 │
│  (RPi 5 / NUC — local inference, no cloud)  │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │Thermal    │  │Occupancy │  │Predictive│  │
│  │Model      │  │Predictor │  │Maintenance│  │
│  └──────────┘  └──────────┘  └──────────┘  │
│  ┌──────────────────────────────────────┐    │
│  │      Optimization Engine            │    │
│  │  (setpoint scheduling, staging,     │    │
│  │   economizer blending, setback)     │    │
│  └──────────────────────────────────────┘    │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│          HARDWARE ABSTRACTION LAYER          │
│                                              │
│  BACnet MSTP ←→ Modbus ←→ Dry Contact ←→    │
│  Smart Thermostat API ←→ MQTT DIY Sensors   │
│                                              │
│  Every piece is optional — start with what   │
│  your equipment already speaks.              │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│          SENSOR / ACTUATOR LAYER             │
│                                              │
│  • ESP32 sensor nodes (T, RH, CO2, motion)  │
│  • Existing thermostat / BAS controller      │
│  • CWCVT wireless MSTP for BACnet            │
│  • Relay board for legacy 24V equipment      │
│  • Optional: smart vents, zone dampers       │
└─────────────────────────────────────────────┘
```

## AI Models (All Local, ARM-Capable)

| Model | Purpose | Technique |
|-------|---------|-----------|
| **Thermal Dynamics** | Per-zone thermal lag, solar gain, insulation | LSTM / Gradient Boosted Trees |
| **Occupancy Predictor** | Zone-level presence probability | Lightweight classifier |
| **Predictive Maintenance** | Compressor cycles, filter life, coil delta-T | Isolation Forest + Rules |
| **Optimization Engine** | Merges all three + weather for optimal schedule | Constrained optimization |

All models run on-device (RPi 5 or NUC). No cloud inference required.

## Software Stack

| Layer | Choice | Why |
|-------|--------|-----|
| ML Framework | sklearn, ONNX Runtime, Prophet | ARM-compatible, tiny footprint |
| BACnet | [BAC0](https://bac0.readthedocs.io/) (bacpypes) | Mature open-source BACnet stack |
| Modbus | minimalmodbus | Lightweight, battle-tested |
| MQTT | Mosquitto + paho-mqtt | Industry IoT transport |
| Firmware | [ESPHome](https://esphome.io/) | Declarative, OTA-updatable |
| Orchestrator | Python asyncio | Simple, debuggable, async I/O |
| Time-Series | InfluxDB | Sensor data storage |
| UI | Home Assistant + Grafana | Self-hosted dashboards |

## Hardware (Minimum Viable)

| Component | Cost | Required? |
|-----------|------|-----------|
| RPi 5 (4GB+) or NUC | $60–$200 | ✅ Core compute |
| ESP32 + BME280 sensor | ~$8/room | For zonal temp/humidity |
| CWCVT MSTP WiFi bridge | ~$50 | To talk BACnet over WiFi |
| 4-ch relay board | ~$15 | For 24V equipment override |
| MQTT Broker (Mosquitto) | Free | Glue layer |

**Start with 2–3 sensor nodes and whatever interface your equipment already speaks.**

## Development Roadmap

- **Phase 1** (MVP): Sensor deployment, data pipeline, passive thermal modeling, advisory UI
- **Phase 2**: Active setpoint optimization, occupancy prediction, predictive maintenance
- **Phase 3**: Multi-zone staging, heat pump optimization, demand response
- **Phase 4**: Installer-friendly setup, community equipment profiles, hardening

## Project Status

⚠️ **Pre-Alpha.** Core architecture defined, sensor firmware ready, BACnet integration designed. MVP development in progress.

## Contributing

See [CONTRIBUTING.md](docs/contributing.md) (coming soon). We welcome:
- Equipment compatibility reports (especially non-standard systems)
- BACnet point maps for specific models
- Sensor deployment designs
- ML model improvements

## License

MIT — see [LICENSE](LICENSE).

## Supporting

If ThermVate saves you money or sparks ideas, [coming soon: sponsorship / grant links]

---

*Built for the home. Data stays home.*
