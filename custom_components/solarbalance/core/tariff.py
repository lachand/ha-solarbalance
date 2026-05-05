"""Generic multi-slot tariff model for SolarBalance.

A tariff is declared as an ordered list of `TariffSlot` entries, each covering
a time-of-day window on selected weekdays. The model resolves the current
import/export price for a given datetime, returning `None` when no slot matches
(graceful degradation — callers fall back to a no-opinion decision).

See SPECIFICATIONS §8 — Configuration tarifaire générique multi-plages.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, time

# ---------------------------------------------------------------------------
# Slot definition
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class TariffSlot:
    """One time-of-day price window.

    Args:
        name: Human-readable label (e.g. "HC", "HP", "Peak").
        start: Inclusive start time (HH:MM or time object).
        end: Exclusive end time (HH:MM or time object).
        import_price: Import price in €/kWh (or whatever unit the user uses).
        export_price: Export price in €/kWh. Optional — defaults to 0.
        weekdays: Days of the week this slot applies to (0=Monday … 6=Sunday).
                  Empty tuple means every day.
    """

    name: str
    start: time
    end: time
    import_price: float
    export_price: float = 0.0
    weekdays: tuple[int, ...] = ()  # empty = all days

    def applies_at(self, dt: datetime) -> bool:
        """Return True when `dt` falls within this slot."""
        if self.weekdays and dt.weekday() not in self.weekdays:
            return False
        t = dt.time().replace(second=0, microsecond=0)
        if self.start <= self.end:
            return self.start <= t < self.end
        # Overnight slot: e.g. 22:00 → 06:00
        return t >= self.start or t < self.end


# ---------------------------------------------------------------------------
# Tariff registry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TariffConfig:
    """Ordered list of tariff slots with current-price resolution.

    Args:
        slots: Ordered list of `TariffSlot`. First match wins.
        default_import_price: Fallback import price when no slot matches.
        default_export_price: Fallback export price when no slot matches.
    """

    slots: list[TariffSlot] = field(default_factory=list)
    default_import_price: float | None = None
    default_export_price: float | None = None

    # ------------------------------------------------------------------

    def current_import_price(self, dt: datetime) -> float | None:
        """Resolve import price for `dt` (first matching slot, then default)."""
        for slot in self.slots:
            if slot.applies_at(dt):
                return slot.import_price
        return self.default_import_price

    def current_export_price(self, dt: datetime) -> float | None:
        """Resolve export price for `dt` (first matching slot, then default)."""
        for slot in self.slots:
            if slot.applies_at(dt):
                return slot.export_price
        return self.default_export_price

    def is_cheap_window(self, dt: datetime, *, threshold: float) -> bool:
        """Return True when the current import price is at or below `threshold`.

        Returns False when no price is resolvable (conservative: assume not cheap).
        """
        price = self.current_import_price(dt)
        if price is None:
            return False
        return price <= threshold

    def is_expensive_window(self, dt: datetime, *, threshold: float) -> bool:
        """Return True when the current import price is above `threshold`.

        Returns False when no price is resolvable (conservative: assume not expensive).
        """
        price = self.current_import_price(dt)
        if price is None:
            return False
        return price > threshold


# ---------------------------------------------------------------------------
# Convenience factory for two-level HC/HP tariffs (very common in France)
# ---------------------------------------------------------------------------


def make_hchp_tariff(
    slots: Sequence[tuple[str, str, float]],
    *,
    export_price: float = 0.0,
) -> TariffConfig:
    """Build a `TariffConfig` from a compact HC/HP declaration.

    Args:
        slots: List of ``(start_hhmm, end_hhmm, import_price)`` triples.
               Slots apply every day. The first match wins at query time.
        export_price: Export price applied to all slots (typically the buy-back
                      tariff, e.g. 0.13 €/kWh).

    Example::

        tariff = make_hchp_tariff(
            [("00:00", "06:00", 0.17), ("22:00", "24:00", 0.17)],
            export_price=0.13,
        )
    """
    parsed: list[TariffSlot] = []
    for start_s, end_s, price in slots:
        sh, sm = map(int, start_s.split(":"))
        # "24:00" is not a valid time; normalise to 00:00 with next-day semantics
        # by treating the slot as ending at midnight (00:00), which in our
        # applies_at logic means the slot ends just before 00:00 (i.e. 23:59:59).
        # Callers should declare "22:00"→"06:00" as an overnight slot instead.
        if end_s == "24:00":
            eh, em = 0, 0
        else:
            eh, em = map(int, end_s.split(":"))
        parsed.append(
            TariffSlot(
                name=f"slot_{start_s}_{end_s}",
                start=time(sh, sm),
                end=time(eh, em),
                import_price=price,
                export_price=export_price,
            )
        )
    return TariffConfig(slots=parsed)
