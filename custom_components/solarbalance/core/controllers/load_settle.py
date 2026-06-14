"""Anti-yoyo settle helper for load on→off transitions.

When the controller drops a big interruptible load (e.g. pausing the EV via
fast-charge or evening-shed), the surplus that load was consuming suddenly
returns to the grid. The zero-injection PI loop then sees a one-tick export
spike and over-corrects (slamming the batteries into charge), which oscillates
for a few ticks — the "yoyo".

This module turns a load-dispatch transition into a *settle* directive:

- ``load_drop_w`` measures how much load power disappeared between two dispatch
  states (only decreases count; new/increased loads do not).
- ``arm_settle`` decides, from that drop, whether to arm a settle window: freeze
  the PI integral for a few ticks and emit a one-shot feed-forward equal to the
  dropped power, so the controllable battery fleet immediately discharges that
  much less instead of waiting for the loop to react.

Non-controllable batteries cannot be commanded, so the feed-forward only moves
the controllable fleet; the integral freeze still helps there by stopping the
loop from fighting their transient.

Pure module — no Home Assistant imports.
"""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class SettleState:
    """Active settle window: PI frozen for ``ticks_remaining`` ticks.

    ``feedforward_w`` is the one-shot discharge reduction (W, battery-charge
    convention: positive = charge more / discharge less) applied on the next
    tick only, then cleared so the measured fleet power is not double-counted.
    """

    ticks_remaining: int = 0
    feedforward_w: float = 0.0

    @property
    def active(self) -> bool:
        """True while the settle window is holding the PI frozen."""
        return self.ticks_remaining > 0


def load_drop_w(prev: Mapping[str, float], current: Mapping[str, float]) -> float:
    """Total load power (W) that turned off or reduced between two dispatches."""
    return sum(max(0.0, prev.get(name, 0.0) - current.get(name, 0.0)) for name in prev)


def arm_settle(
    *,
    prev_loads: Mapping[str, float],
    current_loads: Mapping[str, float],
    settle_ticks: int,
    min_drop_w: float,
) -> SettleState | None:
    """Arm a settle window when a significant load drop just occurred.

    Returns a fresh :class:`SettleState` to install, or ``None`` when the drop
    is below ``min_drop_w`` or the behaviour is disabled (``settle_ticks <= 0``).
    """
    if settle_ticks <= 0:
        return None
    drop = load_drop_w(prev_loads, current_loads)
    if drop < min_drop_w:
        return None
    return SettleState(ticks_remaining=settle_ticks, feedforward_w=drop)


def advance_settle(state: SettleState) -> tuple[float, SettleState]:
    """Consume one settle tick.

    Returns ``(feedforward_w, next_state)``: the feed-forward to apply this tick
    (the armed value on the first tick, then 0) and the decremented state with
    the feed-forward cleared so it fires only once.
    """
    if not state.active:
        return 0.0, SettleState()
    return state.feedforward_w, SettleState(
        ticks_remaining=state.ticks_remaining - 1, feedforward_w=0.0
    )
