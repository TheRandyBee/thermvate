"""
ThermVate Orchestrator — Main Entry Point

Connects MQTT sensor data → AI models → Equipment control.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

import yaml
from paho.mqtt.client import Client as MqttClient

from .models.thermal import ThermalModel, ThermalModelConfig

logger = logging.getLogger("thermvate")

CONFIG_PATH = Path(os.getenv("THERMVATE_CONFIG", "/etc/thermvate/config.yaml"))


class ThermVateOrchestrator:
    """
    Central orchestrator: reads MQTT sensor telemetry, runs AI models,
    and publishes setpoint/staging commands.
    """

    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config = self._load_config(config_path)
        self.mqtt = MqttClient()
        self.zones: dict[str, ThermalModel] = {}
        self._setup_mqtt()

    def _load_config(self, path: Path) -> dict:
        if not path.exists():
            # Fall back to default
            return {
                "mqtt_broker": "localhost",
                "mqtt_port": 1883,
                "zones": ["living_room", "bedroom", "kitchen"],
                "hal": {"type": "dry_contact", "relay_pins": [17, 18, 19]},
            }
        with open(path) as f:
            return yaml.safe_load(f)

    def _setup_mqtt(self):
        self.mqtt.on_connect = self._on_mqtt_connect
        self.mqtt.on_message = self._on_mqtt_message

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        logger.info(f"Connected to MQTT broker (rc={rc})")
        # Subscribe to all zone sensor topics
        for zone in self.config.get("zones", []):
            client.subscribe(f"thermvate/{zone}/#")

    def _on_mqtt_message(self, client, userdata, msg):
        """Handle incoming sensor data."""
        topic = msg.topic
        try:
            payload = json.loads(msg.payload)
            self._ingest_sensor_data(topic, payload)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse message on {topic}: {e}")

    def _ingest_sensor_data(self, topic: str, data: dict):
        """Store sensor reading and tick models."""
        # TODO: Write to InfluxDB
        logger.debug(f"Sensor data on {topic}: {data}")

    async def optimization_loop(self):
        """Main control loop — runs every 60 seconds."""
        while True:
            try:
                # 1. Read latest sensor data from InfluxDB
                # 2. Run thermal model predictions
                # 3. Run occupancy model
                # 4. Run optimization engine
                # 5. Publish setpoint commands
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Optimization loop error: {e}")
                await asyncio.sleep(120)

    async def run(self):
        """Start the orchestrator."""
        self.mqtt.connect(
            self.config.get("mqtt_broker", "localhost"),
            self.config.get("mqtt_port", 1883),
        )
        self.mqtt.loop_start()

        logger.info("ThermVate orchestrator starting...")
        await self.optimization_loop()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    orch = ThermVateOrchestrator()
    asyncio.run(orch.run())


if __name__ == "__main__":
    main()
