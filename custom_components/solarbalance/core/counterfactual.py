"""What the orchestration is actually worth, against the honest alternative.

The existing savings figure answers "what do the panels and the batteries bring?"
by valuing every kilowatt-hour the house did not import. That number is real, but
it is not the one this integration has to justify: unplug SolarBalance and the
batteries keep doing plain self-consumption on their own — charge the surplus,
cover the deficit — and most of that saving survives. The question worth
answering is the marginal one:

    what does the *orchestration* add over the same hardware left to itself?

So a shadow controller runs alongside the real one. Every tick it faces the exact
same house load and the exact same production — both derived from the same
measurements, so no scenario gets an easier day than the other — and does the
obvious thing: charge what the sun leaves over, discharge what the house is
short, within its own power and capacity limits. Its grid flows are priced with
the same tariff as the real ones, and the difference between the two bills is the
answer.

Settling the stored energy
--------------------------
The two scenarios do not end the day holding the same charge, and that difference
is worth money. Without settling it, every mechanism that deliberately *keeps*
energy — the evening reserve above all — would read as a pure loss right up until
the moment it pays off. So the headline figure values the charge each scenario is
still sitting on, at the current import price:

    savings = (naive bill - actual bill) + (actual stored - naive stored) x price

Deliberately not modelled: what the PV would have produced uncurtailed. Measured
production is used for both scenarios, so any solar SolarBalance threw away is
simply absent from both bills. That understates the naive scenario's exports —
which makes this estimate **conservative**, never flattering.

Pure module — no Home Assistant imports; persist via ``to_dict`` / ``from_dict``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

# Skip integration across a long gap (restart, outage) rather than dumping a
# large bogus increment — same rule, same reason, as `DailyEnergyAccumulator`.
_MAX_GAP_S = 1800.0

# Round-trip efficiency of a typical LFP + inverter chain, applied as its square
# root on each leg so the shadow's stored kWh stays comparable to a real SoC.
_DEFAULT_ROUND_TRIP = 0.90


@dataclass(slots=True, frozen=True)
class CounterfactualResult:
    """Today's comparison, in the terms someone would want to read it."""

    actual_cost_eur: float
    naive_cost_eur: float
    savings_eur: float
    """Cost avoided by orchestrating, stored-energy difference settled in."""

    actual_import_kwh: float
    naive_import_kwh: float
    actual_export_kwh: float
    naive_export_kwh: float
    stored_delta_kwh: float
    """Charge the real fleet holds over the shadow's — positive = held back."""

    hours: float
    """How much of the day the comparison actually covers; below a few hours it
    is a trend, not a figure."""


