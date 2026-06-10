"""ThermVate — quick import sanity check."""
import sys
sys.path.insert(0, '.')

from orchestrator.src.mqtt_bridge import MqttBridge
from orchestrator.src.influx_writer import InfluxConfig, InfluxWriter
from orchestrator.src.safety import SafetyEnforcer, SafetyLimits
from orchestrator.src.hal import HardwareAbstractionLayer
from orchestrator.src.health_api import app, set_orchestrator, start_health_api
from orchestrator.src.main import ThermVateOrchestrator
from orchestrator.src.utils.sensor_simulator import generate_sensor_data, diurnal_offset, outdoor_temp
from orchestrator.src.models.thermal import ThermalModel, ThermalModelConfig

from datetime import datetime, timezone

print("Imports OK")

# Test simulator
now = datetime.now(timezone.utc)
data = generate_sensor_data('living_room', now)
assert 'temperature' in data
assert 'humidity' in data
print(f"Simulator OK: {data['temperature']}F / {data['humidity']}%")

# Test diurnal cycle — peak at hour 15 (3pm), trough at hour 3 (3am)
offset_peak = diurnal_offset(15, 2.0)
assert abs(offset_peak - 2.0) < 0.01, f"Expected 2.0 at peak, got {offset_peak}"
print(f"Diurnal OK: hour=15 -> {offset_peak:.2f}F (peak)")

offset_trough = diurnal_offset(3, 2.0)
assert abs(offset_trough + 2.0) < 0.01, f"Expected -2.0 at trough, got {offset_trough}"
print(f"Diurnal OK: hour=3 -> {offset_trough:.2f}F (trough)")

# Test safety
se = SafetyEnforcer({
    'min_setpoint_f': 60,
    'max_setpoint_f': 80,
    'min_stage_interval_s': 300,
})
assert se.validate_setpoint('test', 72)[0]
assert not se.validate_setpoint('test', 55, 'cool')[0]
print("Safety OK: bounds work")

# Test staging rate
assert se.validate_staging('compressor', 1, 0)[0]
print("Safety OK: staging rate works")

print("\nALL CHECKS PASS")
