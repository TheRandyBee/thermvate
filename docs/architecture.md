# ThermVate Architecture

## Overview

ThermVate uses a **four-layer architecture** that cleanly separates concerns: Sensors → Hardware Abstraction → AI Orchestration → User Interface. Each layer has a well-defined API boundary, so swapping out a component (e.g., replacing BACnet with Modbus) doesn't require touching any other layer.

---

## Layer 1: Sensor Layer

**Responsibility:** Measure the physical environment.

### Sensor Types

| Sensor | Purpose | Recommended Part | Protocol |
|--------|---------|-----------------|----------|
| Temperature + Humidity | Room-level thermal data | BME280 (±0.5°C, ±3% RH) | I²C → ESP32 → MQTT |
| CO₂ | Ventilation demand | Senseair S8 / MH-Z19B | UART → ESP32 → MQTT |
| Motion | Occupancy detection | HC-SR501 / LD2410 | GPIO → ESP32 → MQTT |
| Outdoor temp | Ambient reference | DS18B20 (1-wire) or weather API | 1-wire → ESP32 → MQTT |
| Equipment data | Supply/return temps, staging, faults | Via BACnet/Modbus from equipment controller | See Layer 2 |

### Sensor Node Design

Each room gets an ESP32 with:
- BME280 (T/RH) — always present
- Optional: CO₂ sensor, PIR motion sensor
- Powered via USB-C or 24VAC transformer tap
- Communicates via WiFi → MQTT (WiFi credentials stored in ESPHome secrets)

**Firmware:** ESPHome — declarative YAML, OTA updates, Home Assistant auto-discovery built in.

---

## Layer 2: Hardware Abstraction Layer (HAL)

**Responsibility:** Translate between the orchestrator and whatever HVAC equipment exists.

The HAL presents a **unified equipment API** — the orchestrator calls `set_setpoint(zone, temp)`, `get_equipment_state()`, `get_sensor_readings()` — and the HAL figures out how to actually do that for the specific equipment.

### Supported Interfaces

#### BACnet MS/TP (via BAC0 + CWCVT or equivalent)
- Most common on JCI, Carrier, Trane, Lennox, Daikin communicating systems
- Wireless bridge (CWCVT or similar) converts MS/TP serial → WiFi → BACnet/IP
- BAC0 Python library discovers and reads/writes points
- **Available points:** supply/return temp, outdoor temp, compressor stages, fan status, economizer position, leaving water temp, defrost state, error codes, runtime hours

#### Modbus RTU
- Common on VRF systems, some heat pumps, third-party controllers
- minimalmodbus library via USB-to-RS485 adapter
- Point map varies by manufacturer (stored in `hardware/profiles/`)

#### Dry Contact (24V)
- Universal fallback for any HVAC equipment
- Sainsmart 4/8-channel relay board connected to RPi GPIO
- Relay in parallel with existing thermostat wire
- Simple on/off control: CALL_FOR_HEAT, CALL_FOR_COOL, FAN

#### Smart Thermostat API
- Some installations have a connected thermostat already
- Adapters for common APIs (Ecobee, Honeywell, Venstar)
- Read-only or limited write depending on model

### Point Mapping

Every equipment type has a **profile** that maps abstract ThermVate points to the interface-specific point:

```yaml
# Example: JCI YZV036 Heat Pump via BACnet
equipment:
  model: "JCI YZV036"
  interface: bacnet
  device_instance: 18001
  points:
    supply_air_temp:
      bacnet_object: "analog-input:1"
      bacnet_property: "presentValue"
      unit: "°F"
    return_air_temp:
      bacnet_object: "analog-input:2"
      bacnet_property: "presentValue"
    compressor_stage:
      bacnet_object: "analog-output:1"
      bacnet_property: "presentValue"
      writable: true
    fan_status:
      bacnet_object: "binary-input:1"
      bacnet_property: "presentValue"
```

Profiles live in `hardware/equipment_profiles/` and are community-contributed.

---

## Layer 3: AI Orchestrator

**Responsibility:** Read sensor data, run models, produce optimization outputs.

### Data Flow

```
Sensors (MQTT) → Ingestion Pipeline → Time-Series DB (InfluxDB)
                                            ↓
                                     Feature Store
                                    (windowed stats)
                                            ↓
                              ┌───────────────┼───────────────┐
                              ↓               ↓               ↓
                       Thermal Model   Occupancy Model   Predictive Maint.
                              ↓               ↓               ↓
                              └───────────────┼───────────────┘
                                              ↓
                                       Optimization Engine
                                              ↓
                                     Setpoint Schedule
                                     Staging Decisions
                                     Economizer Commands
                                              ↓
                                     HAL → Equipment
```

### Model Details

#### Thermal Dynamics Model

