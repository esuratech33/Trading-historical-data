"""
BOT F — MNQ Momentum Scalper (hundred-dollar-day research, 2026-11-22).

NEW strategy, FIXED rules as specified for the $100/day test — nothing
tuned on the sample:

  * 5-minute bars aggregated from the 1-minute feed, RTH only.
  * Long when EMA(9) crosses above EMA(21) on a completed 5-minute bar
    AND that bar's close is above session VWAP. Short mirrored (cross
    down + close below VWAP). Indicators seeded/updated exactly like
    Bot B (recursive EMA seeded with the first close; VWAP from
    1-minute typical price x volume, reset daily).
  * Stop = 1.0 x ATR(14) of the 5-minute bars (Wilder). SKIP the trade
    if the ATR stop would exceed 8 points (volatility too high for the
    design) or is under 3 points (conventional minimum, same as Bot B).
  * Target = 1.5R. Max 6 entries/day. No entries after 15:30 ET.
    Flat by 15:55 ET. Manual OCO exits like the other bots.
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


class MomentumScalpConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    session_open: str = "09:30"
    entry_start: str = "09:35"
    entry_end: str = "15:30"
    flatten_time: str = "15:55"
    ema_fast: int = 9
    ema_slow: int = 21
    atr_period: int = 14
    atr_stop_multiple: float = 1.0
    max_stop_points: float = 8.0
    min_stop_points: float = 3.0
    target_r_multiple: float = 1.5
    tick_size: float = 0.25
    multiplier: int = 2
    risk_per_trade_usd: float = 100.0
    max_contracts: int = 10
    max_trades_per_day: int = 6
    use_controller: bool = False
    risk_fraction: float = 0.0
    round_trip_cost_usd: float = 2.0
    margin_init_pct: float = 0.05
    margin_fraction_cap: float = 0.9


class MomentumScalp(Strategy):
    def __init__(self, config: MomentumScalpConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._entry_start_t = _parse_hhmm(config.entry_start)
        self._entry_end_t = _parse_hhmm(config.entry_end)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._equity_now: float | None = None
        # 5-minute aggregation state (persists across days, like Bot B's EMAs)
        self._bucket = None            # datetime of the open 5-min bucket (ET)
        self._b_open = self._b_high = self._b_low = self._b_close = None
        self._ema_fast: float | None = None
        self._ema_slow: float | None = None
        self._prev_ema_fast: float | None = None
        self._prev_ema_slow: float | None = None
        self._atr: float | None = None
        self._prev_5m_close: float | None = None
        self._reset_day(None)

    def _reset_day(self, day) -> None:
        self._day = day
        self._trades_today = 0
        self._pv = 0.0
        self._vol = 0.0
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
            REGISTRY.record_close("F", pnl, now)

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

        # Session VWAP from 1-minute bars (typical price), RTH only.
        self._pv += ((high + low + close) / 3.0) * vol
        self._vol += vol
        vwap = self._pv / self._vol if self._vol > 0 else close

        # Aggregate into 5-minute bars; a bucket completes when the
        # first bar of the next bucket arrives.
        bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        if self._bucket is None:
            self._bucket = bucket
            self._b_open = self._b_high = self._b_low = self._b_close = close
            self._b_high, self._b_low = high, low
            return
        if bucket == self._bucket:
            self._b_high = max(self._b_high, high)
            self._b_low = min(self._b_low, low)
            self._b_close = close
            return
        # Previous bucket just completed.
        c5, h5, l5 = self._b_close, self._b_high, self._b_low
        self._bucket = bucket
        self._b_open = self._b_high = self._b_low = self._b_close = close
        self._b_high, self._b_low = high, low
        self._on_5m_close(ts, c5, h5, l5, vwap, flat)

    def _on_5m_close(self, ts, c5, h5, l5, vwap, flat) -> None:
        t = ts.time()
        # Indicators on the completed 5-minute bar.
        self._prev_ema_fast, self._prev_ema_slow = self._ema_fast, self._ema_slow
        kf = 2.0 / (self.config.ema_fast + 1)
        ks = 2.0 / (self.config.ema_slow + 1)
        self._ema_fast = c5 if self._ema_fast is None else c5 * kf + self._ema_fast * (1 - kf)
        self._ema_slow = c5 if self._ema_slow is None else c5 * ks + self._ema_slow * (1 - ks)
        if self._prev_5m_close is None:
            tr = h5 - l5
        else:
            tr = max(h5 - l5, abs(h5 - self._prev_5m_close), abs(l5 - self._prev_5m_close))
        n = self.config.atr_period
        self._atr = tr if self._atr is None else (self._atr * (n - 1) + tr) / n
        self._prev_5m_close = c5

        if self._prev_ema_fast is None or self._prev_ema_slow is None or self._atr is None:
            return
        cross_up = self._prev_ema_fast <= self._prev_ema_slow and self._ema_fast > self._ema_slow
        cross_dn = self._prev_ema_fast >= self._prev_ema_slow and self._ema_fast < self._ema_slow
        direction = 0
        if cross_up and c5 > vwap:
            direction = 1
        elif cross_dn and c5 < vwap:
            direction = -1
        if direction == 0:
            return
        if not flat or self.cache.orders_inflight(strategy_id=self.id):
            return
        if self._trades_today >= self.config.max_trades_per_day:
            return
        if not (self._entry_start_t <= t <= self._entry_end_t):
            return
        stop_dist = self.config.atr_stop_multiple * self._atr
        if stop_dist > self.config.max_stop_points or stop_dist < self.config.min_stop_points:
            return
        if self.config.use_controller and not REGISTRY.allow_entry("F", ts):
            return
        if self.config.risk_fraction > 0:
            if not self._equity_now:
                return
            budget = self.config.risk_fraction * self._equity_now
        else:
            budget = self.config.risk_per_trade_usd
        qty = contract_qty(budget, stop_dist, self.config.multiplier,
                           self.config.round_trip_cost_usd, self._equity_now,
                           c5, self.config.margin_init_pct,
                           self.config.margin_fraction_cap, self.config.max_contracts)
        if qty < 1:
            return
        stop = c5 - direction * stop_dist
        target = c5 + direction * self.config.target_r_multiple * stop_dist
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
            REGISTRY.record_entry("F", ts)

    def _place_exits(self) -> None:
        positions = self.cache.positions_open(instrument_id=self._instrument_id)
        if not positions:
            return
        pos = positions[0]
        qty = Quantity.from_int(int(pos.quantity))
        if pos.side == PositionSide.LONG:
            sl_side = tp_side = OrderSide.SELL
        else:
            sl_side = tp_side = OrderSide.BUY
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
