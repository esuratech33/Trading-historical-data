"""
BOT B — Trend Pullback Scalper (master plan §2, Bot B).

The plan describes the idea qualitatively, so every precise rule below
is a LABELED DEFAULT (decision pending), not plan text:

* Trend (higher-timeframe direction, approximated on 1-minute bars):
  EMA(20) vs EMA(50) plus price vs session VWAP. Long trend when
  EMA20 > EMA50 and close > VWAP; short trend mirrored.
* Pullback: in a long trend, a bar closes below EMA20 (a dip toward
  the reference zone). The pullback extreme is tracked.
* Recovery confirmation: a later bar closes above the previous bar's
  high (long) / below the previous bar's low (short).
* Invalidation: trend flips, or price closes more than 12 points
  beyond VWAP against the trend (the "pullback" became a reversal).
* Stop: pullback extreme -/+ 1 tick (structural). Skipped if the stop
  distance is under 3 or over 25 points.
* Exit: 1.5R target, stop, 90-minute time stop, or 15:59 ET flatten.
* Entries 09:35–15:30 ET only; max 3 trades/day standalone.
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


class PullbackConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    session_open: str = "09:30"
    entry_start: str = "09:35"
    entry_end: str = "15:30"
    flatten_time: str = "15:59"
    ema_fast: int = 20
    ema_slow: int = 50
    deep_invalidation_points: float = 12.0
    min_stop_points: float = 3.0
    max_stop_points: float = 25.0
    target_r_multiple: float = 1.5
    time_stop_minutes: int = 90
    tick_size: float = 0.25
    multiplier: int = 2
    risk_per_trade_usd: float = 100.0
    max_contracts: int = 10
    max_trades_per_day: int = 3
    use_controller: bool = False
    risk_fraction: float = 0.0
    round_trip_cost_usd: float = 2.0
    margin_init_pct: float = 0.05
    margin_fraction_cap: float = 0.9
    target_r_override: float = 0.0


class TrendPullback(Strategy):
    def __init__(self, config: PullbackConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._entry_start_t = _parse_hhmm(config.entry_start)
        self._entry_end_t = _parse_hhmm(config.entry_end)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._ema_fast: float | None = None
        self._ema_slow: float | None = None
        self._equity_now: float | None = None
        self._prev_high: float | None = None
        self._prev_low: float | None = None
        self._reset_day(None)

    def _reset_day(self, day) -> None:
        self._day = day
        self._trades_today = 0
        self._pv = 0.0
        self._vol = 0.0
        self._armed = 0               # +1 long pullback, -1 short, 0 none
        self._extreme: float | None = None
        self._pending_stop: float | None = None
        self._pending_target: float | None = None
        self._exits_placed = False
        self._entry_time: datetime | None = None

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
        self._entry_time = None
        if self.config.use_controller:
            try:
                pnl = event.realized_pnl.as_double()
            except Exception:
                pnl = 0.0
            now = datetime.fromtimestamp(event.ts_event / 1e9, tz=timezone.utc).astimezone(ET)
            REGISTRY.record_close("B", pnl, now)

    def on_bar(self, bar: Bar) -> None:
        ts = datetime.fromtimestamp(bar.ts_event / 1e9, tz=timezone.utc).astimezone(ET)
        day = ts.date()
        t = ts.time()
        if day != self._day:
            self._reset_day(day)
        self._equity_now = read_equity_usd(self)
        if self.config.use_controller and self._equity_now is not None:
            REGISTRY.update_equity(self._equity_now, ts)

        close = float(bar.close)
        high = float(bar.high)
        low = float(bar.low)
        vol = float(bar.volume)
        prev_high, prev_low = self._prev_high, self._prev_low

        flat = self.portfolio.is_flat(self._instrument_id)

        # Manage exits for an open position
        if not flat and not self._exits_placed and self._pending_stop is not None:
            self._place_exits()
        # Time stop
        if not flat and self._entry_time is not None:
            held = (ts - self._entry_time).total_seconds() / 60.0
            if held >= self.config.time_stop_minutes:
                self.cancel_all_orders(self._instrument_id)
                self.close_all_positions(self._instrument_id)
                return
        # Flatten at the close
        if t >= self._flatten_t:
            if not flat:
                self.cancel_all_orders(self._instrument_id)
                self.close_all_positions(self._instrument_id)
            return

        # Indicators: RTH bars only (09:30-16:00 ET)
        if not (self._open_t <= t <= time(16, 0)):
            self._prev_high, self._prev_low = high, low
            return
        self._pv += ((high + low + close) / 3.0) * vol
        self._vol += vol
        vwap = self._pv / self._vol if self._vol > 0 else close
        kf = 2.0 / (self.config.ema_fast + 1)
        ks = 2.0 / (self.config.ema_slow + 1)
        self._ema_fast = close if self._ema_fast is None else close * kf + self._ema_fast * (1 - kf)
        self._ema_slow = close if self._ema_slow is None else close * ks + self._ema_slow * (1 - ks)
        self._prev_high, self._prev_low = high, low

        if self._ema_fast > self._ema_slow and close > vwap:
            trend = 1
        elif self._ema_fast < self._ema_slow and close < vwap:
            trend = -1
        else:
            trend = 0

        # Arm / track / invalidate the pullback
        if self._armed == 0:
            if trend == 1 and close < self._ema_fast:
                self._armed, self._extreme = 1, low
            elif trend == -1 and close > self._ema_fast:
                self._armed, self._extreme = -1, high
        elif self._armed == 1:
            self._extreme = min(self._extreme, low)
            if trend != 1 or close < vwap - self.config.deep_invalidation_points:
                self._armed, self._extreme = 0, None
        elif self._armed == -1:
            self._extreme = max(self._extreme, high)
            if trend != -1 or close > vwap + self.config.deep_invalidation_points:
                self._armed, self._extreme = 0, None

        # Entry: recovery confirmation
        if not flat or self.cache.orders_inflight(strategy_id=self.id):
            return
        if self._trades_today >= self.config.max_trades_per_day:
            return
        if not (self._entry_start_t <= t <= self._entry_end_t):
            return
        if self._armed == 0 or prev_high is None or prev_low is None:
            return

        direction = 0
        stop = target = None
        if self._armed == 1 and close > prev_high:
            direction = 1
            stop = self._extreme - self.config.tick_size
            risk = close - stop
            target = close + (self.config.target_r_override or self.config.target_r_multiple) * risk
        elif self._armed == -1 and close < prev_low:
            direction = -1
            stop = self._extreme + self.config.tick_size
            risk = stop - close
            target = close - (self.config.target_r_override or self.config.target_r_multiple) * risk
        if direction == 0:
            return
        if not (self.config.min_stop_points <= risk <= self.config.max_stop_points):
            return
        if self.config.use_controller and not REGISTRY.allow_entry("B", ts):
            return

        if self.config.risk_fraction > 0:
            if not self._equity_now:
                return
            budget = self.config.risk_fraction * self._equity_now
        else:
            budget = self.config.risk_per_trade_usd
        qty = contract_qty(budget, risk, self.config.multiplier,
                           self.config.round_trip_cost_usd, self._equity_now,
                           close, self.config.margin_init_pct,
                           self.config.margin_fraction_cap, self.config.max_contracts)
        if qty < 1:
            return
        order = self.order_factory.market(
            instrument_id=self._instrument_id,
            order_side=OrderSide.BUY if direction > 0 else OrderSide.SELL,
            quantity=Quantity.from_int(qty),
        )
        self._pending_stop = stop
        self._pending_target = target
        self._exits_placed = False
        self._entry_time = ts
        self._armed, self._extreme = 0, None
        self.submit_order(order)
        self._trades_today += 1
        if self.config.use_controller:
            REGISTRY.record_entry("B", ts)

    def _place_exits(self) -> None:
        positions = self.cache.positions_open(instrument_id=self._instrument_id)
        if not positions:
            return
        pos = positions[0]
        qty = Quantity.from_int(int(pos.quantity))
        if pos.side == PositionSide.LONG:
            sl_side, tp_side = OrderSide.SELL, OrderSide.SELL
        else:
            sl_side, tp_side = OrderSide.BUY, OrderSide.BUY
        sl = self.order_factory.stop_market(
            instrument_id=self._instrument_id,
            order_side=sl_side,
            quantity=qty,
            trigger_price=Price.from_str(f"{self._pending_stop:.2f}"),
        )
        tp = self.order_factory.limit(
            instrument_id=self._instrument_id,
            order_side=tp_side,
            quantity=qty,
            price=Price.from_str(f"{self._pending_target:.2f}"),
        )
        self.submit_order(sl)
        self.submit_order(tp)
        self._exits_placed = True
