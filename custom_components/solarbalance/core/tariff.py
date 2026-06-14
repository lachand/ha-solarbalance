"""Generic multi-slot tariff model for SolarBalance.

A tariff is declared as an ordered list of `TariffSlot` entries, each covering
a time-of-day window on selected weekdays. The model resolves the current
import/export price for a given datetime, returning `None` when no slot matches
(graceful degradation — callers fall back to a no-opinion decision).

This module also provides:
- `TempoTariff`: EDF Tempo three-colour tariff (blue/white/red days + HC/HP slots).
- `EpexSpotTariff`: Day-ahead spot price pass-through with configurable markup.

See SPECIFICATIONS §7.3 — Configuration tarifaire générique multi-plages.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import StrEnum
from typing import Protocol


class Tariff(Protocol):
    """Common interface for all tariff resolvers (price + cheap/expensive)."""

    def current_import_price(self, dt: datetime) -> float | None: ...
    def current_export_price(self, dt: datetime) -> float | None: ...
    def is_cheap_window(self, dt: datetime, *, threshold: float) -> bool: ...
    def is_expensive_window(self, dt: datetime, *, threshold: float) -> bool: ...

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
        if end_s == "24:00":
            raise ValueError(
                f"make_hchp_tariff: end_s='24:00' is not a valid time. "
                f"Use an overnight slot instead, e.g. ('{start_s}', '00:00', ...) "
                f"written as an overnight range like ('22:00', '06:00', ...)."
            )
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


# ---------------------------------------------------------------------------
# EDF Tempo tariff
# ---------------------------------------------------------------------------


class TempoColor(StrEnum):
    """EDF Tempo day colour.

    EDF publishes the next day's colour by 11:00 (10:00 in winter) each
    working day. SolarBalance reads it from a HA entity (typically provided by
    the ``rte_tempo`` or ``rte`` HACS integration).
    """

    BLUE = "blue"
    WHITE = "white"
    RED = "red"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class TempoSlotPrices:
    """HC/HP import prices for one Tempo colour.

    Args:
        hc_price: Off-peak (Heures Creuses) import price in €/kWh.
        hp_price: Peak (Heures Pleines) import price in €/kWh.
        export_price: Buy-back price (same for all colours in current EDF offers).
    """

    hc_price: float
    hp_price: float
    export_price: float = 0.0


# Default 2025-2026 Tempo prices (indicative; override at instantiation).
_TEMPO_DEFAULTS: dict[TempoColor, TempoSlotPrices] = {
    TempoColor.BLUE: TempoSlotPrices(hc_price=0.1296, hp_price=0.1609),
    TempoColor.WHITE: TempoSlotPrices(hc_price=0.1467, hp_price=0.1894),
    TempoColor.RED: TempoSlotPrices(hc_price=0.1569, hp_price=0.7562),
}

# HC window: 22:00 → 06:00 (overnight).
_TEMPO_HC_START = time(22, 0)
_TEMPO_HC_END = time(6, 0)


class TempoTariff:
    """EDF Tempo three-colour tariff resolver.

    Combines a day-colour provider (callback returning `TempoColor` for a given
    date) with HC/HP slot detection to resolve the current import/export price.

    Args:
        color_provider: Callable ``(dt) -> TempoColor`` returning the Tempo colour
            for the **day** of ``dt``. When it returns ``UNKNOWN`` the tariff
            falls back to ``None`` (graceful degradation).
        prices: Per-colour price mapping. Defaults to 2025-2026 EDF prices.
        export_price: Global export (buy-back) price in €/kWh.
    """

    def __init__(
        self,
        color_provider: Callable[[datetime], TempoColor],
        *,
        prices: dict[TempoColor, TempoSlotPrices] | None = None,
        export_price: float = 0.0,
    ) -> None:
        self._color_provider = color_provider
        self._prices = prices if prices is not None else dict(_TEMPO_DEFAULTS)
        self._export_price = export_price

    def _is_hc(self, dt: datetime) -> bool:
        t = dt.time().replace(second=0, microsecond=0)
        # HC = 22:00 → 06:00 (overnight)
        return t >= _TEMPO_HC_START or t < _TEMPO_HC_END

    def is_off_peak(self, dt: datetime) -> bool:
        """True during the Tempo off-peak (Heures Creuses) window."""
        return self._is_hc(dt)

    def current_import_price(self, dt: datetime) -> float | None:
        """Return the HC or HP import price for the current Tempo colour.

        The Tempo "day" starts at 06:00 and ends at 06:00 the next morning.
        Ticks in the HC window 00:00–06:00 belong to the Tempo day that started
        at 06:00 the *previous* calendar day, so we look up that day's colour.
        """
        tempo_dt = dt - timedelta(hours=6) if dt.hour < 6 else dt
        color = self._color_provider(tempo_dt)
        if color is TempoColor.UNKNOWN:
            return None
        slot = self._prices.get(color)
        if slot is None:
            return None
        return slot.hc_price if self._is_hc(dt) else slot.hp_price

    def current_export_price(self, dt: datetime) -> float | None:
        """Return the export price (constant, independent of colour/slot)."""
        return self._export_price

    def is_cheap_window(self, dt: datetime, *, threshold: float) -> bool:
        """True when the current import price is at or below ``threshold``."""
        price = self.current_import_price(dt)
        return price is not None and price <= threshold

    def is_expensive_window(self, dt: datetime, *, threshold: float) -> bool:
        """True when the current import price is strictly above ``threshold``."""
        price = self.current_import_price(dt)
        return price is not None and price > threshold

    def as_tariff_config(self, dt: datetime) -> TariffConfig:
        """Snapshot current prices into a static `TariffConfig` for this tick.

        Useful for strategies that call ``tariff.current_import_price`` multiple
        times — avoids repeated calls to the color provider.
        """
        import_price = self.current_import_price(dt)
        export_price = self.current_export_price(dt)
        return TariffConfig(
            default_import_price=import_price,
            default_export_price=export_price,
        )


# ---------------------------------------------------------------------------
# EPEX/Nordpool day-ahead spot tariff
# ---------------------------------------------------------------------------


class EpexSpotTariff:
    """Day-ahead electricity spot price pass-through.

    The spot price for the current hour is supplied by a callback (typically
    reading a HA sensor fed by the ``nordpool`` or ``epex_spot`` integration).
    A fixed markup is added to cover grid fees, taxes, and supplier margin.

    Args:
        spot_price_provider: Callable ``(dt) -> float | None`` returning the
            raw spot price in €/kWh for the hour containing ``dt``.
            Returns ``None`` when the price is unavailable.
        markup: Fixed add-on in €/kWh (taxes + grid fees + margin). Added to
            the spot price to obtain the consumer import price.
        export_price: Fixed buy-back price in €/kWh (independent of spot).
        price_cap: Optional ceiling on the computed import price in €/kWh.
            Useful to clip extreme values without disabling the strategy.
        price_floor: Optional floor on the computed import price. Prevents
            negative prices from triggering unexpected behaviour.
    """

    def __init__(
        self,
        spot_price_provider: Callable[[datetime], float | None],
        *,
        markup: float = 0.0,
        export_price: float = 0.0,
        price_cap: float | None = None,
        price_floor: float | None = None,
    ) -> None:
        self._provider = spot_price_provider
        self._markup = markup
        self._export_price = export_price
        self._price_cap = price_cap
        self._price_floor = price_floor

    def current_import_price(self, dt: datetime) -> float | None:
        """Return markup-adjusted spot import price, clamped if configured."""
        raw = self._provider(dt)
        if raw is None:
            return None
        price = raw + self._markup
        if self._price_floor is not None:
            price = max(self._price_floor, price)
        if self._price_cap is not None:
            price = min(self._price_cap, price)
        return price

    def current_export_price(self, dt: datetime) -> float | None:
        """Return the fixed export buy-back price."""
        return self._export_price

    def is_cheap_window(self, dt: datetime, *, threshold: float) -> bool:
        """True when the current import price is at or below ``threshold``."""
        price = self.current_import_price(dt)
        return price is not None and price <= threshold

    def is_expensive_window(self, dt: datetime, *, threshold: float) -> bool:
        """True when the current import price is strictly above ``threshold``."""
        price = self.current_import_price(dt)
        return price is not None and price > threshold

    def as_tariff_config(self, dt: datetime) -> TariffConfig:
        """Snapshot current prices into a static `TariffConfig` for this tick."""
        return TariffConfig(
            default_import_price=self.current_import_price(dt),
            default_export_price=self.current_export_price(dt),
        )


# ---------------------------------------------------------------------------
# Builder from a validated ``tariff:`` YAML block
# ---------------------------------------------------------------------------


def parse_tempo_color(state: str | None) -> TempoColor:
    """Map a HA Tempo-colour state (RTE integrations, FR/EN labels) to TempoColor."""
    if not state:
        return TempoColor.UNKNOWN
    s = str(state).strip().lower()
    if "roug" in s or "red" in s or s == "3":
        return TempoColor.RED
    if "blanc" in s or "white" in s or s == "2":
        return TempoColor.WHITE
    if "bleu" in s or "blue" in s or s == "1":
        return TempoColor.BLUE
    return TempoColor.UNKNOWN


def build_tariff(
    spec: Mapping[str, object],
    *,
    color_provider: Callable[[datetime], TempoColor] | None = None,
    spot_price_provider: Callable[[datetime], float | None] | None = None,
) -> Tariff:
    """Build a tariff resolver from a validated ``tariff:`` block.

    ``type`` is one of ``flat`` | ``hc_hp`` | ``tempo`` | ``spot``. ``tempo``
    needs a ``color_provider`` and ``spot`` a ``spot_price_provider`` (both read
    the configured HA entities).
    """
    kind = str(spec.get("type", "flat"))
    export_price = float(spec.get("export_price", 0.0) or 0.0)

    if kind == "spot":
        if spot_price_provider is None:
            raise ValueError("spot tariff requires a spot_price_provider")
        return EpexSpotTariff(
            spot_price_provider,
            markup=float(spec.get("markup", 0.0) or 0.0),
            export_price=export_price,
            price_cap=spec.get("price_cap"),  # type: ignore[arg-type]
            price_floor=spec.get("price_floor"),  # type: ignore[arg-type]
        )

    if kind == "hc_hp":
        slots = spec.get("slots") or []
        triples = [
            (str(s["start"]), str(s["end"]), float(s["price"]))
            for s in slots  # type: ignore[union-attr]
        ]
        return make_hchp_tariff(triples, export_price=export_price)

    if kind == "tempo":
        if color_provider is None:
            raise ValueError("tempo tariff requires a color_provider")
        prices = dict(_TEMPO_DEFAULTS)
        raw_prices = spec.get("prices") or {}
        for color in (TempoColor.BLUE, TempoColor.WHITE, TempoColor.RED):
            entry = raw_prices.get(color.value)  # type: ignore[union-attr]
            if entry:
                prices[color] = TempoSlotPrices(
                    hc_price=float(entry["hc"]),
                    hp_price=float(entry["hp"]),
                    export_price=export_price,
                )
        return TempoTariff(color_provider, prices=prices, export_price=export_price)

    # flat
    return TariffConfig(
        default_import_price=float(spec.get("import_price", 0.0) or 0.0),
        default_export_price=export_price,
    )
