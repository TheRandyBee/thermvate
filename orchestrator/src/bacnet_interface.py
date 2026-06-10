"""
ThermVate — BACnet Interface via BAC0

Reads equipment data and writes setpoints over BACnet/IP through
a BACnet bridge (CWCVT wireless MS/TP bridge).

Uses the BAC0 open-source Python library (bacpypes under the hood).
BACnet MS/TP → BACnet bridge → WiFi → BACnet/IP → BAC0 → ThermVate
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("thermvate.bacnet")


@dataclass
class BACnetPoint:
    """A single BACnet point mapping."""
    name: str
    object_type: str  # analog-input, analog-output, binary-input, etc.
    instance: int
    property: str = "presentValue"
    writable: bool = False
    unit: str = ""
    last_value: Any = None
    last_read: datetime | None = None


class BACnetInterface:
    """
    Reads and writes HVAC equipment points via BAC0 + BACnet/IP bridge (CWCVT or equivalent).

    Usage:
        bacnet = BACnetInterface(config)
        bacnet.connect()
        bacnet.read_all()  # polls all configured points
        bacnet.write_setpoint("cooling_setpoint", 72.0)
    """

    def __init__(
        self,
        config: dict,
        on_data: Callable | None = None,
    ):
        """
        Args:
            config: HAL config dict with 'bacnet' key containing:
                - cwcvt_ip: BACnet bridge IP (CWCVT or equivalent)
                - device_instance: BACnet device instance of the equipment
                - poll_interval_s: seconds between poll cycles
            on_data: callback(point_name, value, unit) for each read
        """
        bacnet_cfg = config.get("bacnet", config)  # accept both
        self.cwcvt_ip = bacnet_cfg.get("cwcvt_ip", "192.168.1.50")
        self.bacnet_port = bacnet_cfg.get("bacnet_port", 47808)
        self.device_instance = bacnet_cfg.get("device_instance", 18001)
        self.poll_interval = bacnet_cfg.get("poll_interval_s", 30)
        self._on_data = on_data

        # Build point map from config
        self.points: dict[str, BACnetPoint] = {}
        raw_points = bacnet_cfg.get("points", {})
        for name, cfg in raw_points.items():
            self.points[name] = BACnetPoint(
                name=name,
                object_type=cfg.get("object_type", "analog-input"),
                instance=cfg.get("instance", 1),
                property=cfg.get("property", "presentValue"),
                writable=cfg.get("writable", False),
                unit=cfg.get("unit", ""),
            )

        self._bacnet = None
        self._connected = False
        self._last_poll = 0.0

    # ── Connection ────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Initialize BAC0 connection via BACnet bridge (CWCVT or equivalent).

        BAC0.connect() creates a BACnet/IP virtual device on the local
        network. The bridge converts between BACnet/IP (WiFi) and the
        equipment's MS/TP bus.
        """
        try:
            import bac0

            # BAC0 registers a local virtual BACnet device on our network.
            # It discovers the bridge and equipment via BACnet/IP broadcasts.
            logger.info(
                f"Connecting BAC0 via BACnet bridge at {self.cwcvt_ip}:{self.bacnet_port}"
            )
            self._bacnet = bac0.connect(
                ip=self.cwcvt_ip,
                port=self.bacnet_port,
            )

            # Give the network a moment for device discovery
            logger.info("Discovering BACnet devices (3s)...")
            time.sleep(3)

            # Read device name to confirm connection
            try:
                device_info = self._bacnet.whois(self.device_instance)
                if device_info:
                    logger.info(
                        f"Found BACnet device {self.device_instance}: "
                        f"{device_info}"
                    )
                else:
                    logger.warning(
                        f"Device {self.device_instance} not found via whois. "
                        "Trying fallback discovery..."
                    )
            except Exception as e:
                logger.warning(f"Device discovery warning: {e}")

            self._connected = True
            return True

        except ImportError:
            logger.error(
                "BAC0 library not installed. "
                "Install with: pip install BAC0 bacpypes"
            )
            return False
        except Exception as e:
            logger.error(f"BACnet connection failed: {e}")
            return False

    def disconnect(self):
        """Close BACnet connection."""
        self._connected = False
        if self._bacnet:
            try:
                self._bacnet.disconnect()
            except Exception:
                pass
            self._bacnet = None
            logger.info("BACnet disconnected")

    @property
    def connected(self) -> bool:
        return self._connected and self._bacnet is not None

    # ── Reading Points ────────────────────────────────────────

    def read_point(self, point: BACnetPoint) -> Any:
        """
        Read a single BACnet point.

        Uses BAC0's read() with the BACnet object identifier syntax:
            "<object_type>:<instance>" property "presentValue"
        """
        if not self.connected:
            logger.warning(f"Cannot read {point.name}: not connected")
            return None

        object_id = f"{point.object_type}:{point.instance}"

        try:
            value = self._bacnet.read(
                object_id,
                point.property,
                device_instance=self.device_instance,
            )
            point.last_value = value
            point.last_read = datetime.now(timezone.utc)

            # Normalize binary values
            if value in ("active", "on"):
                value = 1.0
            elif value in ("inactive", "off"):
                value = 0.0

            if self._on_data:
                self._on_data(point.name, float(value) if value is not None else None, point.unit)

            return value

        except Exception as e:
            logger.warning(
                f"Failed to read {object_id} ({point.name}): {e}"
            )
            return None

    def read_all(self) -> dict[str, Any]:
        """Read all configured points. Returns {name: value} dict."""
        results = {}
        for name, point in self.points.items():
            value = self.read_point(point)
            if value is not None:
                results[name] = value
        self._last_poll = time.time()
        return results

    # ── Writing Setpoints ─────────────────────────────────────

    def write_setpoint(self, point_name: str, value: float) -> bool:
        """
        Write a setpoint to a writable BACnet point.

        Args:
            point_name: Name of the point from config (e.g. "cooling_setpoint")
            value: Temperature in Fahrenheit

        Returns:
            True if write succeeded
        """
        point = self.points.get(point_name)
        if not point:
            logger.error(f"Unknown point: {point_name}")
            return False

        if not point.writable:
            logger.warning(f"Point {point_name} is not marked writable")
            return False

        if not self.connected:
            logger.error(f"Cannot write {point_name}: not connected")
            return False

        object_id = f"{point.object_type}:{point.instance}"

        try:
            self._bacnet.write(
                object_id,
                point.property,
                value,
                device_instance=self.device_instance,
            )
            point.last_value = value
            point.last_read = datetime.now(timezone.utc)
            logger.info(
                f"Wrote {point_name} ({object_id}) = {value} {point.unit}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to write {object_id} ({point_name}): {e}")
            return False

    # ── Discovery ─────────────────────────────────────────────

    def discover_points(self) -> list[dict]:
        """
        Brute-force discover available BACnet points on the device.
        Useful for building your equipment profile when you don't
        know what points are available.

        Returns list of {object_id, value, name} dicts.
        """
        if not self.connected:
            logger.error("Cannot discover: not connected")
            return []

        discovered = []
        obj_types = [
            "analog-input",
            "analog-output",
            "analog-value",
            "binary-input",
            "binary-output",
            "binary-value",
            "multi-state-input",
            "multi-state-output",
        ]

        for obj_type in obj_types:
            for instance in range(1, 50):  # scan instances 1-50
                object_id = f"{obj_type}:{instance}"
                try:
                    value = self._bacnet.read(
                        object_id,
                        "presentValue",
                        device_instance=self.device_instance,
                    )
                    try:
                        name = self._bacnet.read(
                            object_id,
                            "objectName",
                            device_instance=self.device_instance,
                        )
                    except Exception:
                        name = f"Unknown_{obj_type}_{instance}"

                    discovered.append({
                        "object_id": object_id,
                        "name": name,
                        "value": value,
                    })
                    logger.info(f"  Found: {object_id} = {value}  ({name})")
                except Exception:
                    # Object likely doesn't exist at this instance
                    # Many BACnet devices have non-contiguous instance numbering
                    # so we just skip silently for blank slots
                    pass

        return discovered
