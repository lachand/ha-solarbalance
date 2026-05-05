"""Strategy modules. Each strategy produces a `Decision` for each tick."""

from .base import Strategy
from .self_consumption import SelfConsumptionStrategy

__all__ = ["SelfConsumptionStrategy", "Strategy"]
