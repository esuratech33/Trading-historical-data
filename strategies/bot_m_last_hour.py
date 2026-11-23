"""
BOT M — Last-Hour Momentum (fast-pass research, 2026-11-22).

BRAND-NEW strategy family for this project, FIXED rules as specified —
nothing tuned on the sample:

  * At 15:00 ET, compute the day's move from the RTH open (09:30 bar
    open) to the 15:00 price (close of the 14:59 bar).
  * Qualify only if |day move| >= 0.8 x the median full-RTH-day range
    of the trailing 20 sessions AND the 14:30 -> 15:00 move (close of
    the 14:29 bar to the 15:00 price) agrees in direction.
  * Enter in the day's direction at 15:00. Stop = 12 points. NO
    profit target — the exit is the 15:55 ET flatten.
  * Max 1 trade/day, qualifying days only.

Conventions: trailing ranges use completed prior sessions only
(a minimum of 5 prior sessions is required before the median is
trusted — stated here because the spec fixes the lookback at 20 but
not the warmup; with fewer than 5 there is no trade). The entry is
submitted when the 15:00 bar arrives, so the fill lands on the next
1-minute bar like every other strategy in this project; the stop
reference is the 15:00 price (14:59 close).
"""

from datetime import datetime, time, timezone
from statistics import median
from zoneinfo import ZoneInfo

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
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


class BotMLastHourConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    session_open: str = "09:30"
    decision_time: str = "15:00"
    flatten_time: str = "15:55"
    range_lookback: int = 20
    min_prior_sessions: int = 5
    range_multiple: float = 0.8
    stop_points: float = 12.0
    tick_size: float = 0.25
    multiplier: int = 2
    risk_per_trade_usd: float = 100.0
    max_contracts: int = 10
    max_trades_per_day: int = 1
    use_controller: bool = False
    risk_fraction: float = 0.0
    round_trip_cost_usd: float = 2.0
    margin_init_pct: float = 0.05
    margin_fraction_cap: float = 0.9


class BotMLastHour(Strategy):
    def __init__(self, config: BotMLastHourConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._decision_t = _parse_hhmm(config.decision_time)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._equity_now: float | None = None
        self._rth_ranges: list[float] = []
        self._reset_day(None)

    def _reset_day(self, day) -> None:
        self._day = day
        self._trades_today = 0
        self._evaluated = False
        self._rth_open: float | None = None
        self._rth_high: float | None = None
        self._rth_low: float | None = None
        self._close_1430: float | None = None
        self._last_close: float | None = None
        self._pending_stop: float | None = None
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
        if self.config.use_controller:
            try:
                pnl = event.realized_pnl.as_double()
            except Exception:
                pnl = 0.0
            now = datetime.fromtimestamp(event.ts_event / 1e9, tz=timezone.utc).astimezone(ET)
            REGISTRY.record_close("M", pnl, now)

    # -- main loop --------------------------------------------------------------
    def on_bar(self, bar: Bar) -> None:
        ts = datetime.fromtimestamp(bar.ts_event / 1e9, tz=timezone.utc).astimezone(ET)
        day = ts.date()
        t = ts.time()
        if day != self._day:
            if self._day is not None and self._rth_high is not None and self._rth_low is not None:
                self._rth_ranges.append(self._rth_high - self._rth_low)
                self._rth_ranges = self._rth_ranges[-self.config.range_lookback:]
            self._reset_day(day)
        self._equity_now = read_equity_usd(self)
        if self.config.use_controller and self._equity_now is not None:
            REGISTRY.update_equity(self._equity_now, ts)

        close = float(bar.close)
        high = float(bar.high)
        low = float(bar.low)
        open_ = float(bar.open)

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

        # Track the RTH day.
        if self._rth_open is None:
            self._rth_open = open_
        self._rth_high = high if self._rth_high is None else max(self._rth_high, high)
        self._rth_low = low if self._rth_low is None else min(self._rth_low, low)
        if t == time(14, 29):
            self._close_1430 = close

        # 15:00 decision: uses closes through the 14:59 bar, which are
        # already stored before this bar's close is recorded.
        if not self._evaluated and t >= self._decision_t:
            self._evaluated = True
            self._evaluate(ts, flat)
        self._last_close = close

    def _evaluate(self, ts, flat) -> None:
        if self._last_close is None or self._rth_open is None or self._close_1430 is None:
            return
        if len(self._rth_ranges) < self.config.min_prior_sessions:
            return
        day_move = self._last_close - self._rth_open
        move_30 = self._last_close - self._close_1430
        threshold = self.config.range_multiple * median(self._rth_ranges)
        if abs(day_move) < threshold or day_move == 0:
            return
        if (move_30 > 0) != (day_move > 0) or move_30 == 0:
            return
        direction = 1 if day_move > 0 else -1
        if not flat or self.cache.orders_inflight(strategy_id=self.id):
            return
        if self._trades_today >= self.config.max_trades_per_day:
            return
        if self.config.use_controller and not REGISTRY.allow_entry("M", ts):
            return
        entry_ref = self._last_close
        if self.config.risk_fraction > 0:
            if not self._equity_now:
                return
            budget = self.config.risk_fraction * self._equity_now
        else:
            budget = self.config.risk_per_trade_usd
        qty = contract_qty(budget, self.config.stop_points, self.config.multiplier,
                           self.config.round_trip_cost_usd, self._equity_now,
                           entry_ref, self.config.margin_init_pct,
                           self.config.margin_fraction_cap, self.config.max_contracts)
        if qty < 1:
            return
        order = self.order_factory.market(
            instrument_id=self._instrument_id,
            order_side=OrderSide.BUY if direction > 0 else OrderSide.SELL,
            quantity=Quantity.from_int(qty),
        )
        self._pending_stop = entry_ref - direction * self.config.stop_points
        self._exits_placed = False
        self.submit_order(order)
        self._trades_today += 1
        if self.config.use_controller:
            REGISTRY.record_entry("M", ts)

    def _place_exits(self) -> None:
        positions = self.cache.positions_open(instrument_id=self._instrument_id)
        if not positions:
            return
        pos = positions[0]
        qty = Quantity.from_int(int(pos.quantity))
        from nautilus_trader.model.enums import PositionSide
        side = OrderSide.SELL if pos.side == PositionSide.LONG else OrderSide.BUY
        sl = self.order_factory.stop_market(
            instrument_id=self._instrument_id,
            order_side=side,
            quantity=qty,
            trigger_price=Price.from_str(f"{self._pending_stop:.2f}"),
        )
        self.submit_order(sl)
        self._exits_placed = True