**Input features (per zone):**
- Indoor temperature (last 24h, 5-min resolution)
- Outdoor temperature (last 48h)
- Solar irradiance (from weather API or local sensor)
- HVAC state (heating/cooling/off, stage)
- Timestamp features (hour, day, weekend flag)

**Architecture:** LSTM with 2–3 layers (hidden=64) or Gradient Boosted Trees (XGBoost/LightGBM). Prophet used as baseline.

**Output:** Temperature prediction 1–6 hours ahead, per zone.

**Training:** Train on 14 days of data, retrain weekly with new data. Inference runs every 5 minutes.

#### Occupancy Predictor

**Input features:**
- Motion sensor events (per zone, last 30min window)
- WiFi device presence count
- Hour of day, day of week
- Historical presence patterns

**Architecture:** Logistic regression + rule overrides (e.g., "away if no motion for 2h and no WiFi devices").

**Output:** Probability of occupancy per zone, next 6h in 30-min intervals.

#### Predictive Maintenance

**Tracked metrics:**
- Compressor cycles/hour (short-cycling detection)
- Filter pressure drop trend (from supply/return delta-T and fan current)
- Evaporator delta-T (indicates refrigerant issues)
- Defrost cycle frequency and duration (heat pumps)
- Runtime since last filter change

**Architecture:** Isolation Forest for anomaly detection + deterministic rules with thresholds.

#### Optimization Engine

**Inputs:**
- Thermal model predictions (per zone)
- Occupancy schedule (predictions + user overrides)
- Weather forecast (next 24h from Open-Meteo)
- Equipment efficiency curves (staging, heat pump COP vs temp)
- Utility rate structure (if time-of-use)

**Outputs (every 15 min):**
- Setpoints for next 6h (per zone, continuous variable)
- Staging recommendations
- Free cooling / economizer enable
- Pre-conditioning start time

**Algorithm:** Constrained optimization (scipy.optimize) minimizing energy cost subject to comfort constraints.

**Safety:** Hard limits enforced at HAL layer and controller level. The optimizer cannot command setpoints outside configurable safe bounds (default: 60–80°F). Equipment short-cycle protection (minimum 5 min between stage transitions) in hardware.

---

## Layer 4: User Interface

### Primary: Home Assistant Dashboard
- Real-time sensor readings
- Model predictions vs actual temps
- Occupancy heatmap
- Energy savings estimates
- Manual override controls

### Secondary: Grafana
- Historical trends (weeks/months)
- Equipment runtime analysis
- Model performance metrics

### Configuration
- YAML config files in `/etc/thermvate/`
- Web UI for setpoint adjustments
- Physical override: existing thermostat still works (parallel control)

---

## Communication Diagram

```
┌──────────┐  MQTT  ┌──────────────┐  REST   ┌──────────┐
│ ESP32    │───────►│  Mosquitto   │───────►│  Grafana │
│ Sensors  │        │  (broker)    │        └──────────┘
└──────────┘        └──────┬───────┘
                          │ MQTT
                          ▼
                   ┌──────────────┐     HTTP    ┌──────────────┐
                   │ Orchestrator │◄───────────│  Home        │
                   │  (Python)    │───────────►│  Assistant   │
                   └──────┬───────┘   MQTT     └──────────────┘
                          │
                    ┌─────┴─────┐
                    │           │
                    ▼           ▼
              ┌──────────┐  ┌──────────┐
              │ BAC0     │  │ Relay    │
              │ (BACnet) │  │ Board    │
              └────┬─────┘  │ (Dry CT) │
                   │        └──────────┘
              BACnet Bridge
          (CWCVT or alternative)
                   │
              ┌────▼─────┐
              │ HVAC     │
              │Equipment │
              └──────────┘
```

## Data Storage

| Data | Store | Retention | Schema |
|------|-------|-----------|--------|
| Sensor readings | InfluxDB | 90 days | measurement=temperature, humidity, co2 via MQTT |
| Model predictions | InfluxDB | 30 days | measurement=predicted_temp |
| Equipment state | InfluxDB | 90 days | measurement=compressor_stage, fan_status |
| Config | YAML files | Permanent | `/etc/thermvate/config.yaml` |
| Model artifacts | SQLite / disk | Per version | `/var/thermvate/models/` |
| Logs | Systemd journal | 30 days | Structured JSON |

## Safety Architecture

Safety is designed with **defense in depth**:

1. **Equipment controller** has built-in high/low pressure cutouts, short-cycle timers, and freeze protection independent of ThermVate
2. **HAL layer** enforces min/max setpoint bounds and minimum on/off times
3. **Orchestrator** validates all outputs against safety constraints before sending
4. **User override**: existing thermostat remains functional; AI outputs are *parallel commands*, not exclusive control
5. **Kill switch**: physical relay disconnecting the AI from the thermostat circuit (Phase 2+)
