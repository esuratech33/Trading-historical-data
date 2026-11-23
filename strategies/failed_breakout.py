"""
BOT C — Failed Breakout / Mean Reversion (master plan §2, Bot C).

The plan describes the idea qualitatively, so every precise rule below
is a LABELED DEFAULT (decision pending), not plan text:

* Reference range: the first 60 minutes of the regular session
  (09:30–10:30 ET) high/low.
* Expansion guard ("disable during strong directional expansion"):
  v1 used a fixed 60-point cap — on this data the median first-hour
  range is 212.8 points and 100% of days exceeded 60, so v1 stood
  down every day and took 0 trades (result preserved in
  results/plan_backtests_2026-11-19_v1.json).
  v2 (LABELED MODIFICATION, 2026-11-19): the guard is relative —
  stand down when today's range exceeds 1.5x the median of the
  prior 20 sessions' ranges (needs >= 5 prior sessions), with a
  400-point absolute backstop for truly extreme mornings.
* Failed breakout: after 10:30, a bar closes beyond the range edge
  by at least 2 ticks; if within 30 minutes a bar closes back inside
  the range, enter AGAINST the breakout (fade).
* Stop: beyond the excursion extreme by 2 ticks. Skipped if the stop
  distance is under 2 or over 40 points.
* Target: the range midpoint; skipped unless the target distance is
  at least 0.75x the stop distance.
* Entries 10:30–15:30 ET; max 2 trades/day standalone; flatten 15:59.
"""

from datetime import datetime, time, timedelta, timezone
from statistics import median
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


class FailedBreakoutConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    session_open: str = "09:30"
    range_minutes: int = 60
    entry_end: str = "15:30"
    flatten_time: str = "15:59"
    break_buffer_ticks: int = 2
    stop_buffer_ticks: int = 2
    reclaim_window_minutes: int = 30
    max_range_points: float = 400.0
    expansion_multiple: float = 1.5
    expansion_lookback: int = 20
    min_stop_points: float = 2.0
    max_stop_points: float = 40.0
    min_reward_risk: float = 0.75
    tick_size: float = 0.25
    multiplier: int = 2
    risk_per_trade_usd: float = 100.0
    max_contracts: int = 10
    max_trades_per_day: int = 2
    use_controller: bool = False
    risk_fraction: float = 0.0
    round_trip_cost_usd: float = 2.0
    margin_init_pct: float = 0.05
    margin_fraction_cap: float = 0.9
    target_r_override: float = 0.0


class FailedBreakout(Strategy):
    def __init__(self, config: FailedBreakoutConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._entry_end_t = _parse_hhmm(config.entry_end)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._width_history: list[float] = []
        self._equity_now: float | None = None
        self._reset_day(None)

    def _reset_day(self, day) -> None:
        self._day = day
        self._rhigh: float | None = None
        self._rlow: float | None = None
        self._range_done = False
        self._disabled = False
        self._trades_today = 0
        self._exc = 0                    # +1 upside excursion, -1 downside, 0 none
        self._exc_extreme: float | None = None
        self._exc_deadline: datetime | None = None
        self._pending_stop: float | None = None
        self._pending_target: float | None = None
        self._exits_placed = False

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
            REGISTRY.record_close("C", pnl, now)

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
        range_end = (datetime.combine(day, self._open_t) + timedelta(minutes=self.config.range_minutes)).time()

        flat = self.portfolio.is_flat(self._instrument_id)

        if not flat and not self._exits_placed and self._pending_stop is not None:
            self._place_exits()
        if t >= self._flatten_t:
            if not flat:
                self.cancel_all_orders(self._instrument_id)
                self.close_all_positions(self._instrument_id)
            return

        # Build the reference range
        if self._open_t <= t < range_end:
            self._rhigh = high if self._rhigh is None else max(self._rhigh, high)
            self._rlow = low if self._rlow is None else min(self._rlow, low)
            return
        if t >= range_end and self._rhigh is not None and not self._range_done:
            self._range_done = True
            width = self._rhigh - self._rlow
            hist = self._width_history[-self.config.expansion_lookback:]
            if width > self.config.max_range_points:
                self._disabled = True
            elif len(hist) >= 5 and width > self.config.expansion_multiple * median(hist):
                self._disabled = True
            self._width_history.append(width)
        if not self._range_done or self._disabled:
            return

        buffer = self.config.break_buffer_ticks * self.config.tick_size
        midpoint = (self._rhigh + self._rlow) / 2.0

        # Track excursions and detect the reclaim
        direction = 0
        stop = target = None
        if self._exc == 0:
            if close > self._rhigh + buffer:
                self._exc, self._exc_extreme = 1, high
                self._exc_deadline = ts + timedelta(minutes=self.config.reclaim_window_minutes)
            elif close < self._rlow - buffer:
                self._exc, self._exc_extreme = -1, low
                self._exc_deadline = ts + timedelta(minutes=self.config.reclaim_window_minutes)
            return
        if ts > self._exc_deadline:
            self._exc, self._exc_extreme = 0, None
            return
        if self._exc == 1:
            self._exc_extreme = max(self._exc_extreme, high)
            if close <= self._rhigh:      # reclaimed -> fade short
                direction = -1
                stop = self._exc_extreme + self.config.stop_buffer_ticks * self.config.tick_size
                target = midpoint
        else:
            self._exc_extreme = min(self._exc_extreme, low)
            if close >= self._rlow:       # reclaimed -> fade long
                direction = 1
                stop = self._exc_extreme - self.config.stop_buffer_ticks * self.config.tick_size
                target = midpoint
        if direction == 0:
            return
        self._exc, self._exc_extreme = 0, None

        if not flat or self.cache.orders_inflight(strategy_id=self.id):
            return
        if self._trades_today >= self.config.max_trades_per_day:
            return
        if t > self._entry_end_t:
            return
        risk = abs(close - stop)
        if self.config.target_r_override > 0:
            target = close + direction * self.config.target_r_override * risk
        reward = abs(target - close)
        if not (self.config.min_stop_points <= risk <= self.config.max_stop_points):
            return
        if reward < self.config.min_reward_risk * risk:
            return
        if self.config.use_controller and not REGISTRY.allow_entry("C", ts):
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
        self.submit_order(order)
        self._trades_today += 1
        if self.config.use_controller:
            REGISTRY.record_entry("C", ts)

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
