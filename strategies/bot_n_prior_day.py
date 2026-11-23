"""
BOT N — Prior-Day Level Acceptance (fast-pass research, 2026-11-22).

BRAND-NEW strategy family for this project, FIXED rules as specified —
nothing tuned on the sample:

  * Levels are the prior RTH session's high and low (PDH / PDL),
    tracked from 1-minute bars over 09:30-15:59 ET.
  * Enter long after TWO consecutive completed 5-minute closes above
    PDH (short mirrored: two consecutive closes below PDL).
  * Stop back at the level itself (PDH for a long, PDL for a short);
    skip the entry if the stop distance from the trigger close
    exceeds 25 points. The acceptance trigger is consumed either way —
    one evaluation per level per day.
  * Target = the prior day's full range projected from the level
    (PDH + range for a long, PDL - range for a short).
  * Max 1 entry per level per day (so at most 2 entries/day).
    Flat by 15:55 ET.

Conventions: 5-minute bars aggregated from the 1-minute feed exactly
like Bot F; entry/stop/target reference price is the second
(triggering) 5-minute close. Manual OCO exits like the other bots.
"""

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, PositionSide
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from controller import REGISTRY
from sizing import contract_qty, read_equity_usd

ET = ZoneInfo("America/New_York")


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


class BotNPriorDayConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    session_open: str = "09:30"
    flatten_time: str = "15:55"
    max_stop_points: float = 25.0
    tick_size: float = 0.25
    multiplier: int = 2
    risk_per_trade_usd: float = 100.0
    max_contracts: int = 10
    use_controller: bool = False
    risk_fraction: float = 0.0
    round_trip_cost_usd: float = 2.0
    margin_init_pct: float = 0.05
    margin_fraction_cap: float = 0.9


