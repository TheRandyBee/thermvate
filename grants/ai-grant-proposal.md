# ThermVate — Open-Source AI HVAC Orchestrator

## Grant Proposal Draft

**Target Program:** AI Grant (aigrant.org) — $5k–$50k open source AI projects  
**Status:** Ready for submission  
**Submitted by:** TheRandyBee (github.com/TheRandyBee)  

---

## Current Project Status (built before grant funding)

This proposal asks for funding to expand and harden a **working MVP** that already exists:

| Deliverable | Status | Detail |
|-------------|--------|--------|
| Orchestrator with async lifecycle | ✅ Done | MQTT ingestion, BAC0 integration, graceful shutdown |
| MQTT sensor bridge | ✅ Done | ESPHome ingestion, auto-parse, alarm routing |
| BACnet interface via CWCVT | ✅ Done | BAC0 read/write, point discovery, equipment profiles |
| Hardware Abstraction Layer | ✅ Done | Unified API over BACnet/Modbus/dry-contact |
| InfluxDB time-series storage | ✅ Done | v1 + v2, write + query |
| Safety enforcer | ✅ Done | Setpoint bounds, staging rate limits, supply air checks |
| Thermal dynamics model | ✅ Done | Prophet + GBRT ensemble, ONNX-capable |
| Docker Compose dev stack | ✅ Done | 5 services, auto-setup, Grafana dashboards |
| Sensor simulator | ✅ Done | Realistic fake data for testing without hardware |
| Health API | ✅ Done | FastAPI, Docker health checks, /status, /zones |
| one-command RPi setup script | ✅ Done | Installs everything: Mosquitto, InfluxDB, venv, systemd |

