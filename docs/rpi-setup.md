# ThermVate RPi Setup — Quick Start Guide

This guide walks you through setting up the ThermVate orchestrator on a Raspberry Pi 5 from scratch.

## Prerequisites

- Raspberry Pi 5 (4GB+) running **Raspberry Pi OS Lite** (64-bit, Bookworm)
- MicroSD card (32GB+ recommended) or NVMe SSD
- Network connectivity (WiFi or Ethernet)
- CWCVT wireless MSTP router configured and on your network
- ESP32 sensor nodes (optional but recommended)

## Automated Setup

Run the setup script as root:

```bash
# On your RPi:
curl -fsSL https://raw.githubusercontent.com/TheRandyBee/thermvate/main/scripts/setup.sh | sudo bash
```

Or if you have the repo cloned locally:

```bash
sudo bash scripts/setup.sh
```

The script will install:
- Mosquitto MQTT broker (for sensor communication)
- InfluxDB v2 (time-series storage)
- Python 3.11+ virtual environment with all dependencies
- systemd service for the orchestrator
- Log rotation

## Post-Install Configuration

### 1. Configure Equipment

Edit `/etc/thermvate/config.yaml`:

```yaml
mqtt:
  broker: "localhost"              # Mosquitto runs locally
  topic_prefix: "thermvate"

hal:
  type: "bacnet"
  bacnet:
    cwcvt_ip: "192.168.1.50"       # YOUR CWCVT IP
    device_instance: 18001         # YOUR equipment's BACnet instance
    points:
      supply_air_temp:   { object_type: "analog-input", instance: 1 }
      return_air_temp:   { object_type: "analog-input", instance: 2 }
      cooling_setpoint:  { object_type: "analog-output", instance: 1, writable: true }
      heating_setpoint:  { object_type: "analog-output", instance: 2, writable: true }

zones:
  - name: "living_room"
    label: "Living Room"
    sensors: { temp_humidity: true, motion: true }
  - name: "bedroom_1"
    label: "Primary Bedroom"
    sensors: { temp_humidity: true, motion: true }
```

### 2. Discover BACnet Points

If you don't know your equipment's BACnet point map, run discovery:

```bash
ssh into the RPi and run:
sudo journalctl -u thermvate -f
```

Or use the discovery script directly:

```python
from orchestrator.src.hal import HardwareAbstractionLayer

config = {
    "type": "bacnet",
    "bacnet": {
        "cwcvt_ip": "192.168.1.50",
        "device_instance": 18001,
    }
}
hal = HardwareAbstractionLayer(config)
hal.connect()
points = hal.discover_equipment_points()
for p in points:
    print(f"{p['object_id']:25s} = {p['value']:10s}  ({p['name']})")
```

### 3. Flash ESP32 Sensors

```bash
# Install ESPHome in the venv
source ~/venv/bin/activate
pip install esphome

# Generate secrets
cd ~/thermvate
cp firmware/secrets.yaml.example firmware/secrets.yaml
nano firmware/secrets.yaml   # add your WiFi credentials

# Flash each sensor node
esphome run firmware/esp32-sensor.yaml
```

Update the `name` and `room` substitution at the top of the YAML for each node.

### 4. Verify MQTT Data

```bash
# Subscribe to all thermvate topics
mosquitto_sub -h localhost -t 'thermvate/#' -v

# Expected output:
# thermvate/living_room/temperature {"state": 72.3}
# thermvate/living_room/humidity {"state": 45}
# thermvate/bedroom_1/temperature {"state": 68.1}
```

### 5. Start the Orchestrator

```bash
sudo systemctl start thermvate
sudo systemctl enable thermvate   # auto-start on boot
sudo journalctl -u thermvate -f   # follow logs
```

## Manual Setup (if you don't want the automated script)

```bash
# 1. Install system packages
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git mosquitto mosquitto-clients

# 2. Install InfluxDB (see scripts/setup.sh for exact steps)

# 3. Clone the repo
git clone https://github.com/TheRandyBee/thermvate.git ~/thermvate

# 4. Create venv
python3 -m venv ~/venv
source ~/venv/bin/activate
pip install -r ~/thermvate/orchestrator/requirements.txt

# 5. Copy config
sudo mkdir -p /etc/thermvate
sudo cp ~/thermvate/orchestrator/config.example.yaml /etc/thermvate/config.yaml
sudo nano /etc/thermvate/config.yaml

# 6. Set up systemd
sudo cp ~/thermvate/scripts/thermvate.service /etc/systemd/system/
sudo systemctl enable thermvate
sudo systemctl start thermvate

# 7. Check logs
journalctl -u thermvate -f
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `MQTT connection failed` | Mosquitto not running | `sudo systemctl restart mosquitto` |
| `BACnet connection failed` | CWCVT not reachable | `ping 192.168.1.50` (your CWCVT IP) |
| `Device X not found` | Wrong device instance | Run point discovery script above |
| No sensor data | ESP32 not on WiFi or wrong topic | Check `mosquitto_sub -t 'thermvate/#'` |
| InfluxDB write errors | Wrong token or DB not created | Run `sudo influx setup` |
| Permission denied | Service user can't access files | Run `sudo chown -R thermvate:thermvate /var/lib/thermvate` |

## Architecture Diagram (Quick Reference)

```
┌──────────────────────────────────────┐
│  RPi 5                               │
│                                      │
│  thermvate.service  ────►  InfluxDB  │
│       │                              │
│       │ MQTT (local)                 │
│       ▼                              │
│  Mosquitto Broker  ◄── ESP32 sensors │
│       │                              │
│  BAC0 ──► CWCVT ──► Equipment       │
└──────────────────────────────────────┘
```
