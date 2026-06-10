# BACnet Integration Guide

## Overview

BACnet is the most common communication protocol in commercial and high-end residential HVAC. If your equipment has a communicating thermostat or zoning system, it almost certainly has a BACnet MS/TP port.

ThermVate uses **BAC0** (brought to you by Christian Tremblay), a mature open-source BACnet Python stack, to discover devices, read points, and write setpoints over BACnet/IP. A wireless MS/TP bridge like the CWCVT converts your equipment's MS/TP serial bus to WiFi, eliminating the need for a serial cable run. **(Note: I have access to a CWCVT at work — may purchase one or use a direct serial alternative for the project.)**

## Prerequisites

- HVAC equipment with BACnet MS/TP port (check the control board for 3-pin terminal labeled "BUS A/B" or "MS/TP")
- CWCVT wireless MS/TP router (or equivalent — access at work, may purchase) OR direct RS-485 serial adapter as alternative
- Network connectivity between CWCVT and RPi orchestrator

## CWCVT Setup

The CWCVT bridges BACnet MS/TP (serial) to BACnet/IP (WiFi/Ethernet). No cloud service required.

### Wiring

```
CWCVT Terminal       Equipment Control Board
┌─────────────┐      ┌──────────────────────┐
│ B A/C A (+)  │─────│ MS/TP BUS A (+)      │
│ B A/C B (-)  │─────│ MS/TP BUS B (-)      │
│ COM / GND    │─────│ MS/TP COM / GND      │
│ 24VAC IN     │─────│ 24VAC Transformer     │
└─────────────┘      └──────────────────────┘
```

**Important:** The CWCVT is powered by the same 24VAC transformer as the equipment. Most residential units have 24VAC available at the thermostat terminals (R and C wires).

### Web Configuration

1. Connect to CWCVT's WiFi access point (SSID: "CWCVT-XXXX")
2. Navigate to `192.168.1.1` in a browser
3. Set:
   - **Network mode:** Station (connect to your WiFi)
   - **WiFi SSID/Password:** Your home network
   - **BACnet mode:** MS/TP → IP
   - **MS/TP baud rate:** 38400 (most common) or 76800
   - **Device Instance:** Assign a unique BACnet device instance (e.g., 18001)
4. Save and reboot. The CWCVT will connect to your WiFi and show its IP on the OLED display.

## BAC0 Discovery

Once the CWCVT is on your network and bridged to MS/TP:

```python
# Quick discovery script
import bac0

# Connect to BACnet network via the CWCVT's IP
bacnet = bac0.connect(
    ip="192.168.1.50",  # CWCVT's IP
    port=47808,          # BACnet/IP port (default)
)

# Discover all devices on the MS/TP bus
bacnet.discover()
print(bacnet.devices)

# Read points from a specific device
device = bacnet.devices[18001]
points = bacnet.points(device)
for point in points:
    print(f"{point.name}: {point.present_value}")

# Read specific temperature
supply_temp = bacnet.read(
    "analog-input:1", "presentValue",
    device_instance=18001
)
print(f"Supply Air Temp: {supply_temp}°F")

# Write setpoint (if writable)
bacnet.write(
    "analog-output:1", "presentValue", 72.0,
    device_instance=18001
)
```

## Finding Your Equipment's BACnet Points

Every manufacturer exposes different points. Common ones:

| BACnet Object | Typical Name | Use in ThermVate |
|---------------|-------------|-----------------|
| AI:1 | Supply Air Temp | System performance monitoring |
| AI:2 | Return Air Temp | Indoor ambient, delta-T calc |
| AI:3 | Outdoor Air Temp | Model input |
| AI:4 | Space Temp | Confirms thermostat reading |
| AI:5 | Leaving Water Temp | Heat pump performance |
| AO:1 | Cooling Setpoint | Zone temperature target |
| AO:2 | Heating Setpoint | Zone temperature target |
| BO:1 | Compressor Y1 | Stage 1 tracking |
| BO:2 | Compressor Y2 | Stage 2 tracking |
| BO:3 | Fan G | Fan status |
| BO:4 | Reversing Valve / ODB | Heat/cool mode |
| BV:1 | System Mode | Off/Heat/Cool/Auto |

**Not sure what your equipment exposes?** Use this broad discovery script:

```python
import bac0

bacnet = bac0.connect(ip="192.168.1.50")

# Dump every point from device 18001
for obj_type in ["analog-input", "analog-output", "analog-value",
                  "binary-input", "binary-output", "binary-value",
                  "multi-state-input", "multi-state-output"]:
    try:
        for i in range(1, 30):  # Try instances 1-30
            value = bacnet.read(f"{obj_type}:{i}", "presentValue",
                               device_instance=18001)
            name = bacnet.read(f"{obj_type}:{i}", "objectName",
                              device_instance=18001)
            if value is not None:
                print(f"{obj_type}:{i} = {value}  ({name})")
    except:
        continue
```

Save the results as a YAML profile in `hardware/equipment_profiles/` for your model.

## Equipment Profiles

Create a profile file like `hardware/equipment_profiles/jci_yzv036.yaml`:

```yaml
# JCI YZV036 Heat Pump Profile
equipment:
  manufacturer: Johnson Controls
  model: "YZV036"
  type: heat_pump
  interface: bacnet
  device_instance: 18001
  mstp_baud: 38400

points:
  # Temperatures
  supply_air_temp:
    bacnet_object: "analog-input:1"
    bacnet_property: "presentValue"
    unit: "°F"

  return_air_temp:
    bacnet_object: "analog-input:2"
    bacnet_property: "presentValue"
    unit: "°F"

  outdoor_air_temp:
    bacnet_object: "analog-input:3"
    bacnet_property: "presentValue"
    unit: "°F"

  # Setpoints (writable)
  cooling_setpoint:
    bacnet_object: "analog-output:1"
    bacnet_property: "presentValue"
    writable: true
    unit: "°F"
    min: 60
    max: 80

  heating_setpoint:
    bacnet_object: "analog-output:2"
    bacnet_property: "presentValue"
    writable: true
    unit: "°F"
    min: 60
    max: 80

  # Status
  compressor_y1:
    bacnet_object: "binary-output:1"
    bacnet_property: "presentValue"
    unit: "on_off"

  compressor_y2:
    bacnet_object: "binary-output:2"
    bacnet_property: "presentValue"
    unit: "on_off"

  fan_g:
    bacnet_object: "binary-output:3"
    bacnet_property: "presentValue"
    unit: "on_off"

  # Runtime tracking
  compressor_runtime:
    bacnet_object: "analog-value:1"
    bacnet_property: "presentValue"
    unit: "hours"
```

## BACnet Without CWCVT

No CWCVT? Still possible:

- **Direct serial:** FTDI USB-to-RS485 adapter → MS/TP bus. BAC0 speaks MS/TP directly with `bac0.connect(serial_port="/dev/ttyUSB0", baud=38400)`
- **BACnet/IP directly:** Some newer equipment supports BACnet/IP natively over Ethernet. Just point BAC0 at its IP address.
- **BACnet router:** Babel Buster Pro or Contemporary Controls BASR routers act as MS/TP ↔ IP gateways.
