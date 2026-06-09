"""
ThermVate — InfluxDB Time-Series Writer

Ingests sensor and equipment data into InfluxDB for model training
and historical analysis. Supports both v1 (password) and v2 (token) auth.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger("thermvate.influx")


@dataclass
class InfluxConfig:
    url: str = "http://localhost:8086"
    token: str = ""
    org: str = "thermvate"
    bucket: str = "thermvate_data"
    retention_days: int = 90
    v1_database: str = "thermvate"
    v1_username: str = ""
    v1_password: str = ""


class InfluxWriter:
    """Writes sensor readings and equipment state to InfluxDB."""

    def __init__(self, config: InfluxConfig):
        self.config = config
        self._client = None
        self._write_api = None

    def connect(self) -> bool:
        """Initialize the InfluxDB client."""
        try:
            if self.config.token:
                # v2 API
                from influxdb_client import InfluxDBClient
                from influxdb_client.client.write_api import SYNCHRONOUS

                self._client = InfluxDBClient(
                    url=self.config.url,
                    token=self.config.token,
                    org=self.config.org,
                )
                self._write_api = self._client.write_api(write_type=SYNCHRONOUS)
                logger.info(f"Connected to InfluxDB v2 at {self.config.url}")
            else:
                # v1 API fallback
                from influxdb import InfluxDBClient

                self._client = InfluxDBClient(
                    host=self.config.url.replace("http://", "").replace(
                        "https://", ""
                    ).split(":")[0],
                    port=int(
                        self.config.url.split(":")[-1]
                        if ":" in self.config.url
                        else 8086
                    ),
                    username=self.config.v1_username or None,
                    password=self.config.v1_password or None,
                    database=self.config.v1_database,
                )
                self._client.create_database(self.config.v1_database)
                logger.info(
                    f"Connected to InfluxDB v1 at {self.config.url} "
                    f"db={self.config.v1_database}"
                )
            return True
        except Exception as e:
            logger.warning(f"InfluxDB connection failed: {e}")
            logger.warning("Continuing without time-series storage")
            return False

    @property
    def connected(self) -> bool:
        return self._client is not None

    def write_zone_sensor(
        self,
        zone: str,
        sensor_type: str,
        value: float,
        timestamp: datetime | None = None,
        tags: dict[str, str] | None = None,
    ):
        """Write a single sensor reading."""
        if not self.connected:
            return

        point = {
            "measurement": sensor_type,
            "tags": {"zone": zone, **(tags or {})},
            "time": (
                timestamp.isoformat()
                if timestamp
                else datetime.now(timezone.utc).isoformat()
            ),
            "fields": {"value": value},
        }

        try:
            if self.config.token:
                from influxdb_client import Point as InfluxPoint
                from influxdb_client.client.write_api import SYNCHRONOUS

                p = (
                    InfluxPoint(sensor_type)
                    .tag("zone", zone)
                    .field("value", value)
                )
                if timestamp:
                    p.time(timestamp)
                self._write_api.write(
                    bucket=self.config.bucket,
                    record=p,
                )
            else:
                self._client.write_points([point])
        except Exception as e:
            logger.warning(f"Failed to write {zone}/{sensor_type}={value}: {e}")

    def write_equipment_state(
        self,
        point_name: str,
        value: Any,
        tags: dict[str, str] | None = None,
    ):
        """Write equipment BACnet/modbus state."""
        if not self.connected:
            return

        # Normalize numeric
        if isinstance(value, bool):
            value = 1.0 if value else 0.0
        elif value in ("active", "on"):
            value = 1.0
        elif value in ("inactive", "off"):
            value = 0.0

        point = {
            "measurement": "equipment",
            "tags": {"point": point_name, **(tags or {})},
            "time": datetime.now(timezone.utc).isoformat(),
            "fields": {"value": float(value)},
        }

        try:
            if self.config.token:
                from influxdb_client import Point as InfluxPoint

                p = (
                    InfluxPoint("equipment")
                    .tag("point", point_name)
                    .field("value", float(value))
                )
                self._write_api.write(bucket=self.config.bucket, record=p)
            else:
                self._client.write_points([point])
        except Exception as e:
            logger.warning(
                f"Failed to write equipment {point_name}={value}: {e}"
            )

    def query_latest(
        self,
        measurement: str,
        zone: str | None = None,
    ) -> dict[str, Any] | None:
        """Get the most recent reading for a measurement."""
        if not self.connected:
            return None

        try:
            if self.config.token:
                query = (
                    f'from(bucket:"{self.config.bucket}") '
                    f'|> range(start: -1h) '
                    f'|> filter(fn: (r) => r._measurement == "{measurement}")'
                )
                if zone:
                    query += f' and r.zone == "{zone}"'
                query += ' |> last()'

                tables = self._client.query_api().query(
                    query, org=self.config.org
                )
                for table in tables:
                    for record in table.records:
                        return {
                            "value": record.get_value(),
                            "time": record.get_time(),
                            "zone": record.values.get("zone"),
                        }
            else:
                query = (
                    f'SELECT last("value") FROM "{measurement}"'
                )
                if zone:
                    query += f' WHERE "zone" = \'{zone}\''
                results = self._client.query(query)
                if results:
                    point = list(results.get_points())[0]
                    return {
                        "value": point.get("last"),
                        "time": point.get("time"),
                        "zone": zone,
                    }
            return None
        except Exception as e:
            logger.warning(
                f"Failed to query latest {measurement}/{zone}: {e}"
            )
            return None

    def query_range(
        self,
        measurement: str,
        zone: str | None = None,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Query sensor data over a time range (for model training)."""
        if not self.connected:
            return []

        try:
            if self.config.token:
                query = (
                    f'from(bucket:"{self.config.bucket}") '
                    f'|> range(start: -{hours}h) '
                    f'|> filter(fn: (r) => r._measurement == "{measurement}")'
                )
                if zone:
                    query += f' and r.zone == "{zone}"'
                query += (
                    ' |> pivot(rowKey:["_time"], '
                    'columnKey:["_field"], valueColumn: "_value")'
                    ' |> keep(columns: ["_time", "value", "zone"])'
                )

                tables = self._client.query_api().query(
                    query, org=self.config.org
                )
                results = []
                for table in tables:
                    for record in table.records:
                        results.append({
                            "time": record.get_time(),
                            "value": record.get_value_by_key("value"),
                            "zone": record.values.get("zone", zone),
                        })
                return results
            else:
                query = (
                    f'SELECT * FROM "{measurement}" '
                    f"WHERE time > now() - {hours}h"
                )
                if zone:
                    query += f' AND "zone" = \'{zone}\''
                results = self._client.query(query)
                points = []
                for series in results:
                    for point in series:
                        points.append({
                            "time": point.get("time"),
                            "value": point.get("value"),
                            "zone": point.get("zone", zone),
                        })
                return points
        except Exception as e:
            logger.warning(
                f"Failed to query range {measurement}/{zone}: {e}"
            )
            return []

    def close(self):
        """Close the InfluxDB connection."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            self._write_api = None
