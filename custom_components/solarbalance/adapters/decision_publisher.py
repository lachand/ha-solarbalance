"""Publish core `Decision` outputs as Home Assistant entity states.

This is the **only** component that converts decisions into entity updates,
per AGENTS.md. Strategies and controllers must never write to HA directly.
"""

import logging
from collections.abc import Mapping

from ..core.arbitrer import ArbitrationResult
from ..core.controllers.balancing import BalancingResult

_LOGGER = logging.getLogger(__name__)


class DecisionPublisher:
    """Translate `ArbitrationResult` into setpoints exposed as sensors.

    The actual `SensorEntity` instances are created by the sensor platform
    and registered here at startup. The publisher merely caches the latest
    values; entities pull them on each `async_update`.
    """

    def __init__(self) -> None:
        self._latest: ArbitrationResult | None = None
        self._latest_balancing: BalancingResult | None = None

    def publish(
        self, result: ArbitrationResult, *, balancing_result: BalancingResult | None = None
    ) -> None:
        """Cache the most recent arbitration and balancing results for entity consumption."""
        _LOGGER.debug(
            "Publishing decision (dominant=%s, batteries=%d, grid_import_max=%s)",
            result.dominant_strategy,
            len(result.decision.battery_targets),
            result.decision.grid_constraint.max_import_w,
        )
        self._latest = result
        self._latest_balancing = balancing_result

    @property
    def latest(self) -> ArbitrationResult | None:
        """Most recent published arbitration result, or None if never published."""
        return self._latest

    @property
    def latest_balancing(self) -> BalancingResult | None:
        """Most recent balancing result, reflecting actual per-battery allocations."""
        return self._latest_balancing

    @property
    def setpoint_charge_per_battery_w(self) -> Mapping[str, float]:
        """Actual per-battery charge power from the last balancing pass (W, positive)."""
        if self._latest_balancing is not None:
            return {name: pw for name, pw in self._latest_balancing.per_battery_w.items() if pw > 0}
        if self._latest is None:
            return {}
        return {
            name: target.preferred_power_w or 0.0
            for name, target in self._latest.decision.battery_targets.items()
            if (target.preferred_power_w or 0.0) > 0
        }

    @property
    def setpoint_discharge_per_battery_w(self) -> Mapping[str, float]:
        """Actual per-battery discharge power from the last balancing pass (W, positive value)."""
        if self._latest_balancing is not None:
            return {
                name: -pw for name, pw in self._latest_balancing.per_battery_w.items() if pw < 0
            }
        if self._latest is None:
            return {}
        return {
            name: -target.preferred_power_w
            for name, target in self._latest.decision.battery_targets.items()
            if target.preferred_power_w is not None and target.preferred_power_w < 0
        }