class BotNPriorDay(Strategy):
    def __init__(self, config: BotNPriorDayConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._equity_now: float | None = None
        self._bucket = None
        self._b_open = self._b_high = self._b_low = self._b_close = None
        self._pdh: float | None = None
        self._pdl: float | None = None
        self._reset_day(None)

    def _reset_day(self, day) -> None:
        self._day = day
        self._rth_high: float | None = None
        self._rth_low: float | None = None
        self._cnt_long = 0
        self._cnt_short = 0
        self._done_long = False
        self._done_short = False
        self._pending_stop: float | None = None
        self._pending_target: float | None = None
        self._exits_placed = False

    # -- lifecycle ------------------------------------------------------------
    def on_start(self) -> None:
        self.subscribe_bars(self._bar_type)

    def on_stop(self) -> None:
        self.cancel_all_orders(self._instrument_id)
        self.close_all_positions(self._instrument_id)
        self.unsubscribe_bars(self._bar_type)

    def on_position_closed(self, event: PositionClosed) -> None:
        self.cancel_all_orders(self._instrument_id)
        self._exits_placed = False
        self._pending_stop = None
        self._pending_target = None
        if self.config.use_controller:
            try:
                pnl = event.realized_pnl.as_double()
            except Exception:
                pnl = 0.0
            now = datetime.fromtimestamp(event.ts_event / 1e9, tz=timezone.utc).astimezone(ET)
            REGISTRY.record_close("N", pnl, now)

    # -- main loop --------------------------------------------------------------
    def on_bar(self, bar: Bar) -> None:
        ts = datetime.fromtimestamp(bar.ts_event / 1e9, tz=timezone.utc).astimezone(ET)
        day = ts.date()
        t = ts.time()
        if day != self._day:
            if self._day is not None and self._rth_high is not None and self._rth_low is not None:
                self._pdh, self._pdl = self._rth_high, self._rth_low
            self._reset_day(day)
        self._equity_now = read_equity_usd(self)
        if self.config.use_controller and self._equity_now is not None:
            REGISTRY.update_equity(self._equity_now, ts)

        close = float(bar.close)
        high = float(bar.high)
        low = float(bar.low)

        flat = self.portfolio.is_flat(self._instrument_id)
        if not flat and not self._exits_placed and self._pending_stop is not None:
            self._place_exits()
        if t >= self._flatten_t:
            if not flat:
                self.cancel_all_orders(self._instrument_id)
                self.close_all_positions(self._instrument_id)
            return
        if not (self._open_t <= t < time(16, 0)):
            return

        # Track today's RTH range (becomes tomorrow's levels).
        self._rth_high = high if self._rth_high is None else max(self._rth_high, high)
        self._rth_low = low if self._rth_low is None else min(self._rth_low, low)

        bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        if self._bucket is None:
            self._bucket = bucket
            self._b_open = close
            self._b_high, self._b_low, self._b_close = high, low, close
            return
        if bucket == self._bucket:
            self._b_high = max(self._b_high, high)
            self._b_low = min(self._b_low, low)
            self._b_close = close
            return
        bar5_close = self._b_close
        self._bucket = bucket
        self._b_open = close
        self._b_high, self._b_low, self._b_close = high, low, close
        self._on_5m_close(ts, bar5_close, flat)

    # -- signal ---------------------------------------------------------------------
    def _on_5m_close(self, ts, c5, flat) -> None:
        if self._pdh is None or self._pdl is None:
            return
        self._cnt_long = self._cnt_long + 1 if c5 > self._pdh else 0
        self._cnt_short = self._cnt_short + 1 if c5 < self._pdl else 0
        if self._cnt_long == 2 and not self._done_long:
            self._done_long = True
            self._enter(ts, 1, c5, self._pdh, flat)
        elif self._cnt_short == 2 and not self._done_short:
            self._done_short = True
            self._enter(ts, -1, c5, self._pdl, flat)

    def _enter(self, ts, direction, close_ref, level, flat) -> None:
        if not flat or self.cache.orders_inflight(strategy_id=self.id):
            return
        risk_points = abs(close_ref - level)
        if risk_points <= 0 or risk_points > self.config.max_stop_points:
            return
        if self.config.use_controller and not REGISTRY.allow_entry("N", ts):
            return
        if self.config.risk_fraction > 0:
            if not self._equity_now:
                return
            budget = self.config.risk_fraction * self._equity_now
        else:
            budget = self.config.risk_per_trade_usd
        qty = contract_qty(budget, risk_points, self.config.multiplier,
                           self.config.round_trip_cost_usd, self._equity_now,
                           close_ref, self.config.margin_init_pct,
                           self.config.margin_fraction_cap, self.config.max_contracts)
        if qty < 1:
            return
        day_range = self._pdh - self._pdl
        target = level + direction * day_range
        order = self.order_factory.market(
            instrument_id=self._instrument_id,
            order_side=OrderSide.BUY if direction > 0 else OrderSide.SELL,
            quantity=Quantity.from_int(qty),
        )
        self._pending_stop = level
        self._pending_target = target
        self._exits_placed = False
        self.submit_order(order)
        if self.config.use_controller:
            REGISTRY.record_entry("N", ts)

    def _place_exits(self) -> None:
        positions = self.cache.positions_open(instrument_id=self._instrument_id)
        if not positions:
            return
        pos = positions[0]
        qty = Quantity.from_int(int(pos.quantity))
        side = OrderSide.SELL if pos.side == PositionSide.LONG else OrderSide.BUY
        sl = self.order_factory.stop_market(
            instrument_id=self._instrument_id,
            order_side=side,
            quantity=qty,
            trigger_price=Price.from_str(f"{self._pending_stop:.2f}"),
        )
        tp = self.order_factory.limit(
            instrument_id=self._instrument_id,
            order_side=side,
            quantity=qty,
            price=Price.from_str(f"{self._pending_target:.2f}"),
        )
        self.submit_order(sl)
        self.submit_order(tp)
        self._exits_placed = True
