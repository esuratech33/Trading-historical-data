"""
BOT E — IBS Oversold Bounce (BRAND-NEW strategy, hypothesis round 2,
2026-11-20). Unrelated to Bots A-D: a daily-bar swing system.

Published basis: Internal Bar Strength mean reversion — one of the
strongest long-run performers in an independent 16-year NQ study
(IBS swing: PF 1.94, 575 trades, 2010-2026) and in the academic/
practitioner literature on short-term index overreaction.

Rules (as published, plus a prop-survival stop variant):
  * IBS = (close - low) / (high - low) of the daily bar.
  * BUY at the next open when a day closes with IBS <= 0.20 (the day
    closed in the bottom fifth of its range — sellers exhausted).
    Long only. One position at a time.
  * EXIT at the next open when a day closes with IBS >= 0.80, or at
    the 5th session's close if no bounce came (time stop).
  * Optional catastrophe stop (prop variant): entry - 2 x ATR(14),
    with position size from a fixed dollar risk budget.
  * Holds overnight and over weekends by design. Pairs naturally
    with end-of-day trailing-drawdown firms, whose limit only
    samples the closing balance.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, PositionSide
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from sizing import contract_qty, read_equity_usd

ET = ZoneInfo("America/New_York")


class IbsBounceConfig(StrategyConfig, frozen=True):
    instrument_id: str = "MNQM26.GLBX"
    bar_type: str = "MNQM26.GLBX-1-DAY-LAST-EXTERNAL"
    ibs_entry: float = 0.20
    ibs_exit: float = 0.80
    max_hold_sessions: int = 5
    tick_size: float = 0.25
    multiplier: int = 2
    fixed_contracts: int = 0          # >0: always this size (no-stop variants)
    use_atr_stop: bool = False
    atr_period: int = 14
    atr_stop_mult: float = 2.0
    risk_budget_usd: float = 750.0    # used when use_atr_stop and fixed_contracts == 0
    max_contracts: int = 10
    # Volatility circuit breaker (v2): skip NEW entries when ATR(14)
    # exceeds vol_gate_mult x the median ATR of the trailing
    # vol_gate_lookback sessions — buy quiet dips, never a storm.
    vol_gate_mult: float = 0.0
    vol_gate_lookback: int = 60
    vol_gate_min_history: int = 20
    round_trip_cost_usd: float = 2.0
    margin_init_pct: float = 0.05
    margin_fraction_cap: float = 0.9


class IbsBounce(Strategy):
    def __init__(self, config: IbsBounceConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._prev_close: float | None = None
        self._trs: list[float] = []
        self._atr: float | None = None
        self._atr_hist: list[float] = []
        self._sessions_held = 0
        self._pending_stop: float | None = None
        self._exits_placed = False
        self._equity_now: float | None = None

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
        self._sessions_held = 0

    def on_bar(self, bar: Bar) -> None:
        close = float(bar.close)
        high = float(bar.high)
        low = float(bar.low)
        self._equity_now = read_equity_usd(self)

        # ATR(14) on true ranges, known at this bar's close.
        if self._prev_close is not None:
            tr = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
            self._trs.append(tr)
            if len(self._trs) >= self.config.atr_period:
                self._atr = sum(self._trs[-self.config.atr_period:]) / self.config.atr_period
                self._atr_hist.append(self._atr)
        self._prev_close = close

        rng = high - low
        if rng <= 0:
            return
        ibs = (close - low) / rng
        flat = self.portfolio.is_flat(self._instrument_id)

        if not flat:
            if not self._exits_placed and self._pending_stop is not None:
                self._place_stop()
            self._sessions_held += 1
            if ibs >= self.config.ibs_exit or self._sessions_held >= self.config.max_hold_sessions:
                self.cancel_all_orders(self._instrument_id)
                self.close_all_positions(self._instrument_id)
            return

        if self.cache.orders_inflight(strategy_id=self.id):
            return
        if ibs > self.config.ibs_entry:
            return
        if self.config.vol_gate_mult > 0 and self._atr is not None \
                and len(self._atr_hist) >= self.config.vol_gate_min_history:
            hist = sorted(self._atr_hist[-self.config.vol_gate_lookback:])
            median_atr = hist[len(hist) // 2]
            if self._atr > self.config.vol_gate_mult * median_atr:
                return  # volatility storm: stand down

        # Entry signal: oversold close. Fill comes at the next bar open.
        stop = None
        if self.config.use_atr_stop:
            if self._atr is None:
                return
            stop = close - self.config.atr_stop_mult * self._atr
            risk = close - stop
            qty = contract_qty(self.config.risk_budget_usd, risk, self.config.multiplier,
                               self.config.round_trip_cost_usd, self._equity_now,
                               close, self.config.margin_init_pct,
                               self.config.margin_fraction_cap, self.config.max_contracts)
        elif self.config.fixed_contracts > 0:
            qty = self.config.fixed_contracts
        else:
            return
        if qty < 1:
            return
        order = self.order_factory.market(
            instrument_id=self._instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity.from_int(qty),
        )
        self._pending_stop = stop
        self._exits_placed = False
        self._sessions_held = 0
        self.submit_order(order)

    def _place_stop(self) -> None:
        positions = self.cache.positions_open(instrument_id=self._instrument_id)
        if not positions:
            return
        pos = positions[0]
        if pos.side != PositionSide.LONG:
            return
        sl = self.order_factory.stop_market(
            instrument_id=self._instrument_id,
            order_side=OrderSide.SELL,
            quantity=Quantity.from_int(int(pos.quantity)),
            trigger_price=Price.from_str(f"{self._pending_stop:.2f}"),
        )
        self.submit_order(sl)
        self._exits_placed = True
