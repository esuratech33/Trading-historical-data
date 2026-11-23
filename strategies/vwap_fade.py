"""
BOT D — VWAP Snapback Fade (hypothesis round, 2026-11-20).

NEW strategy, designed for the prop-survival portfolio. Inspired by the
published "RubberBand" VWAP-snapback concept (TradingView prop-eval
combo, Oct 2026) and by the challenge finding that this portfolio earns
in sideways conditions: fade statistically stretched moves back toward
the session VWAP, but only on a reclaim trigger (never catch the first
stretch).

Rules (v1 defaults, all labeled, none optimized):
  * Session VWAP accumulates over RTH bars only (09:30 ET on).
  * Extension threshold = 0.35 x mean of the last 5 sessions' RTH
    ranges (fallback 40 pts until history exists).
  * ARM short when a close reaches VWAP + threshold; track the extreme.
    ENTER short on the first close back at or below VWAP + 0.5 x
    threshold. Mirror for longs below VWAP.
  * Stop = extension extreme + 2 ticks. Skip if risk < 3 or > 45 pts.
  * Target = session VWAP, capped at 2R; skip unless the target is at
    least 0.75R away.
  * Entries 10:00-15:30 ET only, max 2 trades/day, 30-minute cooldown
    after any close, flatten 15:59 ET. Manual OCO exits like the
    other bots.
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


class VwapFadeConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    session_open: str = "09:30"
    flatten_time: str = "15:59"
    arm_from: str = "09:45"
    entry_start: str = "10:00"
    entry_end: str = "15:30"
    tick_size: float = 0.25
    multiplier: int = 2
    extension_frac: float = 0.35
    fallback_extension_points: float = 40.0
    reclaim_frac: float = 0.5
    stop_buffer_ticks: int = 2
    min_risk_points: float = 3.0
    max_risk_points: float = 45.0
    target_r_cap: float = 2.0
    min_reward_r: float = 0.75
    cooldown_minutes: int = 30
    risk_per_trade_usd: float = 100.0
    max_contracts: int = 10
    max_trades_per_day: int = 2
    use_controller: bool = False
    risk_fraction: float = 0.0
    round_trip_cost_usd: float = 2.0
    margin_init_pct: float = 0.05
    margin_fraction_cap: float = 0.9


class VwapFade(Strategy):
    def __init__(self, config: VwapFadeConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._arm_t = _parse_hhmm(config.arm_from)
        self._start_t = _parse_hhmm(config.entry_start)
        self._end_t = _parse_hhmm(config.entry_end)
        self._equity_now: float | None = None
        self._rth_widths: list[float] = []
        self._last_close_dt: datetime | None = None
        self._reset_day(None)

    def _reset_day(self, day) -> None:
        self._day = day
        self._trades_today = 0
        self._armed = 0                       # +1 stretched up (fade short), -1 stretched down
        self._extreme: float | None = None
        self._pending_stop: float | None = None
        self._pending_target: float | None = None
        self._exits_placed = False
        self._pv = 0.0
        self._vol = 0.0
        self._rth_high: float | None = None
        self._rth_low: float | None = None

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
        now = datetime.fromtimestamp(event.ts_event / 1e9, tz=timezone.utc).astimezone(ET)
        self._last_close_dt = now
        if self.config.use_controller:
            try:
                pnl = event.realized_pnl.as_double()
            except Exception:
                pnl = 0.0
            REGISTRY.record_close("D", pnl, now)

    def _threshold(self) -> float:
        if self._rth_widths:
            hist = self._rth_widths[-5:]
            return self.config.extension_frac * (sum(hist) / len(hist))
        return self.config.fallback_extension_points

    def on_bar(self, bar: Bar) -> None:
        ts = datetime.fromtimestamp(bar.ts_event / 1e9, tz=timezone.utc).astimezone(ET)
        day = ts.date()
        t = ts.time()
        if day != self._day:
            if self._day is not None and self._rth_high is not None and self._rth_low is not None:
                self._rth_widths.append(self._rth_high - self._rth_low)
                self._rth_widths = self._rth_widths[-20:]
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
        if t < self._open_t:
            return

        # RTH-only accumulators from here on.
        self._pv += ((high + low + close) / 3.0) * vol
        self._vol += vol
        self._rth_high = high if self._rth_high is None else max(self._rth_high, high)
        self._rth_low = low if self._rth_low is None else min(self._rth_low, low)
        if self._vol <= 0:
            return
        vwap = self._pv / self._vol
        threshold = self._threshold()

        if not flat or self._trades_today >= self.config.max_trades_per_day:
            return
        if self.cache.orders_inflight(strategy_id=self.id):
            return
        if t < self._arm_t:
            return
        if self._last_close_dt is not None and self._last_close_dt.date() == day:
            if (ts - self._last_close_dt).total_seconds() < self.config.cooldown_minutes * 60:
                return

        # Arm on extension.
        if self._armed == 0:
            if close >= vwap + threshold:
                self._armed = 1
                self._extreme = high
            elif close <= vwap - threshold:
                self._armed = -1
                self._extreme = low
            return

        # Track the extreme while armed.
        if self._armed == 1:
            self._extreme = max(self._extreme, high)
        else:
            self._extreme = min(self._extreme, low)

        if not (self._start_t <= t <= self._end_t):
            return

        # Reclaim trigger.
        direction = 0
        if self._armed == 1 and close <= vwap + self.config.reclaim_frac * threshold:
            direction = -1  # short the snapback
        elif self._armed == -1 and close >= vwap - self.config.reclaim_frac * threshold:
            direction = 1   # long the snapback
        if direction == 0:
            return

        buffer = self.config.stop_buffer_ticks * self.config.tick_size
        if direction == -1:
            stop = self._extreme + buffer
            risk = stop - close
        else:
            stop = self._extreme - buffer
            risk = close - stop
        # Setup is consumed whether or not it is tradeable.
        self._armed = 0
        self._extreme = None
        if not (self.config.min_risk_points <= risk <= self.config.max_risk_points):
            return
        target_dist = min(abs(vwap - close), self.config.target_r_cap * risk)
        if target_dist < self.config.min_reward_r * risk:
            return
        target = close + direction * target_dist

        if self.config.use_controller and not REGISTRY.allow_entry("D", ts):
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
            REGISTRY.record_entry("D", ts)

    def _place_exits(self) -> None:
        positions = self.cache.positions_open(instrument_id=self._instrument_id)
        if not positions:
            return
        pos = positions[0]
        qty = Quantity.from_int(int(pos.quantity))
        if pos.side == PositionSide.LONG:
            sl = self.order_factory.stop_market(
                instrument_id=self._instrument_id,
                order_side=OrderSide.SELL,
                quantity=qty,
                trigger_price=Price.from_str(f"{self._pending_stop:.2f}"),
            )
            tp = self.order_factory.limit(
                instrument_id=self._instrument_id,
                order_side=OrderSide.SELL,
                quantity=qty,
                price=Price.from_str(f"{self._pending_target:.2f}"),
            )
        else:
            sl = self.order_factory.stop_market(
                instrument_id=self._instrument_id,
                order_side=OrderSide.BUY,
                quantity=qty,
                trigger_price=Price.from_str(f"{self._pending_stop:.2f}"),
            )
            tp = self.order_factory.limit(
                instrument_id=self._instrument_id,
                order_side=OrderSide.BUY,
                quantity=qty,
                price=Price.from_str(f"{self._pending_target:.2f}"),
            )
        self.submit_order(sl)
        self.submit_order(tp)
        self._exits_placed = True
