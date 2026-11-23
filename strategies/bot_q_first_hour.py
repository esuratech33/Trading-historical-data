"""
BOT Q — First-Hour Momentum Continuation (payout-sprint research,
2026-11-23).

BRAND-NEW strategy family for this project, FIXED rules as specified —
nothing tuned on the sample:

  * First hour = 09:30-10:30 ET. Track its high and low.
  * After 10:30, a 1-minute CLOSE above the first-hour high enters
    LONG; a close below the first-hour low enters SHORT. While flat,
    any later close beyond either edge can enter again (continuation
    re-breaks), max 2 entries/day. Entries until 14:30 ET.
  * Initial stop: 1.0 x ATR(14) (1-minute Wilder) beyond the entry
    close, against the position.
  * Trailing stop: chandelier 2.0 x ATR (frozen at entry) from the
    best price since entry; effective stop is the initial stop until
    the chandelier moves past it, then only tightens. NO fixed
    profit target.
  * Flat by 15:55 ET.

Conventions: Wilder ATR seeded with the first TR, persists across
days. House style follows Bots B/K.
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


class BotQFirstHourConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    session_open: str = "09:30"
    first_hour_end: str = "10:30"
    entry_end: str = "14:30"
    flatten_time: str = "15:55"
    atr_period: int = 14
    initial_stop_atr: float = 1.0
    trail_atr: float = 2.0
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


class BotQFirstHour(Strategy):
    def __init__(self, config: BotQFirstHourConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._fh_end_t = _parse_hhmm(config.first_hour_end)
        self._entry_end_t = _parse_hhmm(config.entry_end)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._equity_now: float | None = None
        self._atr: float | None = None
        self._prev_close: float | None = None
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
        self._fh_high: float | None = None
        self._fh_low: float | None = None

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
            REGISTRY.record_close("Q", pnl, now)

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

        flat = self.portfolio.is_flat(self._instrument_id)
        if not flat:
            self._manage_position(high, low)
        if t >= self._flatten_t:
            if not flat:
                self.cancel_all_orders(self._instrument_id)
                self.close_all_positions(self._instrument_id)
            self._prev_close = close
            return
        if not (self._open_t <= t <= time(16, 0)):
            self._prev_close = close
            return

        # ATR (RTH bars only, Wilder, persists across days)
        if self._prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
        n = self.config.atr_period
        self._atr = tr if self._atr is None else (self._atr * (n - 1) + tr) / n
        self._prev_close = close

        # Build the first-hour range
        if self._open_t <= t < self._fh_end_t:
            self._fh_high = high if self._fh_high is None else max(self._fh_high, high)
            self._fh_low = low if self._fh_low is None else min(self._fh_low, low)
            return
        if t < self._fh_end_t or self._fh_high is None or not self._atr:
            return
        if not flat or self.cache.orders_inflight(strategy_id=self.id):
            return
        if self._trades_today >= self.config.max_trades_per_day:
            return
        if t > self._entry_end_t:
            return

        direction = 0
        if close > self._fh_high:
            direction = 1
        elif close < self._fh_low:
            direction = -1
        if direction == 0:
            return
        stop_dist = self.config.initial_stop_atr * self._atr
        if stop_dist <= 0:
            return
        if self.config.use_controller and not REGISTRY.allow_entry("Q", ts):
            return
        if self.config.risk_fraction > 0:
            if not self._equity_now:
                return
            budget = self.config.risk_fraction * self._equity_now
        else:
            budget = self.config.risk_per_trade_usd
        qty = contract_qty(budget, stop_dist, self.config.multiplier,
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
        self._init_stop = close - direction * stop_dist
        self._placed_stop = None
        self._exits_placed = False
        self.submit_order(order)
        self._trades_today += 1
        if self.config.use_controller:
            REGISTRY.record_entry("Q", ts)

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
