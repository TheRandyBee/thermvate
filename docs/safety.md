# ThermVate Safety Architecture

**First principle:** The AI must never be the sole thing protecting equipment from damage.

## Defense in Depth (4 Layers)

### Layer 0: Equipment-Level Protection (built-in, passive)

Every modern HVAC system comes with its own safety cutouts:
- High-pressure switch (compressor protection)
- Low-pressure switch (refrigerant loss)
- Freeze stat (evaporator coil)
- Short-cycle timer (minimum compressor off time)
- High-limit temp switch (furnace/heat strip)

**These operate with or without ThermVate.** They are hardware-level, fail-safe, and independent.

### Layer 1: HAL Safety Bounds (software, enforced at protocol level)

The Hardware Abstraction Layer enforces constraints on **every write** to equipment:

```yaml
safety:
  setpoint_range:
    cool_min: 60°F
    heat_max: 80°F
  staging:
    min_on_time_sec: 180      # Minimum compressor run
    min_off_time_sec: 300     # Minimum compressor rest
    interstage_delay_sec: 60  # Between stage changes
  emergency_shutdown:
    supply_air_max: 130°F     # Overheat protection
    supply_air_min: 45°F      # Freeze protection
```

The HAL refuses any command that violates these bounds, regardless of what the AI requests.

### Layer 2: Orchestrator Validation (software, at decision level)

Before the Optimization Engine's outputs are sent to the HAL, they pass through:
- **Constraint check:** All outputs within configured bounds
- **Rate limiter:** No more than 1 staging change per 5 minutes
- **Trend check:** Monotonically increasing/decreasing temps within reason (catches sensor faults)
- **Confidence gate:** If model confidence drops below threshold, revert to baseline schedule

### Layer 3: Independent Monitoring (watchdog)

An independent process (or separate microcontroller in Phase 2+) monitors:
- Equipment runtime cycles (detects short-cycling the AI itself might cause)
- Supply air temp trends
- Orchestrator health (heartbeat)

If the watchdog detects anomalies or loses orchestrator heartbeat, it can:
1. Disconnect the AI from the control circuit (fail-safe relay)
2. Alert the homeowner
3. Log forensic data

### Layer 4: User Override

- **Existing thermostat continues to work.** ThermVate's setpoint commands are in parallel, not in series. The user can always walk up to their wall thermostat and change the temperature.
- **Physical kill switch** (Phase 2+): A physical relay that completely disconnects the AI from the equipment's control circuit.
- **Software override**: Home Assistant dashboard has a big red "Manual Control" button that reverts to the user's schedule.

## Failure Mode Analysis

| Failure | Effect | Mitigation |
|---------|--------|------------|
| Orchestrator crashes | No setpoint changes | Schedule falls back to user's last configured baseline |
| MQTT broker dies | No new sensor data | Orchestrator uses last-known values + thermal model for 2h extrapolation |
| BACnet comms lost | Can't read/write to equipment | Orchestrator logs warning, reverts to offline schedule |
| Sensor node offline | Missing zone temp | Orchestrator uses adjacent zone data + model inference |
| Power loss | Everything off | Equipment default position (heating/cooling circuit defaults to existing thermostat) |
| Model serving wrong values | Setpoints out of bounds | HAL layer refuses out-of-bounds writes. Constraint check prevents it reaching HAL. |
| False sensor reading | Model acts on bad data | Trend validation catches spikes. Cross-zone temp correlation check. |
| Weather API unavailable | No forecast | Falls back to local outdoor sensor (DS18B20) for current conditions |

## Minimum Viable Safety (Phase 1)

For the MVP, only Layer 0, 1, and the constraint check in Layer 2 are required:

```python
# orchestrator/src/safety.py
MIN_COOL = 60.0
MAX_HEAT = 80.0
MIN_STAGE_INTERVAL = 300  # seconds

def validate_setpoint(zone: str, temp: float, mode: str) -> bool:
    if mode == "cool" and temp < MIN_COOL:
        return False
    if mode == "heat" and temp > MAX_HEAT:
        return False
    return True

def validate_staging(
    last_stage_change: dict[str, float]
) -> bool:
    now = time.time()
    for zone, last_time in last_stage_change.items():
        if now - last_time < MIN_STAGE_INTERVAL:
            return False
    return True
```

## Testing Safety

- [ ] All safety bounds enforced by HAL (test with forced bad values from a test script)
- [ ] Constraint check rejects out-of-bounds setpoints
- [ ] Watchdog detects orchestrator crash and disables AI control
- [ ] Equipment runs normally with ThermVate completely offline (removed from circuit)
- [ ] Short-cycle timer respected for all staging commands
- [ ] Supply air temp limits enforced (test by capping AHU sensor)
- [ ] Physical override (existing thermostat) works as expected
