"""
BOT A — Opening Range Breakout (master plan §2), first implementation.

Every rule choice the master plan leaves open is an explicit config
parameter below, with the current default marked. Defaults are starting
points for Esura's decisions, NOT validated strategy rules:

  or_minutes .......... 30      (DECISION: 5 / 15 / 30 / 60 are all common)
  break_buffer_ticks .. 0       (close must clear the range edge by this much)
  require_retest ...... False   (DECISION: plan says "preferably" a retest)
  stop_mode ........... "opposite_edge"  (DECISION: or "midpoint")
  target_r_multiple ... 2.0     (DECISION: target = this x initial risk)
  vwap_filter ......... False   (DECISION: plan lists VWAP as a filter to test)
  risk_per_trade_usd .. 100     (placeholder sizing for plumbing tests)
  max_trades_per_day .. 1

Exits are managed as manual OCO: a stop-market at the invalidation level
and a limit at the target; whichever fills first cancels the other, and
any open position is flattened at FLATTEN_TIME.
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


class OrbConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    or_minutes: int = 30
    session_open: str = "09:30"
    flatten_time: str = "15:59"
    break_buffer_ticks: int = 0
    tick_size: float = 0.25
    multiplier: int = 2
    require_retest: bool = False
    stop_mode: str = "opposite_edge"
    target_r_multiple: float = 2.0
    vwap_filter: bool = False
    risk_per_trade_usd: float = 100.0
    max_contracts: int = 10
    max_trades_per_day: int = 1
    use_controller: bool = False
    # Research-challenge sizing (section 5): risk_fraction > 0 switches
    # from the fixed-dollar placeholder to dynamic % of current equity.
    risk_fraction: float = 0.0
    round_trip_cost_usd: float = 2.0
    margin_init_pct: float = 0.05
    margin_fraction_cap: float = 0.9
    target_r_override: float = 0.0
    # Noise-area breakout (Zarattini-Aziz style): when > 0, the break
    # buffer is this fraction of the trailing 5-session average RTH
    # range instead of the fixed tick buffer.
    noise_buffer_frac: float = 0.0


class OpeningRangeBreakout(Strategy):
    def __init__(self, config: OrbConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._equity_now: float | None = None
        self._rth_widths: list[float] = []
        self._reset_day(None)

    # -- day state ------------------------------------------------------------
    def _reset_day(self, day) -> None:
        self._day = day
        self._or_high: float | None = None
        self._or_low: float | None = None
        self._or_done = False
        self._trades_today = 0
        self._await_retest: int = 0          # +1 long, -1 short, 0 none
        self._pending_stop: float | None = None
        self._pending_target: float | None = None
        self._exits_placed = False
        self._pv = 0.0                        # VWAP accumulators
        self._vol = 0.0
        self._rth_high: float | None = None   # full-RTH range tracking
        self._rth_low: float | None = None    # (for the noise buffer)

    # -- lifecycle --------------------------------------------------------------
    def on_start(self) -> None:
        self.subscribe_bars(self._bar_type)

    def on_stop(self) -> None:
        self.cancel_all_orders(self._instrument_id)
        self.close_all_positions(self._instrument_id)
        self.unsubscribe_bars(self._bar_type)

    def on_position_closed(self, event: PositionClosed) -> None:
        # OCO: one exit filled -> cancel whatever is still working.
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
            REGISTRY.record_close("A", pnl, now)

    # -- main loop ---------------------------------------------------------------
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
        self._pv += ((high + low + close) / 3.0) * vol
        self._vol += vol
        vwap = self._pv / self._vol if self._vol > 0 else close
        if self._open_t <= t <= self._flatten_t:
            self._rth_high = high if self._rth_high is None else max(self._rth_high, high)
            self._rth_low = low if self._rth_low is None else min(self._rth_low, low)

        from datetime import datetime as _dt, timedelta as _td
        or_end = (_dt.combine(day, self._open_t) + _td(minutes=self.config.or_minutes)).time()

        flat = self.portfolio.is_flat(self._instrument_id)

        # Manage exits for an open position (place SL/TP once, right after entry fill)
        if not flat and not self._exits_placed and self._pending_stop is not None:
            self._place_exits()
        # Flatten at the close
        if t >= self._flatten_t:
            if not flat:
                self.cancel_all_orders(self._instrument_id)
                self.close_all_positions(self._instrument_id)
            return

        # Build the opening range
        if self._open_t <= t < or_end:
            self._or_high = high if self._or_high is None else max(self._or_high, high)
            self._or_low = low if self._or_low is None else min(self._or_low, low)
            return
        if t >= or_end and self._or_high is not None:
            self._or_done = True
        if not self._or_done or not flat or self._trades_today >= self.config.max_trades_per_day:
            return
        if self.cache.orders_inflight(strategy_id=self.id):
            return

        buffer = self._break_buffer()
        rng = self._or_high - self._or_low
        if rng <= 0:
            return

        direction = 0
        if close > self._or_high + buffer:
            direction = +1
        elif close < self._or_low - buffer:
            direction = -1

        if self.config.require_retest:
            if self._await_retest == 0:
                if direction != 0:
                    self._await_retest = direction
                return
            direction = self._await_retest
            touched = (low <= self._or_high) if direction > 0 else (high >= self._or_low)
            ran_away = (close > self._or_high + rng) if direction > 0 else (close < self._or_low - rng)
            if ran_away:
                self._await_retest = 0
                return
            reclaimed = (close > self._or_high) if direction > 0 else (close < self._or_low)
            if not (touched and reclaimed):
                return
            self._await_retest = 0
        elif direction == 0:
            return

        if self.config.vwap_filter:
            if direction > 0 and close < vwap:
                return
            if direction < 0 and close > vwap:
                return

        # Stop = invalidation level; target = R multiple of the stop distance.
        if direction > 0:
            entry_ref = self._or_high
            stop = self._or_low if self.config.stop_mode == "opposite_edge" else (self._or_high + self._or_low) / 2.0
        else:
            entry_ref = self._or_low
            stop = self._or_high if self.config.stop_mode == "opposite_edge" else (self._or_high + self._or_low) / 2.0
        risk_points = abs(entry_ref - stop)
        if risk_points <= 0:
            return
        r_mult = self.config.target_r_override if self.config.target_r_override > 0 else self.config.target_r_multiple
        target = entry_ref + direction * r_mult * risk_points

        if self.config.use_controller and not REGISTRY.allow_entry("A", ts):
            return

        if self.config.risk_fraction > 0:
            if not self._equity_now:
                return
            budget = self.config.risk_fraction * self._equity_now
        else:
            budget = self.config.risk_per_trade_usd
        qty = contract_qty(budget, risk_points, self.config.multiplier,
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
            REGISTRY.record_entry("A", ts)

    def _break_buffer(self) -> float:
        if self.config.noise_buffer_frac > 0 and self._rth_widths:
            hist = self._rth_widths[-5:]
            return self.config.noise_buffer_frac * (sum(hist) / len(hist))
        return self.config.break_buffer_ticks * self.config.tick_size

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
