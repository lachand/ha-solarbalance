"""Base class for all optimisation strategies."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..models import Decision, Device, Load, Snapshot


class Strategy(ABC):
    """Abstract base class for an optimisation strategy.

    A strategy receives the configured devices and loads at construction and
    produces a `Decision` on every `compute()` call.

    Strategies are pure: they do not mutate state, do not perform IO, and
    may not import from `homeassistant`.
    """

    def __init__(self, devices: Sequence[Device], loads: Sequence[Load]) -> None:
        self._devices = tuple(devices)
        self._loads = tuple(loads)

    @property
    @abstractmethod
    def kind(self) -> str:
        """Stable identifier used in configuration and arbitration logs."""

    @abstractmethod
    def compute(self, snapshot: Snapshot) -> Decision:
        """Compute this strategy's decision for the given snapshot."""

    @property
    def batteries(self) -> tuple[Device, ...]:
        """Devices declaring a battery role."""
        return tuple(d for d in self._devices if d.battery is not None)
