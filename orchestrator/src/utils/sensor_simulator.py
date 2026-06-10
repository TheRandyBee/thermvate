#!/usr/bin/env python3
"""
ThermVate — Sensor Simulator

Generates realistic fake ESP32 sensor data over MQTT for
development and testing without physical sensors.

Simulates:
- Temperature (indoor per-zone), with realistic daily cycles
- Outdoor temperature from a diurnal curve
- Humidity (correlated with temp)
- Random motion events
- Periodic CO₂ spikes (morning/evening)

Usage:
    python -m orchestrator.src.utils.sensor_simulator
    # or via Docker Compose (automatic)
"""

import asyncio
import json
import math
import os
import random
from datetime import datetime, timezone

from paho.mqtt import client as mqtt

# ── Configuration ─────────────────────────────────────────
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
INTERVAL_SEC = int(os.getenv("SIM_INTERVAL_SEC", "10"))
ZONE_NAMES = os.getenv("SIM_ZONES", "living_room,bedroom_1,kitchen,basement").split(",")
TOPIC_PREFIX = os.getenv("SIM_TOPIC_PREFIX", "thermvate")
CLIENT_ID = os.getenv("SIM_CLIENT_ID", "thermvate-sim")

# ── Zone Profiles ─────────────────────────────────────────
# Each zone has a base temp and daily amplitude to create
# realistic thermal variation.
ZONE_PROFILES = {
    "living_room": {"base_temp": 71, "amplitude": 2.0, "humidity_base": 42, "has_motion": True, "has_co2": True},
    "bedroom_1":   {"base_temp": 68, "amplitude": 1.5, "humidity_base": 48, "has_motion": True, "has_co2": False},
    "kitchen":     {"base_temp": 72, "amplitude": 3.0, "humidity_base": 50, "has_motion": True, "has_co2": True},
    "basement":    {"base_temp": 62, "amplitude": 0.5, "humidity_base": 55, "has_motion": False, "has_co2": False},
}

DEFAULT_PROFILE = {"base_temp": 70, "amplitude": 2.0, "humidity_base": 45, "has_motion": False, "has_co2": False}


def get_zone_profile(name: str) -> dict:
    return ZONE_PROFILES.get(name, DEFAULT_PROFILE)


def diurnal_offset(hour: int, amplitude: float) -> float:
    """
    Simulate daily temperature cycle:
    Peak at 3pm (hour 15), trough at 5am (hour 5).
    Returns ±amplitude depending on time of day.
    """
    # Sinusoidal: min at hour 3 (3am), max at hour 15 (3pm)
    # Phase shift = 9 makes sin(pi/2) align with hour 15
    return amplitude * math.sin((hour - 9) * math.pi / 12)


def outdoor_temp(now: datetime) -> float:
    """Realistic outdoor temp with diurnal cycle and noise."""
    hour = now.hour + now.minute / 60
    base = 45.0  # degrees F (spring/fall average)
    swing = 15.0
    noise = random.gauss(0, 1.5)
    return base + swing * math.sin((hour - 5) * math.pi / 12) + noise


def generate_sensor_data(zone: str, now: datetime) -> dict:
    """Generate a batch of sensor readings for one zone."""
    profile = get_zone_profile(zone)
    hour = now.hour + now.minute / 60

    # Temperature
    temp = (
        profile["base_temp"]
        + diurnal_offset(hour, profile["amplitude"])
        + random.gauss(0, 0.3)  # measurement noise
    )

    # Humidity (inversely correlated with temp swings)
    humidity = (
        profile["humidity_base"]
        - diurnal_offset(hour, 3.0)
        + random.gauss(0, 2)
    )
    humidity = max(20, min(80, humidity))

    readings = {
        "temperature": round(temp, 1),
        "humidity": round(humidity, 0),
        "pressure": round(1013 + random.gauss(0, 5), 0),
    }

    # Motion (random presence events)
    if profile["has_motion"]:
        # ~30% chance of motion in any 10s window during day, 10% at night
        motion_chance = 0.30 if 7 <= hour <= 23 else 0.05
        readings["motion"] = 1 if random.random() < motion_chance else 0

    # CO₂ (spikes during morning/evening + random)
    if profile["has_co2"]:
        base_co2 = 420
        # Morning spike 7-9am, evening spike 6-8pm
        if (7 <= hour <= 9) or (18 <= hour <= 20):
            base_co2 += random.uniform(200, 600)
        # Normal occupancy drift
        base_co2 += random.gauss(0, 50)
        readings["co2"] = round(max(400, min(2000, base_co2)), 0)

    return readings


def publish_temperature(client: mqtt.Client, zone: str, temp_f: float):
    payload = json.dumps({"state": temp_f, "unit": "°F"})
    client.publish(f"{TOPIC_PREFIX}/{zone}/temperature", payload, qos=1)


def publish_humidity(client: mqtt.Client, zone: str, humidity: float):
    payload = json.dumps({"state": humidity, "unit": "%"})
    client.publish(f"{TOPIC_PREFIX}/{zone}/humidity", payload, qos=1)


def publish_pressure(client: mqtt.Client, zone: str, pressure: float):
    payload = json.dumps({"state": pressure, "unit": "hPa"})
    client.publish(f"{TOPIC_PREFIX}/{zone}/pressure", payload, qos=1)


def publish_motion(client: mqtt.Client, zone: str, motion: int):
    state = "ON" if motion else "OFF"
    payload = json.dumps({"state": state})
    client.publish(f"{TOPIC_PREFIX}/{zone}/motion", payload, qos=1)


def publish_co2(client: mqtt.Client, zone: str, co2: float):
    payload = json.dumps({"state": co2, "unit": "ppm"})
    client.publish(f"{TOPIC_PREFIX}/{zone}/co2", payload, qos=1)


async def main():
    print(f"🌡️  ThermVate Sensor Simulator")
    print(f"   Broker:   {MQTT_BROKER}:{MQTT_PORT}")
    print(f"   Interval: {INTERVAL_SEC}s")
    print(f"   Zones:    {', '.join(ZONE_NAMES)}")
    print(f"   Prefix:   {TOPIC_PREFIX}/<zone>/<sensor>")
    print(f"   Press Ctrl+C to stop")
    print()

    client = mqtt.Client(
        client_id=CLIENT_ID,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )

    def on_connect(client_, userdata, flags, rc, props=None):
        print(f"✅ Connected to MQTT broker (rc={rc})")

    client.on_connect = on_connect

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return

    # Wait for connection
    await asyncio.sleep(2)

    tick = 0
    try:
        while True:
            now = datetime.now(timezone.utc)
            outdoor = outdoor_temp(now)

            for zone in ZONE_NAMES:
                data = generate_sensor_data(zone, now)

                publish_temperature(client, zone, data["temperature"])
                publish_humidity(client, zone, data["humidity"])
                publish_pressure(client, zone, data["pressure"])

                if "motion" in data:
                    publish_motion(client, zone, data["motion"])
                if "co2" in data:
                    publish_co2(client, zone, data["co2"])

                # Debug log every 6 ticks
                if tick % 6 == 0:
                    print(
                        f"  [{now.strftime('%H:%M:%S')}] "
                        f"{zone}: {data['temperature']}°F / "
                        f"{data['humidity']}% / "
                        f"{data.get('co2', '-')}ppm / "
                        f"outdoor={outdoor:.1f}°F"
                    )

            tick += 1
            await asyncio.sleep(INTERVAL_SEC)

    except asyncio.CancelledError:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
        print("\n👋 Simulator stopped")


if __name__ == "__main__":
    asyncio.run(main())
