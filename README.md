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

---

## Quick Start (Docker — No Hardware Required)

Test the full pipeline on your laptop immediately — no sensors, no RPi, no BACnet gear:

```bash
git clone https://github.com/TheRandyBee/thermvate.git
cd thermvate
docker compose up -d
```

This spins up:
| Service | What it does | Access |
|---------|-------------|-------|
| `mosquitto` | MQTT broker receiving ESP32-style sensor data | `localhost:1883` |
| `influxdb` | Time-series database with `thermvate_data` bucket | `localhost:8086` |
| `grafana` | Pre-loaded dashboards for live sensor visualization | `localhost:3000` (thermvate/thermvate) |
| `orchestrator` | The AI orchestrator with health check API | `localhost:8000/health` |
| `sensor-simulator` | Generates realistic fake sensor data automatically | (background) |

Check it's alive:

```bash
curl localhost:8000/health        # → {"status": "ok"}
curl localhost:8000/status        # → shows MQTT, HAL, InfluxDB states
mosquitto_sub -h localhost -t 'thermvate/#' -v   # → live sensor feed
```

Open **Grafana** at `localhost:3000` (thermvate/thermvate) → Dashboards → **Live Sensors** — temperature, humidity, and CO₂ charts updating in real time.

---

## Quick Start (RPi / Production)

```bash
# One-command RPi setup (Debian-based):
curl -fsSL https://raw.githubusercontent.com/TheRandyBee/thermvate/main/scripts/setup.sh | sudo bash

# Or manually:
git clone https://github.com/TheRandyBee/thermvate.git
cd thermvate
python3 -m venv venv
source venv/bin/activate
pip install -r orchestrator/requirements.txt
cp orchestrator/config.example.yaml /etc/thermvate/config.yaml
# Edit /etc/thermvate/config.yaml with your CWCVT IP, BACnet device, zones
python -m orchestrator.src.main
```

For more detail, see [docs/rpi-setup.md](docs/rpi-setup.md).

---

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

---

## Project Structure

```
thermvate/
├── README.md                       # This file
├── LICENSE                         # MIT
├── Dockerfile                      # Orchestrator container image
├── docker-compose.yml              # Dev stack (5 services)
├── docker-compose.bacnet.yml       # Override for real BACnet hardware
├── .env.example                    # Docker compose environment vars
│
├── scripts/
│   ├── setup.sh                    # One-command RPi install
│   ├── thermvate.service           # systemd unit file
│   └── test_imports.py             # Import sanity check
│
├── docs/
│   ├── architecture.md             # Full 4-layer stack deep-dive
│   ├── bacnet-integration.md       # BAC0 + CWCVT setup + point discovery
│   ├── safety.md                   # Defense-in-depth safety guide
│   └── rpi-setup.md                # RPi quick-start guide
│
├── firmware/
│   └── esp32-sensor.yaml           # ESPHome YAML for sensor nodes
│
├── hardware/
│   └── bill-of-materials.md        # Parts list with costs ($172–$289)
│
├── docker/
│   ├── config.dev.yaml             # Development config (Docker DNS)
│   ├── config.bacnet.yaml          # Production config (host networking)
│   ├── mosquitto/mosquitto.conf    # MQTT broker config
│   ├── influxdb/                   # InfluxDB init scripts
│   └── grafana/                    # Pre-provisioned dashboards
│       ├── provisioning/           # Datasource + dashboard auto-config
│       └── dashboards/live-sensors.json
│
├── orchestrator/
│   ├── config.example.yaml         # Full config template
│   ├── requirements.txt            # Python dependencies
│   └── src/
│       ├── main.py                 # Async lifecycle + graceful shutdown
│       ├── mqtt_bridge.py          # ESPHome MQTT ingestion
│       ├── bacnet_interface.py     # BAC0 read/write over CWCVT
│       ├── hal.py                  # Hardware Abstraction Layer
│       ├── influx_writer.py        # InfluxDB v1/v2 time-series storage
│       ├── safety.py               # Setpoint bounds + staging rate limits
│       ├── health_api.py           # FastAPI health check (Docker probe)
│       ├── models/
│       │   └── thermal.py          # Prophet + GBRT ensemble model
│       └── utils/
│           └── sensor_simulator.py # Fake sensor data generator
│
└── grants/
    └── ai-grant-proposal.md        # $30k AI Grant draft
```

---

## AI Models (All Local, ARM-Capable)

