"""
ThermVate — Hardware Abstraction Layer (HAL)

Provides a UNIFIED interface to HVAC equipment regardless of protocol.

The orchestrator calls:
    hal.read("supply_air_temp")
    hal.write("cooling_setpoint", 72.0)

...and the HAL dispatches to BACnet, Modbus, or dry-contact relay
depending on the configuration.

This is the key abstraction that makes ThermVate equipment-agnostic.
"""

import logging
from collections.abc import Callable
from typing import Any

from .bacnet_interface import BACnetInterface

logger = logging.getLogger("thermvate.hal")


class HardwareAbstractionLayer:
    """
    Unified interface to HVAC equipment.

    Supports three backends:
    - 'bacnet' — BAC0 over BACnet/IP via CWCVT
    - 'modbus' — minimalmodbus over RS-485 (stub)
    - 'dry_contact' — GPIO relay control (stub)

    The orchestrator never needs to know which protocol the equipment uses.
    """

    def __init__(
        self,
        config: dict,
        on_equipment_data: Callable | None = None,
    ):
        self.config = config
        self.hal_type = config.get("type", "bacnet")
        self._on_data = on_equipment_data

        self._bacnet: BACnetInterface | None = None
        self._connected = False
        self._point_cache: dict[str, Any] = {}

    @property
    def type(self) -> str:
        return self.hal_type

    @property
    def connected(self) -> bool:
        return self._connected

    # ── Connection ────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to equipment via configured protocol."""
        if self.hal_type == "bacnet":
            return self._connect_bacnet()
        elif self.hal_type == "modbus":
            return self._connect_modbus()
        elif self.hal_type == "dry_contact":
            return self._connect_dry_contact()
        else:
            logger.error(f"Unknown HAL type: {self.hal_type}")
            return False

    def disconnect(self):
        """Disconnect from equipment."""
        if self._bacnet:
            self._bacnet.disconnect()
        self._connected = False

    def _connect_bacnet(self) -> bool:
        """Connect via BACnet/IP."""
        self._bacnet = BACnetInterface(
            self.config,
            on_data=self._on_data,
        )
        if self._bacnet.connect():
            self._connected = True
            return True
        return False

    def _connect_modbus(self) -> bool:
        """Connect via Modbus RTU (stub)."""
        logger.warning("Modbus HAL not yet implemented")
        self._connected = False
        return False

    def _connect_dry_contact(self) -> bool:
        """Connect via GPIO relay board (stub)."""
        logger.warning("Dry contact HAL not yet implemented")
        self._connected = False
        return False

    # ── Reading ───────────────────────────────────────────────

    def read(self, point_name: str) -> Any:
        """
        Read a single equipment point.

        Args:
            point_name: Abstract point name (e.g. "supply_air_temp")

        Returns:
            Current value, or None on failure
        """
        if not self.connected:
            return None

        if self.hal_type == "bacnet" and self._bacnet:
            point = self._bacnet.points.get(point_name)
            if point:
                value = self._bacnet.read_point(point)
                if value is not None:
                    self._point_cache[point_name] = value
                return value

        # Fall back to cache
        return self._point_cache.get(point_name)

    def read_all(self) -> dict[str, Any]:
        """Read all configured equipment points."""
        if not self.connected:
            return {}

        if self.hal_type == "bacnet" and self._bacnet:
            results = self._bacnet.read_all()
            self._point_cache.update(results)
            return results

        return {}

    # ── Writing ───────────────────────────────────────────────

    def write(self, point_name: str, value: float) -> bool:
        """
        Write to an equipment point.

        Args:
            point_name: Abstract point name (e.g. "cooling_setpoint")
            value: Value to write (temp in °F, or 0/1 for binary)

        Returns:
            True if write succeeded
        """
        if not self.connected:
            logger.error(f"Cannot write {point_name}: HAL not connected")
            return False

        if self.hal_type == "bacnet" and self._bacnet:
            return self._bacnet.write_setpoint(point_name, value)

        logger.warning(f"HAL type '{self.hal_type}' does not support writes")
        return False

    # ── Poll ──────────────────────────────────────────────────

    def poll(self) -> dict[str, Any]:
        """
        Convenience: read all points and return data dict.
        Call this on a timer (e.g. every 30s).
        """
        return self.read_all()

    def get_point_list(self) -> list[dict]:
        """Get list of configured points with metadata."""
        points = []
        if self.hal_type == "bacnet" and self._bacnet:
            for name, pt in self._bacnet.points.items():
                points.append({
                    "name": name,
                    "object": f"{pt.object_type}:{pt.instance}",
                    "writable": pt.writable,
                    "value": pt.last_value,
                    "unit": pt.unit,
                })
        return points

    def discover_equipment_points(self) -> list[dict]:
        """
        Run discovery to find all BACnet points on the device.
        Useful for building your equipment profile.
        """
        if self.hal_type == "bacnet" and self._bacnet:
            return self._bacnet.discover_points()
        return []
