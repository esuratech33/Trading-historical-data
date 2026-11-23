"""
BOT R — Overnight Gap Continuation / Fade (payout-sprint research,
2026-11-23).

BRAND-NEW strategy family for this project, FIXED rules as specified —
nothing tuned on the sample. One class, two modes (config `mode`):

  * Gap = today's 09:30 bar open minus the prior trading day's last
    RTH close (last bar at or before 16:00 ET). No trade unless
    |gap| >= 10 pts.
  * First-5-minute range = high/low of the 09:30-09:34 bars.
  * CONTINUATION mode: gap >= +10 -> LONG on the first close above
    the first-5 high; gap <= -10 -> SHORT on the first close below
    the first-5 low.
  * FADE mode: gap >= +10 -> SHORT on the first close below the
    first-5 low; gap <= -10 -> LONG on the first close above the
    first-5 high.
  * Stop: the OPPOSITE edge of the first-5 range from the entry
    trigger (structural). Target: 1.5R. Max 1 trade/day.
  * Entries 09:35-10:30 ET only; any open position is flattened at
    11:00 ET — the strategy trades the first 90 minutes only.

House style follows Bots A/B (stop-market + limit OCO placed after
the entry fill; cancel the sibling on close).
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


class BotRGapConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    mode: str = "continuation"          # or "fade"
    session_open: str = "09:30"
    entry_end: str = "10:30"
    flatten_time: str = "11:00"
    gap_threshold_points: float = 10.0
    target_r_multiple: float = 1.5
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


class BotRGap(Strategy):
    def __init__(self, config: BotRGapConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._entry_end_t = _parse_hhmm(config.entry_end)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._equity_now: float | None = None
        self._prev_rth_close: float | None = None   # prior day's last RTH close
        self._today_rth_close: float | None = None
        self._pending_stop: float | None = None
        self._pending_target: float | None = None
        self._exits_placed = False
        self._reset_day(None)

    def _reset_day(self, day) -> None:
        self._day = day
        self._trades_today = 0
        self._today_open: float | None = None
        self._gap: float | None = None
        self._f5_high: float | None = None
        self._f5_low: float | None = None
        self._f5_done = False

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
            REGISTRY.record_close("R", pnl, now)

    def on_bar(self, bar: Bar) -> None:
        ts = datetime.fromtimestamp(bar.ts_event / 1e9, tz=timezone.utc).astimezone(ET)
        day = ts.date()
        t = ts.time()
        if day != self._day:
            self._prev_rth_close = self._today_rth_close
            self._today_rth_close = None
            self._reset_day(day)
        self._equity_now = read_equity_usd(self)
        if self.config.use_controller and self._equity_now is not None:
            REGISTRY.update_equity(self._equity_now, ts)

        close = float(bar.close)
        high = float(bar.high)
        low = float(bar.low)
        opn = float(bar.open)

        if self._open_t <= t <= time(16, 0):
            self._today_rth_close = close

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

        # Today's open + gap (first RTH bar of the day)
        if self._today_open is None:
            self._today_open = opn
            if self._prev_rth_close is not None:
                self._gap = self._today_open - self._prev_rth_close
        # First-5-minute range: bars stamped 09:30..09:34
        if t < time(9, 35):
            self._f5_high = high if self._f5_high is None else max(self._f5_high, high)
            self._f5_low = low if self._f5_low is None else min(self._f5_low, low)
            return
        self._f5_done = True
        if self._gap is None or abs(self._gap) < self.config.gap_threshold_points:
            return
        if not flat or self.cache.orders_inflight(strategy_id=self.id):
            return
        if self._trades_today >= self.config.max_trades_per_day:
            return
        if t > self._entry_end_t or self._f5_high is None:
            return

        gap_up = self._gap > 0
        cont = self.config.mode == "continuation"
        direction = 0
        stop = None
        if cont:
            if gap_up and close > self._f5_high:
                direction, stop = 1, self._f5_low
            elif not gap_up and close < self._f5_low:
                direction, stop = -1, self._f5_high
        else:
            if gap_up and close < self._f5_low:
                direction, stop = -1, self._f5_high
            elif not gap_up and close > self._f5_high:
                direction, stop = 1, self._f5_low
        if direction == 0:
            return
        risk = abs(close - stop)
        if risk <= 0:
            return
        target = close + direction * self.config.target_r_multiple * risk
        if self.config.use_controller and not REGISTRY.allow_entry("R", ts):
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
            REGISTRY.record_entry("R", ts)

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
