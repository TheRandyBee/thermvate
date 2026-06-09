"""
ThermVate — MQTT Sensor Bridge

Subscribes to ESP32 sensor node telemetry, parses payloads,
and writes them to InfluxDB.

Topic structure:
  thermvate/<zone_name>/temperature
  thermvate/<zone_name>/humidity
  thermvate/<zone_name>/pressure
  thermvate/<zone_name>/co2
  thermvate/<zone_name>/presence
  thermvate/<zone_name>/alarm
  thermvate/<zone_name>/status
"""

import json
import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt

logger = logging.getLogger("thermvate.mqtt")

TOPIC_PATTERN = re.compile(r"^thermvate/([^/]+)/(.+)$")

# Map ESPHome sensor types to internal measurement names
SENSOR_TYPE_MAP: dict[str, str] = {
    "temperature": "temperature",
    "humidity": "humidity",
    "pressure": "pressure",
    "co2": "co2",
    "presence": "presence",
    "motion": "motion",
}

# ESPHome sends state as top-level JSON key, sensor name as topic leaf
# e.g. topic: thermvate/living_room/temperature
#       payload: {"state": 72.3, "unit": "°F"}


class MqttBridge:
    """Subscribes to MQTT sensor topics and routes data to callbacks."""

    def __init__(
        self,
        config: dict,
        on_sensor_data: Callable | None = None,
        on_alarm: Callable | None = None,
    ):
        self.config = config
        self.broker = config.get("broker", "localhost")
        self.port = config.get("port", 1883)
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.topic_prefix = config.get("topic_prefix", "thermvate")
        self.client_id = config.get("client_id", "thermvate-orch")
        self.reconnect_delay = config.get("reconnect_delay_s", 5)

        self._on_sensor_data = on_sensor_data
        self._on_alarm = on_alarm

        self._client = mqtt.Client(
            client_id=self.client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        if self.username:
            self._client.username_pw_set(self.username, self.password)

        # Reconnection tracking
        self._connect_attempts = 0
        self._connected = False

    # ── Lifecycle ─────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to the MQTT broker (non-blocking)."""
        try:
            self._client.connect(self.broker, self.port, keepalive=60)
            self._client.loop_start()
            logger.info(
                f"Connecting to MQTT broker at {self.broker}:{self.port}..."
            )
            return True
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from the MQTT broker."""
        self._client.loop_stop()
        self._client.disconnect()
        self._connected = False
        logger.info("MQTT disconnected")

    @property
    def connected(self) -> bool:
        return self._connected

    # ── Callbacks ─────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Called when broker connects (MQTT v5 reason codes)."""
        if reason_code == 0:
            self._connected = True
            self._connect_attempts = 0
            logger.info("Connected to MQTT broker")
            # Subscribe to all zone topics
            self._subscribe_all()
        else:
            self._connected = False
            logger.error(f"MQTT connection failed (rc={reason_code})")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """Called on unexpected disconnect."""
        self._connected = False
        logger.warning(
            f"MQTT disconnected (rc={reason_code}), "
            f"will reconnect in {self.reconnect_delay}s"
        )

    def _on_message(self, client, userdata, msg):
        """Parse incoming MQTT message."""
        match = TOPIC_PATTERN.match(msg.topic)
        if not match:
            logger.debug(f"Ignoring non-standard topic: {msg.topic}")
            return

        zone = match.group(1)
        sensor_key = match.group(2)

        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            # ESPHome can send plain values too
            payload = {"state": msg.payload.decode().strip()}

        self._route_message(zone, sensor_key, payload)

    # ── Routing ───────────────────────────────────────────────

    def _route_message(self, zone: str, sensor_key: str, payload: dict):
        """Route a parsed message to the appropriate handler."""
        # Determine what type of sensor this is
        normalized_key = sensor_key.lower().replace(" ", "_")

        # Extract value from ESPHome's JSON or raw payload
        value = self._extract_value(payload)

        if value is None:
            logger.debug(
                f"No numeric value in {zone}/{sensor_key}: {payload}"
            )
            return

        # Route
        if "alarm" in normalized_key:
            if self._on_alarm:
                self._on_alarm(zone, normalized_key, payload, value)
            logger.warning(f"ALARM from {zone}: {payload}")
            return

        if "status" in normalized_key:
            logger.info(f"Status from {zone}: {value}")
            return

        # Map to measurement name
        measurement = SENSOR_TYPE_MAP.get(normalized_key)
        if measurement is None:
            measurement = normalized_key  # pass through unknown sensor types

        if self._on_sensor_data:
            self._on_sensor_data(
                zone=zone,
                measurement=measurement,
                value=value,
                timestamp=datetime.now(timezone.utc),
                raw=payload,
            )

    @staticmethod
    def _extract_value(payload: dict) -> float | int | None:
        """Extract a numeric value from various ESPHome payload formats."""
        if isinstance(payload, dict):
            # ESPHome JSON: {"state": 72.3} or {"value": 72.3}
            for key in ("state", "value", "count", "distance"):
                val = payload.get(key)
                if val is not None:
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        pass
            # Binary sensor: {"state": "ON"} or {"state": true}
            state = payload.get("state", "").lower()
            if state in ("on", "true", "1"):
                return 1.0
            if state in ("off", "false", "0"):
                return 0.0
        else:
            try:
                return float(payload)
            except (ValueError, TypeError):
                pass
        return None

    # ── Subscription ──────────────────────────────────────────

    def _subscribe_all(self):
        """Subscribe to all thermvate zones."""
        topic = f"{self.topic_prefix}/+/+"
        self._client.subscribe(topic, qos=1)
        logger.info(f"Subscribed to {topic}")

    def subscribe_zone(self, zone: str):
        """Explicitly subscribe to a specific zone."""
        topic = f"{self.topic_prefix}/{zone}/#"
        self._client.subscribe(topic, qos=1)
        logger.info(f"Subscribed to {topic}")
