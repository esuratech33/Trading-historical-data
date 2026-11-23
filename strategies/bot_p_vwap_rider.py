"""
BOT P — VWAP Trend-Day Rider (payout-sprint research, 2026-11-23).

BRAND-NEW strategy family for this project, FIXED rules as specified —
nothing tuned on the sample:

  * Trend (1-minute bars, RTH): long when EMA(20) > EMA(50) and the
    close is above session VWAP; short mirrored (house trend
    definition, same as Bot B).
  * Pullback: in a long trend, a bar whose low comes within 2.0 pts of
    VWAP "touches" the VWAP zone; the pullback extreme (lowest low
    since the touch) is tracked. Mirrored for shorts (high within
    2.0 pts of VWAP, highest high tracked).
  * Entry: while armed, a bar that closes above the previous bar's
    high with close > VWAP (long) / below the previous bar's low with
    close < VWAP (short) enters at market. Multiple entries per day
    (max 4) — this is a rider, not a one-shot.
  * Invalidation: trend flip, or a close more than 12 pts beyond VWAP
    against the trend (the pullback became a reversal).
  * Initial stop: pullback extreme -/+ 1 tick; skipped unless the
    stop distance is 4-30 pts.
  * Trailing stop: chandelier 2.0 x ATR(14) (1-minute Wilder, frozen
    at entry) from the best price since entry; effective stop is the
    initial stop until the chandelier moves past it, then only
    tightens. NO fixed profit target.
  * Entries 09:45-15:15 ET. Flat by 15:55 ET.

Conventions: recursive EMAs seeded with the first close (persist
across days); session VWAP resets daily; Wilder ATR seeded with the
first TR (persists across days). House style follows Bots B/K.
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


class BotPVwapRiderConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    session_open: str = "09:30"
    entry_start: str = "09:45"
    entry_end: str = "15:15"
    flatten_time: str = "15:55"
    ema_fast: int = 20
    ema_slow: int = 50
    touch_zone_points: float = 2.0
    deep_invalidation_points: float = 12.0
    min_stop_points: float = 4.0
    max_stop_points: float = 30.0
    atr_period: int = 14
    trail_atr: float = 2.0
    tick_size: float = 0.25
    multiplier: int = 2
    risk_per_trade_usd: float = 100.0
    max_contracts: int = 10
    max_trades_per_day: int = 4
    use_controller: bool = False
    risk_fraction: float = 0.0
    round_trip_cost_usd: float = 2.0
    margin_init_pct: float = 0.05
    margin_fraction_cap: float = 0.9


class BotPVwapRider(Strategy):
    def __init__(self, config: BotPVwapRiderConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._entry_start_t = _parse_hhmm(config.entry_start)
        self._entry_end_t = _parse_hhmm(config.entry_end)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._equity_now: float | None = None
        self._ema_fast: float | None = None
        self._ema_slow: float | None = None
        self._atr: float | None = None
        self._prev_close: float | None = None
        self._prev_high: float | None = None
        self._prev_low: float | None = None
        # open-position management
        self._dir = 0
        self._atr_entry: float | None = None
        self._best: float | None = None
        self._init_stop: float | None = None
        self._placed_stop: float | None = None
        self._exits_placed = False
        self._reset_day(None)

    def _reset_day(self, day) -> None:
        self._day = day
        self._trades_today = 0
        self._pv = 0.0
        self._vol = 0.0
        self._armed = 0
        self._extreme: float | None = None

    def on_start(self) -> None:
        self.subscribe_bars(self._bar_type)

    def on_stop(self) -> None:
        self.cancel_all_orders(self._instrument_id)
        self.close_all_positions(self._instrument_id)
        self.unsubscribe_bars(self._bar_type)

    def on_position_closed(self, event: PositionClosed) -> None:
        self.cancel_all_orders(self._instrument_id)
        self._exits_placed = False
        self._placed_stop = None
        self._init_stop = None
        self._atr_entry = None
        self._best = None
        self._dir = 0
        if self.config.use_controller:
            try:
                pnl = event.realized_pnl.as_double()
            except Exception:
                pnl = 0.0
            now = datetime.fromtimestamp(event.ts_event / 1e9, tz=timezone.utc).astimezone(ET)
            REGISTRY.record_close("P", pnl, now)

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
        if not flat:
            self._manage_position(high, low)
        if t >= self._flatten_t:
            if not flat:
                self.cancel_all_orders(self._instrument_id)
                self.close_all_positions(self._instrument_id)
            self._prev_close, self._prev_high, self._prev_low = close, high, low
            return
        if not (self._open_t <= t <= time(16, 0)):
            self._prev_close, self._prev_high, self._prev_low = close, high, low
            return

        # Indicators (RTH bars only)
        self._pv += ((high + low + close) / 3.0) * vol
        self._vol += vol
        vwap = self._pv / self._vol if self._vol > 0 else close
        kf = 2.0 / (self.config.ema_fast + 1)
        ks = 2.0 / (self.config.ema_slow + 1)
        self._ema_fast = close if self._ema_fast is None else close * kf + self._ema_fast * (1 - kf)
        self._ema_slow = close if self._ema_slow is None else close * ks + self._ema_slow * (1 - ks)
        if self._prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
        n = self.config.atr_period
        self._atr = tr if self._atr is None else (self._atr * (n - 1) + tr) / n
        self._prev_close, self._prev_high, self._prev_low = close, high, low

        if self._ema_fast > self._ema_slow and close > vwap:
            trend = 1
        elif self._ema_fast < self._ema_slow and close < vwap:
            trend = -1
        else:
            trend = 0

        # Arm / track / invalidate the VWAP pullback
        if self._armed == 0:
            if trend == 1 and low <= vwap + self.config.touch_zone_points:
                self._armed, self._extreme = 1, low
            elif trend == -1 and high >= vwap - self.config.touch_zone_points:
                self._armed, self._extreme = -1, high
        elif self._armed == 1:
            self._extreme = min(self._extreme, low)
            if trend != 1 or close < vwap - self.config.deep_invalidation_points:
                self._armed, self._extreme = 0, None
        elif self._armed == -1:
            self._extreme = max(self._extreme, high)
            if trend != -1 or close > vwap + self.config.deep_invalidation_points:
                self._armed, self._extreme = 0, None

        # Entry: recovery confirmation off the VWAP touch
        if not flat or self.cache.orders_inflight(strategy_id=self.id):
            return
        if self._trades_today >= self.config.max_trades_per_day:
            return
        if not (self._entry_start_t <= t <= self._entry_end_t):
            return
        if self._armed == 0 or prev_high is None or prev_low is None or not self._atr:
            return

        direction = 0
        stop = None
        if self._armed == 1 and close > prev_high and close > vwap:
            direction = 1
            stop = self._extreme - self.config.tick_size
            risk = close - stop
        elif self._armed == -1 and close < prev_low and close < vwap:
            direction = -1
            stop = self._extreme + self.config.tick_size
            risk = stop - close
        if direction == 0:
            return
        if not (self.config.min_stop_points <= risk <= self.config.max_stop_points):
            return
        if self.config.use_controller and not REGISTRY.allow_entry("P", ts):
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
        self._dir = direction
        self._atr_entry = self._atr
        self._best = close
        self._init_stop = stop
        self._placed_stop = None
        self._exits_placed = False
        self._armed, self._extreme = 0, None
        self.submit_order(order)
        self._trades_today += 1
        if self.config.use_controller:
            REGISTRY.record_entry("P", ts)

    # -- trailing-stop management (Bot K pattern) ------------------------------
    def _manage_position(self, high: float, low: float) -> None:
        if self._dir == 0 or self._atr_entry is None:
            return
        if self._dir > 0:
            self._best = high if self._best is None else max(self._best, high)
            desired = max(self._init_stop, self._best - self.config.trail_atr * self._atr_entry)
        else:
            self._best = low if self._best is None else min(self._best, low)
            desired = min(self._init_stop, self._best + self.config.trail_atr * self._atr_entry)
        if not self._exits_placed:
            self._place_stop(desired)
            return
        improved = (desired > self._placed_stop + 1e-9) if self._dir > 0 \
            else (desired < self._placed_stop - 1e-9)
        if improved and abs(desired - self._placed_stop) >= self.config.tick_size:
            self.cancel_all_orders(self._instrument_id)
            self._place_stop(desired)

    def _place_stop(self, stop_level: float) -> None:
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
            trigger_price=Price.from_str(f"{stop_level:.2f}"),
        )
        self.submit_order(sl)
        self._placed_stop = stop_level
        self._exits_placed = True
