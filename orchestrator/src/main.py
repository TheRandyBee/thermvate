"""
ThermVate Orchestrator — Main Entry Point

Wires together all subsystems with proper lifecycle management:

  MQTT → Sensor Data → InfluxDB (time-series storage)
  HAL  → Equipment State → InfluxDB
  BAC0  ← Setpoint Commands ← Safety Enforcer ← Optimization Engine

Run:
    python -m orchestrator.src.main
    # or
    THERMVATE_CONFIG=/path/to/config.yaml python -m orchestrator.src.main
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .mqtt_bridge import MqttBridge
from .hal import HardwareAbstractionLayer
from .influx_writer import InfluxConfig, InfluxWriter
from .safety import SafetyEnforcer
from .health_api import set_orchestrator, start_health_api

logger = logging.getLogger("thermvate")

# Config resolution
CONFIG_PATHS = [
    Path(os.getenv("THERMVATE_CONFIG", "")),
    Path("/etc/thermvate/config.yaml"),
    Path("orchestrator/config.example.yaml"),
    Path("config.example.yaml"),
]


class ThermVateOrchestrator:
    """
    Central orchestrator connecting all ThermVate subsystems.

    Owns the lifecycle of:
    - Config loading
    - MQTT sensor ingestion
    - BACnet/Modbus/dry-contact equipment interface (HAL)
    - InfluxDB time-series storage
    - Safety enforcement
    - Optimization loop (future: AI models)
    """

    def __init__(self):
        self.config: dict = {}
        self.running = False

        # Subsystems (initialized in setup())
        self.mqtt: MqttBridge | None = None
        self.hal: HardwareAbstractionLayer | None = None
        self.influx: InfluxWriter | None = None
        self.safety: SafetyEnforcer | None = None

        # Timers
        self._bacnet_poll_task: asyncio.Task | None = None
        self._optimize_task: asyncio.Task | None = None

        # Signal handling for graceful shutdown
        self._shutdown_event = asyncio.Event()

    # ── Initialization ────────────────────────────────────────

    def load_config(self) -> dict:
        """Load configuration from the first available path."""
        for path_str in [os.getenv("THERMVATE_CONFIG", "")]:
            if path_str:
                path = Path(path_str)
                if path.exists():
                    with open(path) as f:
                        return yaml.safe_load(f)

        for path in CONFIG_PATHS:
            if path.exists():
                logger.info(f"Loaded config from {path}")
                with open(path) as f:
                    return yaml.safe_load(f)

        logger.warning(
            "No config found at any path. FALLING BACK to defaults.\n"
            f"  Searched: {[str(p) for p in CONFIG_PATHS]}"
        )
        return self._default_config()

    @staticmethod
    def _default_config() -> dict:
        """Minimal default config for development/testing."""
        return {
            "orchestrator": {"name": "thermvate-dev", "log_level": "DEBUG"},
            "zones": [
                {
                    "name": "test_zone",
                    "label": "Test Zone",
                    "min_setpoint_f": 62,
                    "max_setpoint_f": 80,
                    "sensors": {"temp_humidity": True},
                }
            ],
            "mqtt": {
                "broker": "localhost",
                "port": 1883,
                "topic_prefix": "thermvate",
                "client_id": "thermvate-dev",
            },
            "hal": {
                "type": "bacnet",
                "bacnet": {
                    "cwcvt_ip": "192.168.1.50",
                    "device_instance": 1,
                    "poll_interval_s": 30,
                    "points": {
                        "supply_air_temp": {
                            "object_type": "analog-input",
                            "instance": 1,
                            "property": "presentValue",
                            "unit": "°F",
                        },
                        "return_air_temp": {
                            "object_type": "analog-input",
                            "instance": 2,
                            "property": "presentValue",
                            "unit": "°F",
                        },
                    },
                },
            },
            "influxdb": {
                "url": "http://localhost:8086",
                "v1_database": "thermvate",
            },
            "safety": {
                "min_setpoint_f": 60,
                "max_setpoint_f": 80,
                "min_stage_interval_s": 300,
            },
        }

    def setup(self):
        """Initialize all subsystems from config."""
        self.config = self.load_config()
        orch_cfg = self.config.get("orchestrator", {})

        # Log level
        logging.getLogger("thermvate").setLevel(
            getattr(logging, orch_cfg.get("log_level", "INFO"))
        )

        logger.info(
            f"ThermVate v0.1.0 starting — "
            f"{orch_cfg.get('name', 'unnamed')}"
        )

        # Health API (Docker health checks)
        start_health_api()
        set_orchestrator(self)

        # InfluxDB
        self.influx = InfluxWriter(InfluxConfig(**{
            k: v for k, v in self.config.get("influxdb", {}).items()
        }))
        self.influx.connect()

        # Safety
        self.safety = SafetyEnforcer(
            self.config.get("safety", {})
        )

        # MQTT Bridge (sensor data → influx)
        self.mqtt = MqttBridge(
            config=self.config.get("mqtt", {}),
            on_sensor_data=self._handle_sensor_data,
            on_alarm=self._handle_alarm,
        )

        # Hardware Abstraction Layer
        self.hal = HardwareAbstractionLayer(
            config=self.config.get("hal", {}),
            on_equipment_data=self._handle_equipment_data,
        )

    # ── Data Handlers ─────────────────────────────────────────

    def _handle_sensor_data(
        self,
        zone: str,
        measurement: str,
        value: float,
        timestamp: datetime,
        raw: dict,
    ):
        """Called by MQTT bridge when sensor data arrives."""
        if self.influx:
            self.influx.write_zone_sensor(
                zone=zone,
                sensor_type=measurement,
                value=value,
                timestamp=timestamp,
            )
        logger.debug(f"Sensor | {zone}/{measurement} = {value}")

    def _handle_alarm(self, zone: str, sensor_key: str, payload: dict, value: Any):
        """Called by MQTT bridge on alarm condition."""
        logger.warning(f"ALARM from {zone}/{sensor_key}: {payload}")
        if self.influx:
            self.influx.write_zone_sensor(
                zone=zone,
                sensor_type=f"{sensor_key}_alarm",
                value=float(value) if value is not None else 1.0,
            )

    def _handle_equipment_data(
        self,
        point_name: str,
        value: float | None,
        unit: str,
    ):
        """Called by HAL when equipment state is polled."""
        if self.influx and value is not None:
            self.influx.write_equipment_state(
                point_name=point_name,
                value=value,
                tags={"unit": unit} if unit else None,
            )

    # ── Background Tasks ─────────────────────────────────────

    async def _bacnet_poll_loop(self):
        """Poll equipment BACnet points on a timer."""
        interval = (
            self.config.get("hal", {})
            .get("bacnet", {})
            .get("poll_interval_s", 30)
        )
        logger.info(
            f"BACnet poll loop started (interval={interval}s)"
        )

        while self.running:
            try:
                if self.hal and self.hal.connected:
                    data = self.hal.poll()
                    if data:
                        logger.debug(f"Equipment poll: {len(data)} points")
                else:
                    logger.debug("HAL not connected, skipping poll")
            except Exception as e:
                logger.error(f"BACnet poll error: {e}")

            await asyncio.sleep(interval)

    async def _optimization_loop(self):
        """Main optimization loop — runs AI models and issues commands."""
        interval = (
            self.config.get("orchestrator", {})
            .get("optimization_interval_s", 60)
        )
        logger.info(
            f"Optimization loop started (interval={interval}s)"
        )

        while self.running:
            try:
                # 1. Read latest sensor data from InfluxDB
                # 2. Run thermal model predictions
                # 3. Run occupancy model
                # 4. Run optimization engine
                # 5. Validate commands with safety enforcer
                # 6. Issue setpoint/staging commands via HAL
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Optimization loop error: {e}")
                await asyncio.sleep(interval * 2)

    # ── Lifecycle ─────────────────────────────────────────────

    async def _connect_subsystems(self) -> bool:
        """Connect all subsystems with retries."""
        # MQTT
        if self.mqtt:
            self.mqtt.connect()

        # HAL (BACnet/Modbus/etc)
        if self.hal:
            if not self.hal.connect():
                logger.warning(
                    "HAL connection failed. System will run in "
                    "observation-only mode."
                )

        # Give things time to connect (non-blocking)
        await asyncio.sleep(2)

        return True

    async def _disconnect_subsystems(self):
        """Gracefully shut down all subsystems."""
        logger.info("Shutting down subsystems...")

        if self.hal:
            self.hal.disconnect()

        if self.mqtt:
            self.mqtt.disconnect()

        if self.influx:
            self.influx.close()

        logger.info("Shutdown complete")

    def _handle_signal(self, sig):
        """Handle shutdown signals."""
        logger.info(f"Received signal {sig}, shutting down...")
        self._shutdown_event.set()

    async def run(self):
        """Main entry point. Sets up, connects, and runs until shutdown."""
        self.setup()
        self.running = True

        # Signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._handle_signal, sig)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        # Connect to MQTT and BACnet
        await self._connect_subsystems()

        # Start background tasks
        self._bacnet_poll_task = asyncio.create_task(
            self._bacnet_poll_loop()
        )
        self._optimize_task = asyncio.create_task(
            self._optimization_loop()
        )

        logger.info(
            "\n"
            "╔══════════════════════════════════════════╗\n"
            "║        ThermVate Orchestrator           ║\n"
            "║         AI HVAC Control Online          ║\n"
            "╚══════════════════════════════════════════╝"
        )

        # Print connection status
        if self.mqtt:
            logger.info(f"  MQTT:    {'✅' if self.mqtt.connected else '⏳ connecting'}")
        if self.hal:
            logger.info(f"  HAL:     {'✅' if self.hal.connected else '⏳ connecting'}")
        if self.influx:
            logger.info(f"  Influx:  {'✅' if self.influx.connected else '⏳ connecting'}")
        logger.info(f"  Zones:   {len(self.config.get('zones', []))}")

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        # Graceful shutdown
        self.running = False
        if self._bacnet_poll_task:
            self._bacnet_poll_task.cancel()
        if self._optimize_task:
            self._optimize_task.cancel()

        await self._disconnect_subsystems()


def main():
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    orch = ThermVateOrchestrator()

    try:
        asyncio.run(orch.run())
    except KeyboardInterrupt:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
