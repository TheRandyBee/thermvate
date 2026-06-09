"""
ThermVate — Safety Module

Enforces hard bounds and constraints on all equipment commands.
Acts as the final gate before any command reaches the HAL.

Architecture: Defense in Depth
  Layer 0: Equipment hardware cutouts (high/low pressure, freeze stat)
  Layer 1: HAL parameter bounds (this module)
  Layer 2: Orchestrator trend/sanity checks
  Layer 3: Independent watchdog (future)
  Layer 4: User override (existing thermostat)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("thermvate.safety")


@dataclass
class SafetyLimits:
    """Configurable safety bounds."""
    min_setpoint_f: float = 60.0
    max_setpoint_f: float = 80.0
    min_stage_interval_s: float = 300.0
    min_on_time_s: float = 180.0
    min_off_time_s: float = 300.0
    supply_air_max_f: float = 130.0
    supply_air_min_f: float = 45.0


class SafetyEnforcer:
    """
    Enforces safety constraints on setpoints and staging commands.

    Every command passes through:
    1. Range check — is the value within safe bounds?
    2. Rate check — has enough time passed since last change?
    3. Trend check — is the change reasonable given recent history?

    Raises SafetyViolation on failure (which the orchestrator catches
    and logs before the command ever reaches the equipment).
    """

    def __init__(self, limits: SafetyLimits | dict | None = None):
        if isinstance(limits, dict):
            self.limits = SafetyLimits(**limits)
        elif limits is None:
            self.limits = SafetyLimits()
        else:
            self.limits = limits

        # Track last transitions for rate limiting
        self._last_stage_time: dict[str, float] = {}
        self._last_any_stage: float = 0.0
        self._violations: list[dict] = []

    # ── Setpoint Validation ───────────────────────────────────

    def validate_setpoint(
        self,
        zone: str,
        temp_f: float,
        mode: str = "auto",
    ) -> tuple[bool, str]:
        """
        Check if a setpoint is within safe range.

        Args:
            zone: Zone name
            temp_f: Requested temperature in Fahrenheit
            mode: "heat", "cool", or "auto"

        Returns:
            (is_valid, reason)
        """
        if mode == "cool" and temp_f < self.limits.min_setpoint_f:
            return (
                False,
                f"Cooling setpoint {temp_f}°F < minimum {self.limits.min_setpoint_f}°F",
            )
        if mode == "heat" and temp_f > self.limits.max_setpoint_f:
            return (
                False,
                f"Heating setpoint {temp_f}°F > maximum {self.limits.max_setpoint_f}°F",
            )
        if temp_f < self.limits.min_setpoint_f or temp_f > self.limits.max_setpoint_f:
            return (
                False,
                f"Setpoint {temp_f}°F outside range "
                f"[{self.limits.min_setpoint_f}, {self.limits.max_setpoint_f}]",
            )
        return True, "ok"

    # ── Staging Validation ────────────────────────────────────

    def validate_staging(
        self,
        stage_name: str,
        new_state: int,
        current_state: int | None = None,
    ) -> tuple[bool, str]:
        """
        Check staging change against rate limits.

        Args:
            stage_name: e.g. "compressor_y1", "fan_g"
            new_state: 0 (off) or 1 (on)
            current_state: Current state if known

        Returns:
            (is_valid, reason)
        """
        now = time.time()

        # If already in the requested state, no change needed
        if current_state is not None and current_state == new_state:
            return True, "no change needed"

        # Global stage change rate limit
        elapsed_since_any = now - self._last_any_stage
        if elapsed_since_any < self.limits.min_stage_interval_s:
            remaining = self.limits.min_stage_interval_s - elapsed_since_any
            return (
                False,
                f"Global stage interval: "
                f"wait {remaining:.0f}s (min {self.limits.min_stage_interval_s}s)",
            )

        # Per-staging rate limit
        last_change = self._last_stage_time.get(stage_name, 0.0)
        elapsed = now - last_change

        # Different limits depending on on→off vs off→on
        if new_state == 1 and current_state == 0:
            # Turning on — respect min_off_time
            if elapsed < self.limits.min_off_time_s:
                remaining = self.limits.min_off_time_s - elapsed
                return (
                    False,
                    f"Minimum off time for {stage_name}: "
                    f"wait {remaining:.0f}s (min {self.limits.min_off_time_s}s)",
                )
        elif new_state == 0 and current_state == 1:
            # Turning off — respect min_on_time
            if elapsed < self.limits.min_on_time_s:
                remaining = self.limits.min_on_time_s - elapsed
                return (
                    False,
                    f"Minimum on time for {stage_name}: "
                    f"wait {remaining:.0f}s (min {self.limits.min_on_time_s}s)",
                )

        return True, "ok"

    # ── Supply Air Temp Validation ────────────────────────────

    def validate_supply_air(
        self,
        supply_temp_f: float,
    ) -> tuple[bool, str]:
        """
        Check supply air temperature against equipment limits.
        Extreme supply temps indicate system malfunction.
        """
        if supply_temp_f > self.limits.supply_air_max_f:
            return (
                False,
                f"Supply air {supply_temp_f}°F > max {self.limits.supply_air_max_f}°F "
                "- possible heat exchanger issue",
            )
        if supply_temp_f < self.limits.supply_air_min_f:
            return (
                False,
                f"Supply air {supply_temp_f}°F < min {self.limits.supply_air_min_f}°F "
                "- possible freeze condition",
            )
        return True, "ok"

    # ── Transition Tracking ───────────────────────────────────

    def record_transition(self, stage_name: str):
        """Record that a stage transition occurred."""
        now = time.time()
        self._last_stage_time[stage_name] = now
        self._last_any_stage = now

    def record_violation(self, point: str, value: Any, reason: str):
        """Log a safety violation for auditing."""
        self._violations.append({
            "time": time.time(),
            "point": point,
            "value": value,
            "reason": reason,
        })
        logger.error(f"SAFETY VIOLATION: {point}={value} — {reason}")

    def get_violations(self, clear: bool = True) -> list[dict]:
        """Get recent safety violations (and optionally clear)."""
        result = list(self._violations)
        if clear:
            self._violations.clear()
        return result

    # ── Bulk Validation ───────────────────────────────────────

    def validate_command(
        self,
        point_name: str,
        value: float,
        mode: str = "auto",
        current_state: int | None = None,
    ) -> tuple[bool, str]:
        """
        Run all applicable validations for a command.

        Returns (is_safe, reason).
        """
        # Setpoint bounds
        if "setpoint" in point_name.lower():
            valid, reason = self.validate_setpoint(
                "default", value, mode
            )
            if not valid:
                return False, reason

        # Staging rate limits
        if any(k in point_name.lower() for k in (
            "compressor", "stage", "fan", "heat", "cool"
        )):
            valid, reason = self.validate_staging(
                point_name, int(value), current_state
            )
            if not valid:
                return False, reason

        return True, "ok"