@dataclass(slots=True)
class Counterfactual:
    """Run a plain self-consumption controller in the shadow of the real one.

    Args:
        usable_capacity_kwh: Usable energy of the controllable fleet. The shadow
            gets exactly the hardware the real system has — anything else would
            be comparing against a machine that does not exist.
        max_charge_w: Fleet charge limit.
        max_discharge_w: Fleet discharge limit.
        round_trip: Round-trip efficiency, split evenly across the two legs.
    """

    usable_capacity_kwh: float = 0.0
    max_charge_w: float = 0.0
    max_discharge_w: float = 0.0
    round_trip: float = _DEFAULT_ROUND_TRIP

    actual_import_kwh: float = 0.0
    actual_export_kwh: float = 0.0
    actual_cost_eur: float = 0.0
    naive_import_kwh: float = 0.0
    naive_export_kwh: float = 0.0
    naive_cost_eur: float = 0.0
    naive_stored_kwh: float = 0.0
    actual_stored_kwh: float = 0.0
    seconds: float = 0.0

    _day: date | None = field(default=None, repr=False)
    _last_ts: datetime | None = field(default=None, repr=False)
    _last_price: float = field(default=0.0, repr=False)

    def update(
        self,
        *,
        now: datetime,
        local_date: date,
        pv_w: float,
        grid_w: float,
        battery_w: float,
        stored_kwh: float,
        import_price: float | None,
        export_price: float | None,
    ) -> None:
        """Advance both scenarios by one tick.

        Args:
            now: Timestamp of this sample.
            local_date: Local date — drives the midnight reset.
            pv_w: Total PV production (W).
            grid_w: Measured grid power (W, positive = import).
            battery_w: Aggregate fleet power (W, positive = charging).
            stored_kwh: Energy the real fleet holds above its own floor. Anchors
                the shadow at the start of the day and settles the difference at
                the end of each tick.
            import_price: Current import price (EUR/kWh); with ``None`` the tick
                still advances the physics but adds no cost to either side.
            export_price: Current export price (EUR/kWh).
        """
        if self._day != local_date:
            self._reset(local_date, now, stored_kwh)
            return
        if self._last_ts is None:
            self._last_ts = now
            return
        dt_s = (now - self._last_ts).total_seconds()
        self._last_ts = now
        if dt_s <= 0.0 or dt_s > _MAX_GAP_S:
            # A gap the shadow cannot simulate would let the two scenarios drift
            # apart on nothing but missing data. Re-anchor instead of guessing.
            self.naive_stored_kwh = max(0.0, min(self.usable_capacity_kwh, stored_kwh))
            return

        dt_h = dt_s / 3600.0
        self.seconds += dt_s
        self.actual_stored_kwh = stored_kwh
        if import_price is not None:
            self._last_price = import_price

        # Both scenarios serve the same house: what the meter, the panels and the
        # fleet say the building is drawing, fleet excluded.
        house_w = max(0.0, pv_w + grid_w - battery_w)

        # --- what really happened ---
        self._bill(
            grid_w=grid_w,
            dt_h=dt_h,
            import_price=import_price,
            export_price=export_price,
            actual=True,
        )

        # --- what a plain self-consumption controller would have done ---
        self._bill(
            grid_w=self._naive_grid_w(pv_w=pv_w, house_w=house_w, dt_h=dt_h),
            dt_h=dt_h,
            import_price=import_price,
            export_price=export_price,
            actual=False,
        )

    def _naive_grid_w(self, *, pv_w: float, house_w: float, dt_h: float) -> float:
        """Step the shadow battery one tick and return its resulting grid power."""
        if self.usable_capacity_kwh <= 0.0 or dt_h <= 0.0:
            return house_w - pv_w

        leg: float = max(0.01, self.round_trip) ** 0.5
        surplus_w = pv_w - house_w
        if surplus_w > 0.0:
            room_kwh = max(0.0, self.usable_capacity_kwh - self.naive_stored_kwh)
            # The AC power the remaining room can absorb this tick.
            room_w = room_kwh / dt_h / leg * 1000.0 if leg > 0 else 0.0
            charge_w = min(surplus_w, self.max_charge_w, room_w)
            self.naive_stored_kwh += charge_w * dt_h / 1000.0 * leg
            return -(surplus_w - charge_w)

        deficit_w = -surplus_w
        avail_w = self.naive_stored_kwh / dt_h * leg * 1000.0
        discharge_w = min(deficit_w, self.max_discharge_w, avail_w)
        self.naive_stored_kwh -= discharge_w * dt_h / 1000.0 / leg
        self.naive_stored_kwh = max(0.0, self.naive_stored_kwh)
        return deficit_w - discharge_w

    def _bill(
        self,
        *,
        grid_w: float,
        dt_h: float,
        import_price: float | None,
        export_price: float | None,
        actual: bool,
    ) -> None:
        import_kwh = max(0.0, grid_w) * dt_h / 1000.0
        export_kwh = max(0.0, -grid_w) * dt_h / 1000.0
        cost = 0.0
        if import_price is not None:
            cost += import_kwh * import_price
        if export_price is not None:
            cost -= export_kwh * export_price
        if actual:
            self.actual_import_kwh += import_kwh
            self.actual_export_kwh += export_kwh
            self.actual_cost_eur += cost
        else:
            self.naive_import_kwh += import_kwh
            self.naive_export_kwh += export_kwh
            self.naive_cost_eur += cost

    def result(self) -> CounterfactualResult:
        """The comparison as it stands, with the stored-energy difference settled."""
        stored_delta = self.actual_stored_kwh - self.naive_stored_kwh
        savings = (self.naive_cost_eur - self.actual_cost_eur) + stored_delta * self._last_price
        return CounterfactualResult(
            actual_cost_eur=round(self.actual_cost_eur, 4),
            naive_cost_eur=round(self.naive_cost_eur, 4),
            savings_eur=round(savings, 4),
            actual_import_kwh=round(self.actual_import_kwh, 3),
            naive_import_kwh=round(self.naive_import_kwh, 3),
            actual_export_kwh=round(self.actual_export_kwh, 3),
            naive_export_kwh=round(self.naive_export_kwh, 3),
            stored_delta_kwh=round(stored_delta, 3),
            hours=round(self.seconds / 3600.0, 2),
        )

    def _reset(self, local_date: date, now: datetime, stored_kwh: float) -> None:
        self._day = local_date
        self._last_ts = now
        self.actual_import_kwh = 0.0
        self.actual_export_kwh = 0.0
        self.actual_cost_eur = 0.0
        self.naive_import_kwh = 0.0
        self.naive_export_kwh = 0.0
        self.naive_cost_eur = 0.0
        self.seconds = 0.0
        # Both scenarios start the day from the charge the real fleet is holding,
        # so nothing is credited to a head start neither of them earned.
        self.actual_stored_kwh = stored_kwh
        self.naive_stored_kwh = max(0.0, min(self.usable_capacity_kwh, stored_kwh))

    @property
    def day(self) -> date | None:
        """Local date the running comparison belongs to."""
        return self._day

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the Store, so a restart does not zero the day."""
        return {
            "day": self._day.isoformat() if self._day else None,
            "actual_import_kwh": self.actual_import_kwh,
            "actual_export_kwh": self.actual_export_kwh,
            "actual_cost_eur": self.actual_cost_eur,
            "naive_import_kwh": self.naive_import_kwh,
            "naive_export_kwh": self.naive_export_kwh,
            "naive_cost_eur": self.naive_cost_eur,
            "naive_stored_kwh": self.naive_stored_kwh,
            "actual_stored_kwh": self.actual_stored_kwh,
            "seconds": self.seconds,
            "last_price": self._last_price,
        }

    def restore(self, data: Mapping[str, Any]) -> None:
        """Seed persisted totals; a payload from another day is ignored, not carried."""
        raw_day = data.get("day")
        if not isinstance(raw_day, str):
            return
        try:
            self._day = date.fromisoformat(raw_day)
        except ValueError:
            return
        self._last_ts = None  # re-seeded by the next update
        self.actual_import_kwh = float(data.get("actual_import_kwh", 0.0))
        self.actual_export_kwh = float(data.get("actual_export_kwh", 0.0))
        self.actual_cost_eur = float(data.get("actual_cost_eur", 0.0))
        self.naive_import_kwh = float(data.get("naive_import_kwh", 0.0))
        self.naive_export_kwh = float(data.get("naive_export_kwh", 0.0))
        self.naive_cost_eur = float(data.get("naive_cost_eur", 0.0))
        self.naive_stored_kwh = float(data.get("naive_stored_kwh", 0.0))
        self.actual_stored_kwh = float(data.get("actual_stored_kwh", 0.0))
        self.seconds = float(data.get("seconds", 0.0))
        self._last_price = float(data.get("last_price", 0.0))
