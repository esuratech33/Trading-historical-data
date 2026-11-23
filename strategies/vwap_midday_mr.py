"""
BOT G — Midday VWAP Mean Reversion (hundred-dollar-day research,
2026-11-22).

NEW strategy, FIXED rules as specified for the $100/day test — nothing
tuned on the sample. (Bot D's vwap_fade.py does not support standard-
deviation bands — it uses a range-fraction extension with a reclaim
trigger — so this is implemented simply, per the test spec.)

  * Session VWAP and sigma accumulate over RTH 1-minute bars from
    09:30 ET, volume-weighted on typical price:
        VWAP = sum(v*tp)/sum(v),  sigma = sqrt(sum(v*tp^2)/sum(v) - VWAP^2).
  * Entries ONLY 12:00-14:00 ET: fade a bar close that extends
    >= 2 sigma from VWAP — close >= VWAP + 2 sigma -> short,
    close <= VWAP - 2 sigma -> long.
  * Stop = 10 points from the entry reference (the signalling close).
    Target = session VWAP at entry. Max 3 entries/day.
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


class VwapMiddayMrConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    session_open: str = "09:30"
    entry_start: str = "12:00"
    entry_end: str = "14:00"
    flatten_time: str = "15:55"
    band_sigma: float = 2.0
    stop_points: float = 10.0
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


class VwapMiddayMr(Strategy):
    def __init__(self, config: VwapMiddayMrConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._start_t = _parse_hhmm(config.entry_start)
        self._end_t = _parse_hhmm(config.entry_end)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._equity_now: float | None = None
        self._reset_day(None)

    def _reset_day(self, day) -> None:
        self._day = day
        self._trades_today = 0
        self._sv = 0.0        # sum of volume
        self._svp = 0.0       # sum of volume * typical price
        self._svp2 = 0.0      # sum of volume * typical price^2
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
            REGISTRY.record_close("G", pnl, now)

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

        tp = (high + low + close) / 3.0
        self._sv += vol
        self._svp += vol * tp
        self._svp2 += vol * tp * tp
        if self._sv <= 0:
            return
        vwap = self._svp / self._sv
        var = self._svp2 / self._sv - vwap * vwap
        sigma = var ** 0.5 if var > 0 else 0.0

        if not (self._start_t <= t <= self._end_t):
            return
        if not flat or self._trades_today >= self.config.max_trades_per_day:
            return
        if self.cache.orders_inflight(strategy_id=self.id):
            return
        if sigma <= 0:
            return
        band = self.config.band_sigma * sigma
        direction = 0
        if close >= vwap + band:
            direction = -1
        elif close <= vwap - band:
            direction = 1
        if direction == 0:
            return

        stop_dist = self.config.stop_points
        stop = close - direction * stop_dist
        target = vwap
        if self.config.use_controller and not REGISTRY.allow_entry("G", ts):
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
        self._pending_stop = stop
        self._pending_target = target
        self._exits_placed = False
        self.submit_order(order)
        self._trades_today += 1
        if self.config.use_controller:
            REGISTRY.record_entry("G", ts)

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
