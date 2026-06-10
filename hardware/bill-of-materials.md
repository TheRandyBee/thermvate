# ThermVate Bill of Materials

## Core Compute (Required)

| Item | Est. Cost | Source | Notes |
|------|-----------|--------|-------|
| Raspberry Pi 5 (4GB) | $60 | Adafruit / DigiKey | 4GB sufficient, 8GB for larger homes |
| NVMe Base Hat for Pi 5 | $20 | waveshare | Boot from NVMe, way faster than SD |
| 256GB NVMe M.2 2230 | $25 | Amazon | Way more reliable than SD card |
| USB-C PSU 27W 5.1V/5A | $12 | Official RPi | Can share with monitor if using |
| Enclosure for Pi | $10 | Amazon | Ventilated, DIN-rail optional |
| **Subtotal** | **$127** | | |

## Sensor Nodes (Per Zone)

| Item | Qty per Room | Est. Cost | Notes |
|------|-------------|-----------|-------|
| ESP32 WROOM-32 | 1 | $5 | NodeMCU or DevKitC form factor |
| BME280 Module | 1 | $2.50 | I²C, ±0.5°C, ±3% RH |
| Option: MH-Z19B CO₂ | 1 | $25 | NDIR, 400–5000ppm |
| Option: LD2410 mmWave | 1 | $8 | Presence detection, not just motion |
| USB power adapter | 1 | $3 | Any 5V/1A min |
| Small enclosure | 1 | $3 | 3D printed or project box |
| Hookup wire | ~$1 | Various | Dupont or solder |
| **Subtotal per room** | | **$5–15 light / $35+ full** | |

**Recommended minimum:** 3 zones = ~$75 with CO₂ in living areas

## Equipment Interface

Choose ONE based on what your HVAC equipment supports:

### BACnet (recommended for communicating systems)

| Item | Est. Cost | Notes |
|------|-----------|-------|
| CWCVT Wireless MS/TP Router | ~$200 | BACnet MS/TP ←→ WiFi bridge |
| Option: Babel Buster Pro | $400 | Alternative BACnet gateway |
| Option: Babel Buster Pro | $400 | Alternative BACnet gateway |
| Direct RS-485 adapter | $15 | FTDI USB-to-RS485 for direct MS/TP serial (no CWCVT needed) |
| RJ12 / 3-pin terminal cable | $10 | MS/TP connection |
| **Subtotal** | **$15–$210** | Depending on chosen interface |

### Modbus (for VRF systems, chiller plants, heat pumps with Modbus)

| Item | Est. Cost | Notes |
|------|-----------|-------|
| USB-to-RS485 adapter | $15 | FTDI-based recommended |
| 2-conductor shielded wire | $10 | 100ft, 18AWG |
| 120Ω termination resistor | $2 | End of bus |
| **Subtotal** | **$27** | |

### Dry Contact (Universal — any system)

| Item | Est. Cost | Notes |
|------|-----------|-------|
| Sainsmart 4-ch relay module | $12 | Opto-isolated, RPi GPIO |
| 18/2 thermostat wire | $15 | Brown, 50ft |
| Wire nuts / Wago connectors | $5 | |
| **Subtotal** | **$32** | |

## Optional / Nice-to-Have

| Item | Est. Cost | Notes |
|------|-----------|-------|
| DS18B20 outdoor temp sensor | $4 | 1-wire, -55°C to +125°C |
| 24VAC transformer for sensors | $15 | Instead of USB adapters |
| DIN rail backplane | $20 | For clean electrical panel install |
| Ethernet cable (Pi wired) | $10 | More reliable than WiFi for orchestrator |
| APC UPS (backup power) | $50–100 | Keeps orchestrator + router up |
| USB SDR for weather data | $25 | Reads NOAA signals directly |

## Total System Cost (3-zone, BACnet, light sensors)

```
Compute               $127
3x Light sensor       $ 15
BACnet interface      $15–$210 (see equipment interface section)
Wiring & misc         $ 20
                       ─────
Total                 $162–$357
```

## Total System Cost (3-zone, Dry Contact, full sensors)
```
Compute               $127
3x Full sensor        $105
Dry contact relay     $ 32
Wiring & misc         $ 25
                       ─────
Total                 $289
```

Both under **$300 for dry contact** or **$162–$357 for BACnet** — cheaper than a single Nest thermostat and infinitely more capable.
