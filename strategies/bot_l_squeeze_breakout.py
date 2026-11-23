"""
BOT L — Squeeze Breakout (fast-pass research, 2026-11-22).

BRAND-NEW strategy family for this project, FIXED rules as specified —
nothing tuned on the sample:

  * 5-minute bars aggregated from the 1-minute feed (RTH only).
  * Squeeze ON for a completed 5-min bar when its Bollinger Bands
    (20 closes, 2.0 sigma, population stdev) lie fully inside its
    Keltner Channels (EMA(20) of closes +/- 1.5 x ATR(14), Wilder).
  * Entry: the immediately preceding completed bar was in squeeze and
    this bar closes OUTSIDE its own Bollinger band — above the upper
    band with the close in the top third of the bar's range (long),
    or below the lower band with the close in the bottom third
    (short).
  * Stop = midpoint of the squeeze episode's price range (highest
    high / lowest low across the consecutive squeeze bars that
    preceded the release bar).
  * Target = 2R. Max 2 entries/day. Flat by 15:55 ET.

Conventions (project house style): recursive EMA seeded with the
first close; Wilder ATR seeded with the first TR; signals evaluated
when a 5-min bucket completes; entry/stop/target reference price is
the completed bar's close. Manual OCO exits like the other bots.
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


class BotLSqueezeConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    session_open: str = "09:30"
    flatten_time: str = "15:55"
    bb_period: int = 20
    bb_mult: float = 2.0
    kc_ema_period: int = 20
    kc_atr_mult: float = 1.5
    atr_period: int = 14
    target_r_multiple: float = 2.0
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


class BotLSqueeze(Strategy):
    def __init__(self, config: BotLSqueezeConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._equity_now: float | None = None
        # 5-minute aggregation + indicator state (persists across days)
        self._bucket = None
        self._b_open = self._b_high = self._b_low = self._b_close = None
        self._closes: list[float] = []
        self._ema: float | None = None
        self._atr: float | None = None
        self._prev_5m_close: float | None = None
        # squeeze episode state
        self._prev_squeeze = False
        self._ep_high: float | None = None
        self._ep_low: float | None = None
        self._reset_day(None)

    def _reset_day(self, day) -> None:
        self._day = day
        self._trades_today = 0
        self._pending_stop: float | None = None
        self._pending_target: float | None = None
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
        self._pending_target = None
        if self.config.use_controller:
            try:
                pnl = event.realized_pnl.as_double()
            except Exception:
                pnl = 0.0
            now = datetime.fromtimestamp(event.ts_event / 1e9, tz=timezone.utc).astimezone(ET)
            REGISTRY.record_close("L", pnl, now)

    # -- main loop --------------------------------------------------------------
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
        if not flat and not self._exits_placed and self._pending_stop is not None:
            self._place_exits()
        if t >= self._flatten_t:
            if not flat:
                self.cancel_all_orders(self._instrument_id)
                self.close_all_positions(self._instrument_id)
            return
        if not (self._open_t <= t < time(16, 0)):
            return

        bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        if self._bucket is None:
            self._bucket = bucket
            self._b_open = close
            self._b_high, self._b_low, self._b_close = high, low, close
            return
        if bucket == self._bucket:
            self._b_high = max(self._b_high, high)
            self._b_low = min(self._b_low, low)
            self._b_close = close
            return
        bar5 = (self._b_open, self._b_high, self._b_low, self._b_close)
        self._bucket = bucket
        self._b_open = close
        self._b_high, self._b_low, self._b_close = high, low, close
        self._on_5m_close(ts, bar5, flat)

    # -- indicators + signal ------------------------------------------------------
    def _on_5m_close(self, ts, bar5, flat) -> None:
        o, h, l, c = bar5
        # ATR (Wilder) + EMA for the Keltner midline.
        if self._prev_5m_close is None:
            tr = h - l
        else:
            pc = self._prev_5m_close
            tr = max(h - l, abs(h - pc), abs(l - pc))
        n = self.config.atr_period
        self._atr = tr if self._atr is None else (self._atr * (n - 1) + tr) / n
        self._prev_5m_close = c
        kk = 2.0 / (self.config.kc_ema_period + 1)
        self._ema = c if self._ema is None else c * kk + self._ema * (1 - kk)
        self._closes.append(c)
        if len(self._closes) > self.config.bb_period:
            self._closes.pop(0)

        squeeze = False
        bb_up = bb_lo = None
        if len(self._closes) >= self.config.bb_period and self._atr is not None:
            m = sum(self._closes) / len(self._closes)
            var = sum((x - m) ** 2 for x in self._closes) / len(self._closes)
            sd = var ** 0.5
            bb_up = m + self.config.bb_mult * sd
            bb_lo = m - self.config.bb_mult * sd
            kc_up = self._ema + self.config.kc_atr_mult * self._atr
            kc_lo = self._ema - self.config.kc_atr_mult * self._atr
            squeeze = (bb_up < kc_up) and (bb_lo > kc_lo)

        # Entry: previous bar in squeeze, this bar closes outside its band.
        if self._prev_squeeze and bb_up is not None and self._ep_high is not None:
            rng = h - l
            direction = 0
            if c > bb_up and rng > 0 and c >= l + (2.0 / 3.0) * rng:
                direction = 1
            elif c < bb_lo and rng > 0 and c <= l + (1.0 / 3.0) * rng:
                direction = -1
            if direction != 0:
                self._enter(ts, direction, c, flat)

        # Episode bookkeeping: extend the running squeeze episode with
        # this bar if it is itself in squeeze, else close the episode.
        if squeeze:
            self._ep_high = h if self._ep_high is None else max(self._ep_high, h)
            self._ep_low = l if self._ep_low is None else min(self._ep_low, l)
        else:
            self._ep_high = None
            self._ep_low = None
        self._prev_squeeze = squeeze

    def _enter(self, ts, direction, close_ref, flat) -> None:
        if not flat or self.cache.orders_inflight(strategy_id=self.id):
            return
        if self._trades_today >= self.config.max_trades_per_day:
            return
        stop = (self._ep_high + self._ep_low) / 2.0
        risk_points = abs(close_ref - stop)
        if risk_points <= 0:
            return
        if (direction > 0 and stop >= close_ref) or (direction < 0 and stop <= close_ref):
            return
        if self.config.use_controller and not REGISTRY.allow_entry("L", ts):
            return
        if self.config.risk_fraction > 0:
            if not self._equity_now:
                return
            budget = self.config.risk_fraction * self._equity_now
        else:
            budget = self.config.risk_per_trade_usd
        qty = contract_qty(budget, risk_points, self.config.multiplier,
                           self.config.round_trip_cost_usd, self._equity_now,
                           close_ref, self.config.margin_init_pct,
                           self.config.margin_fraction_cap, self.config.max_contracts)
        if qty < 1:
            return
        target = close_ref + direction * self.config.target_r_multiple * risk_points
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
            REGISTRY.record_entry("L", ts)

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
