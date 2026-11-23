"""
BOT K — 15-Minute Trend Rider (fast-pass research, 2026-11-22).

BRAND-NEW strategy family for this project, FIXED rules as specified —
nothing tuned on the sample:

  * Direction from 15-minute bars aggregated from the 1-minute feed
    (RTH only): long only when the completed 15-min close is above
    EMA(50) of 15-min closes AND ADX(14) > 25; short mirrored.
  * Entry on a completed 15-min close that breaks the PRIOR 15-min
    bar's high (long) / low (short).
  * Initial stop = 1.0 x ATR(14) of 15-min bars (Wilder).
  * Chandelier trailing stop = 2.5 x ATR (ATR frozen at its entry-time
    value) from the best price since entry; the effective stop is the
    initial stop until the chandelier moves past it, and only ever
    tightens after that. NO fixed profit target.
  * Max 2 entries/day. Flat by 15:55 ET.

Conventions (project house style, same as Bots B/F): recursive EMA
seeded with the first close; Wilder ATR seeded with the first TR;
ADX is Wilder's: +DM/-DM/TR smoothed (seeded with the 14-bar sums),
DX from the smoothed DIs, ADX seeded as the mean of the first 14 DX
values then Wilder-smoothed. Indicator state persists across days;
signals are evaluated when a 15-min bucket completes (on the first
1-minute bar of the next bucket), and the entry/stop reference price
is the completed bar's close.
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


class BotKTrendRiderConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQZ26.GLBX"
    bar_type: str = "MNQZ26.GLBX-1-MINUTE-LAST-EXTERNAL"
    session_open: str = "09:30"
    flatten_time: str = "15:55"
    ema_period: int = 50
    adx_period: int = 14
    adx_threshold: float = 25.0
    atr_period: int = 14
    initial_stop_atr: float = 1.0
    chandelier_atr: float = 2.5
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


class BotKTrendRider(Strategy):
    def __init__(self, config: BotKTrendRiderConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._open_t = _parse_hhmm(config.session_open)
        self._flatten_t = _parse_hhmm(config.flatten_time)
        self._equity_now: float | None = None
        # 15-minute aggregation + indicator state (persists across days)
        self._bucket = None
        self._b_open = self._b_high = self._b_low = self._b_close = None
        self._prev_bar = None            # (open, high, low, close) of prior 15m bar
        self._ema: float | None = None
        self._atr: float | None = None
        self._prev_15m_close: float | None = None
        n = config.adx_period
        self._adx_seed_count = 0
        self._s_tr = self._s_pdm = self._s_ndm = None
        self._dx_hist: list[float] = []
        self._adx: float | None = None
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
            REGISTRY.record_close("K", pnl, now)

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
        if not flat:
            self._manage_position(high, low)
        if t >= self._flatten_t:
            if not flat:
                self.cancel_all_orders(self._instrument_id)
                self.close_all_positions(self._instrument_id)
            return
        if not (self._open_t <= t < time(16, 0)):
            return

        # Aggregate into 15-minute bars (RTH only).
        bucket = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
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
        # Previous bucket just completed.
        bar15 = (self._b_open, self._b_high, self._b_low, self._b_close)
        self._bucket = bucket
        self._b_open = close
        self._b_high, self._b_low, self._b_close = high, low, close
        self._on_15m_close(ts, bar15, flat)

    # -- indicators + signal ------------------------------------------------------
    def _on_15m_close(self, ts, bar15, flat) -> None:
        o, h, l, c = bar15
        prev = self._prev_bar
        # EMA(50) on 15-min closes (recursive, seeded with first close).
        k = 2.0 / (self.config.ema_period + 1)
        self._ema = c if self._ema is None else c * k + self._ema * (1 - k)
        # ATR + Wilder DM smoothing.
        if self._prev_15m_close is None:
            tr = h - l
            pdm = ndm = 0.0
        else:
            pc = self._prev_15m_close
            tr = max(h - l, abs(h - pc), abs(l - pc))
            up = h - prev[1] if prev is not None else 0.0
            dn = prev[2] - l if prev is not None else 0.0
            pdm = up if (up > dn and up > 0) else 0.0
            ndm = dn if (dn > up and dn > 0) else 0.0
        n = self.config.atr_period
        self._atr = tr if self._atr is None else (self._atr * (n - 1) + tr) / n
        # ADX (Wilder): seed the smoothed sums over the first n bars.
        if self._adx_seed_count < n:
            self._adx_seed_count += 1
            self._s_tr = (self._s_tr or 0.0) + tr
            self._s_pdm = (self._s_pdm or 0.0) + pdm
            self._s_ndm = (self._s_ndm or 0.0) + ndm
            if self._adx_seed_count < n:
                self._prev_15m_close = c
                self._prev_bar = bar15
                return
        else:
            self._s_tr = self._s_tr - self._s_tr / n + tr
            self._s_pdm = self._s_pdm - self._s_pdm / n + pdm
            self._s_ndm = self._s_ndm - self._s_ndm / n + ndm
        if self._s_tr and self._s_tr > 0:
            pdi = 100.0 * self._s_pdm / self._s_tr
            ndi = 100.0 * self._s_ndm / self._s_tr
            dx = 100.0 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) > 0 else 0.0
            if self._adx is None:
                self._dx_hist.append(dx)
                if len(self._dx_hist) >= n:
                    self._adx = sum(self._dx_hist) / len(self._dx_hist)
            else:
                self._adx = (self._adx * (n - 1) + dx) / n
        self._prev_15m_close = c

        # Signal.
        direction = 0
        if (prev is not None and self._adx is not None
                and self._adx > self.config.adx_threshold and self._atr):
            if c > self._ema and c > prev[1]:
                direction = 1
            elif c < self._ema and c < prev[2]:
                direction = -1
        self._prev_bar = bar15
        if direction == 0:
            return
        if not flat or self.cache.orders_inflight(strategy_id=self.id):
            return
        if self._trades_today >= self.config.max_trades_per_day:
            return
        stop_dist = self.config.initial_stop_atr * self._atr
        if stop_dist <= 0:
            return
        if self.config.use_controller and not REGISTRY.allow_entry("K", ts):
            return
        if self.config.risk_fraction > 0:
            if not self._equity_now:
                return
            budget = self.config.risk_fraction * self._equity_now
        else:
            budget = self.config.risk_per_trade_usd
        qty = contract_qty(budget, stop_dist, self.config.multiplier,
                           self.config.round_trip_cost_usd, self._equity_now,
                           c, self.config.margin_init_pct,
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
        self._best = c
        self._init_stop = c - direction * stop_dist
        self._placed_stop = None
        self._exits_placed = False
        self.submit_order(order)
        self._trades_today += 1
        if self.config.use_controller:
            REGISTRY.record_entry("K", ts)

    # -- trailing-stop management --------------------------------------------------
    def _manage_position(self, high: float, low: float) -> None:
        if self._dir == 0 or self._atr_entry is None:
            return
        if self._dir > 0:
            self._best = high if self._best is None else max(self._best, high)
            desired = max(self._init_stop, self._best - self.config.chandelier_atr * self._atr_entry)
        else:
            self._best = low if self._best is None else min(self._best, low)
            desired = min(self._init_stop, self._best + self.config.chandelier_atr * self._atr_entry)
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