| Model | Purpose | Technique |
|-------|---------|-----------|
| **Thermal Dynamics** | Per-zone thermal lag, solar gain, insulation | Prophet + GBRT ensemble |
| **Occupancy Predictor** | Zone-level presence probability | Lightweight classifier (planned) |
| **Predictive Maintenance** | Compressor cycles, filter life, coil delta-T | Isolation Forest + Rules (planned) |
| **Optimization Engine** | Merges all three + weather for optimal schedule | Constrained optimization (planned) |

All models run on-device (RPi 5 or NUC). No cloud inference required.

---

## Software Stack

| Layer | Choice | Why |
|-------|--------|-----|
| ML Framework | sklearn, Prophet, ONNX Runtime | ARM-compatible, tiny footprint |
| BACnet | [BAC0](https://bac0.readthedocs.io/) (bacpypes) | Mature open-source BACnet stack |
| Modbus | minimalmodbus | Lightweight, battle-tested |
| MQTT | Eclipse Mosquitto + paho-mqtt | Industry IoT transport |
| Firmware | [ESPHome](https://esphome.io/) | Declarative, OTA-updatable |
| Orchestrator | Python asyncio | Simple, debuggable, async I/O |
| Time-Series | InfluxDB v1/v2 | Sensor data + model predictions |
| Dashboards | Grafana (auto-provisioned) | Pre-built live sensor dashboards |
| Health API | FastAPI + uvicorn | Docker health checks, /status, /zones |

---

## BACnet Integration (your CWCVT)

ThermVate communicates with equipment over BACnet/IP via a CWCVT wireless MS/TP bridge:

```python
from orchestrator.src.hal import HardwareAbstractionLayer
hal = HardwareAbstractionLayer({"type": "bacnet", ...})
hal.connect()
supply_temp = hal.read("supply_air_temp")   # → 68.5°F
hal.write("cooling_setpoint", 72.0)          # → True
```

For discovery (finding your equipment's BACnet points):

```python
points = hal.discover_equipment_points()
# → [{"object_id": "analog-input:1", "name": "Supply Air Temp", "value": 68.5}, ...]
```

See [docs/bacnet-integration.md](docs/bacnet-integration.md) for the full guide.

---

## Safety Architecture

Defense-in-depth (4 layers):

| Layer | What | When |
|-------|------|------|
| 0 | Equipment hardware cutouts (high/low pressure, freeze stat) | Always |
| 1 | HAL parameter bounds (configurable min/max setpoints, staging delays) | Every write |
| 2 | Orchestrator trend/sanity checks | Every command |
| 3 | Independent watchdog (future) | Phase 2+ |

The orchestrator enforces: minimum setpoint 60°F, maximum 80°F, 5-minute minimum between stage changes, supply air temp limits (45°F–130°F). See [docs/safety.md](docs/safety.md).

---

## Hardware Requirements (Minimum)

| Component | Cost | Required? |
|-----------|------|-----------|
| RPi 5 (4GB+) or NUC | $60–$200 | ✅ Core compute |
| ESP32 + BME280 sensor | ~$8/room | For zonal temp/humidity |
| CWCVT MSTP WiFi bridge | ~$50 | To talk BACnet over WiFi |
| 4-ch relay board (Sainsmart) | ~$15 | For 24V equipment override |
| MQTT Broker (Mosquitto) | Free | Bundled in setup |

Total: **$172–$289** for a 3-zone system. See [hardware/bill-of-materials.md](hardware/bill-of-materials.md).

---

## Development Roadmap

- ✅ **Phase 0** (Docker Dev Stack): Orchestrator, MQTT, InfluxDB, Grafana, sensor simulator — all running on your laptop
- 🔄 **Phase 1** (MVP): Sensor deployment, data pipeline, passive thermal modeling, advisory UI (in progress)
- ⬜ **Phase 2**: Active setpoint optimization, occupancy prediction, predictive maintenance
- ⬜ **Phase 3**: Multi-zone staging, heat pump optimization, demand response
- ⬜ **Phase 4**: Installer-friendly setup, community equipment profiles, hardening

---

## License

MIT — see [LICENSE](LICENSE).

---

## Grant

A $30k grant proposal for [AI Grant](https://aigrant.org) is in [`grants/ai-grant-proposal.md`](grants/ai-grant-proposal.md). Contributions welcome.

---

*Built for the home. Data stays home.*