**GitHub:** [github.com/TheRandyBee/thermvate](https://github.com/TheRandyBee/thermvate) — 35+ files, ~3,000 lines, MIT licensed.

Grant funding would accelerate the remaining phases (optimization engine, occupancy predictor, predictive maintenance, community equipment profiles) and fund the developer stipend.

---

## Summary

ThermVate is an open-source AI layer for residential HVAC that learns a home's thermal dynamics room-by-room and optimizes heating/cooling schedules without cloud dependence or equipment replacement. It speaks BACnet, Modbus, and MQTT — adapting to whatever HVAC infrastructure already exists.

For the homeowner, it means lower energy bills with no behavioral sacrifice. For the grid, it means distributed demand-response at scale. For the open-source ecosystem, it's the first residential AI HVAC platform that industrial BAS engineers would recognize as serious.

---

## Problem

1. **42% of residential energy goes to HVAC** (US EIA), and most homes are conditioned by dumb schedules or cloud-dependent "smart" thermostats that treat the entire house as a single zone.

2. **Industrial BAS intelligence doesn't exist in residential.** Buildings with BACnet (JCI, Siemens, Distech) get staging optimization, economizer free cooling, demand-controlled ventilation, and predictive maintenance — but only commercial buildings. The same technology exists in a residential rooftop unit's BACnet interface, but no residential product uses it.

3. **Cloud-dependent thermostats are fragile.** Nest/Ecobee stop optimizing when the internet goes down. They don't learn per-zone thermal dynamics. They don't integrate with existing BAS infrastructure. And they're proprietary — you can't add features, fix bugs, or connect them to your own ML pipeline.

4. **The AI-home gap.** ML has revolutionized forecasting, time-series modeling, and control — but none of it has reached residential HVAC. The hardware is there (cheap ESP32 sensors, RPi compute, BACnet/Modbus interfaces on most modern equipment). The models are there (Prophet, tiny LSTM, ONNX runtime on ARM). The integration layer isn't.

---

## Solution

ThermVate is an equipment-agnostic AI orchestrator that runs on a Raspberry Pi 5 or NUC, connects to existing HVAC equipment via BACnet, Modbus, dry contact, or smart thermostat API, and operates:

### Core AI Models (all local, ARM-capable)

1. **Thermal Dynamics Model** — learns per-zone thermal lag, solar gain, insulation, and airflow from 7-14 days of passive sensor data. Predicts "if we set back 4°F at 10pm, bedroom hits 66°F by 7am with no morning spike."

2. **Occupancy Predictor** — predicts zone-level occupancy probability from motion sensors, WiFi presence, and patterns. Pre-heats/pre-cools only zones that will be used.

3. **Predictive Maintenance** — tracks compressor cycles, filter pressure drop, evaporator delta-T. Alerts before failures impact comfort.

4. **Optimization Engine** — merges all three + weather forecast to produce a continuously variable setpoint schedule, staging decisions, free-cooling timing, and demand-response participation.

### Why This Is New

| Feature | Nest/Ecobee | ThermVate |
|---------|-------------|-----------|
| Per-zone thermal model | Single zone | Room-by-room |
| Equipment compatibility | Specific HVAC types | BACnet / Modbus / dry contact / any |
| Predictive maintenance | None | Compressor cycles, filter life, coil delta-T |
| Occupancy prediction | Simple motion-based absence | ML patterns + multi-sensor |
| Open source | ❌ Proprietary | ✅ MIT |
| Local-only AI | ❌ Cloud required | ✅ Fully offline |
| BAS integration (BACnet) | ❌ | ✅ Native via BAC0 + CWCVT |

---

## Technical Architecture

```
┌─────────────────────────────────────────────┐
│              AI ORCHESTRATOR                 │
│  (RPi 5 / NUC — local inference)            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │Thermal    │  │Occupancy │  │Predictive│  │
│  │Model      │  │Predictor │  │Maintenance│  │
│  └──────────┘  └──────────┘  └──────────┘  │
│  ┌──────────────────────────────────────┐    │
│  │      Optimization Engine            │    │
│  └──────────────────────────────────────┘    │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│          HARDWARE ABSTRACTION LAYER          │
│  BACnet MSTP ←→ Modbus ←→ Dry Contact ←→    │
│  Smart Thermostat API ←→ MQTT DIY Sensors   │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│          SENSOR / ACTUATOR LAYER             │
│  ESP32 nodes (T/RH/CO2/motion)              │
│  Existing thermostat / BAS controller        │
│  CWCVT (BACnet MS/TP → WiFi bridge)         │
│  Relay board for legacy 24V equipment        │
└─────────────────────────────────────────────┘
```

### Software Stack

| Layer | Choice | Why |
|-------|--------|-----|
| ML inference | sklearn, ONNX Runtime, Prophet | Runs on ARM, tiny footprint |
| BACnet | BAC0 (bacpypes) | Mature open-source BACnet stack |
| Modbus | minimalmodbus | Lightweight, battle-tested |
| MQTT | Mosquitto + paho-mqtt | Industry standard IoT transport |
| Firmware | ESPHome | Declarative, OTA updates |
| Orchestrator | Python asyncio | Simple, debuggable |
| Storage | InfluxDB + SQLite | Time-series + config |
| Dashboard | Home Assistant + Grafana | User-facing control |

---

## Deliverables & Timeline

### Phase 1 (Months 1–2) — $10k
- RPi orchestrator with MQTT sensor ingestion and BACnet integration via BAC0
- ESP32 sensor node firmware (T/RH/CO2) with ESPHome
- Passive data collection pipeline → InfluxDB
- Training pipeline for thermal dynamics model (Prophet baseline)
- Web UI showing real-time sensor data + model predictions (advisory only)
- **Milestone:** System running in a real home, collecting data, thermal model producing ±1.5°F predictions after 14 days

### Phase 2 (Months 3–4) — $10k
- Optimization Engine: active setpoint scheduling with user-override
- Occupancy predictor with motion + WiFi presence
- Basic predictive maintenance alerts
- Home Assistant auto-discovery integration
- Documentation: hardware compatibility, wiring guide, calibration procedure
- **Milestone:** System actively optimizing HVAC schedule, demonstrable energy savings

### Phase 3 (Months 5–6) — $10k
- Heat pump / aux heat staging optimization
- Demand response: time-of-use rate optimization
- Multi-zone damper coordination
- Equipment profiles for 5 most common residential systems
- Installer-friendly setup wizard
- **Milestone:** System suitable for non-technical installation, published compatibility list

### Post-Grant (self-sustaining)
- Community equipment profile contributions
- Pre-trained model sharing (house-to-house transfer)
- Comprehensive safety certification documentation

**Total grant request: $30,000** — 50% engineering effort, 30% hardware and compute, 20% documentation and testing.

---

## Budget Breakdown

| Category | Amount | Details |
|----------|--------|---------|
| Compute hardware | $500 | RPi 5, NVMe hat, case, PSU |
| Sensor deployment | $800 | 10× ESP32 + BME280, enclosures |
| BACnet interface | $200 | CWCVT or compatible MSTP router |
| Relay/actuator hardware | $300 | Dry-contact relays, wire, connectors |
| Cloud GPU (model training) | $1,000 | Lambda/runpod for model development |
| Cloud GPU (CI/CD inference tests) | $500 | Automated regression on real data |
| Developer stipend (6 months) | $22,000 | Part-time engineering effort |
| Hosting & domain | $200 | GitHub, container registry, docs site |
| Contingency | $4,500 | Hardware revisions, unexpected equipment |
| **Total** | **$30,000** | |

---

## Team

**Randy** (github.com/TheRandyBee) — HVAC/BAS controls engineer with JCI experience, residential and commercial commissioning. Domain expertise in BACnet MS/TP, VRF systems, heat pump staging, and building thermal dynamics. Building a home AI lab for independent AI+HVAC research.

---

## Why This Matters (Beyond One House)

- **Scalable impact:** 121 million US homes, each spending ~$1,200/year on HVAC. Even 15% savings × 1M adopters = $18B/year and equivalent CO₂ reduction of 9 million cars.
- **Peak demand reduction:** Coordinated residential HVAC is the largest untapped demand-response resource in the US grid. A 10% peak reduction from AI-optimized HVAC equals dozens of peaker plants.
- **Open-source reproducibility:** Every model, every wiring diagram, every config file is public. No black boxes. Anyone can audit, improve, or adapt it to their specific equipment.
- **Indie AI research value:** This is a rare intersection of domain expertise (BAS controls), practical ML (time series), hardware (IoT sensors), and open-source sustainability — exactly the profile AI Grant funds.

---

## Risks & Mitigation

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Equipment damage from AI setpoints | Low | Safety limits enforced at controller level (hardware backup), AI output is advisory-only in Phase 1 |
| Poor model generalization across houses | Medium | Start simple (Prophet + GBRT), collect training data per-house, pre-trained model as warm start only |
| BACnet incompatibility with specific equipment | Medium | Hardware abstraction layer with Modbus and dry-contact fallback; publish compatible table early |
| Scope creep | Medium | Phased deliverables with hard milestones; no feature beyond Phase 1 counted as grant commitment |
| User adoptability | Medium | Home Assistant integration means users get a UI they may already use; installer wizard planned |

---

## Appendix: Why BACnet Matters (for non-HVAC readers)

Most modern residential HVAC equipment (anything with a communicating thermostat or zoning system) has a BACnet MS/TP port — the same protocol used in commercial buildings. It exposes hundreds of data points: supply air temp, return air temp, compressor stages, outdoor air damper position, leaving water temp, defrost state, error codes, runtime hours. Manufacturers deliberately hide these behind proprietary thermostats — but the BACnet port is right there on the control board.

ThermVate uses the open-source BAC0 Python library to discover and read these points over BACnet/IP via a $50 wireless MS/TP bridge (CWCVT). This means it can talk to equipment from Johnson Controls, Carrier, Trane, Lennox, Daikin, Rheem, and dozens more — all without a single wire splice or proprietary adapter.

---

*Draft updated June 2026. Ready for submission.*
