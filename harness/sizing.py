"""
Risk-based position sizing (research challenge §5).

Contracts = Floor(Available Dollar Risk /
                  (Stop Distance in Points x $2 + Round-Trip Cost/Contract))

Additional ceilings, both required by the challenge:
* the portfolio combined open-risk ceiling is enforced by the caller
  (with one position open at a time, the per-trade budget IS the
  combined budget);
* a margin ceiling: quantity may not require more than
  `margin_fraction_cap` of current equity as initial margin
  (exposure is controlled through stop-loss risk, equity, and margin
  requirements — not an arbitrary notional cap).

Returns 0 when one contract does not fit inside the risk budget —
the trade is skipped, never rounded up beyond the budget.
"""


def read_equity_usd(strategy) -> float | None:
    """Current account equity (realized + unrealized) in USD.

    Nautilus' Portfolio.equity() returns a {Currency: Money} dict;
    this unwraps it. Returns None if equity cannot be read.
    """
    try:
        from nautilus_trader.model.identifiers import Venue

        iid = strategy.config.instrument_id
        venue = iid.venue if hasattr(iid, "venue") else Venue(str(iid).rsplit(".", 1)[-1])
        eq = strategy.portfolio.equity(venue)
        if eq is None:
            return None
        if isinstance(eq, dict):
            if not eq:
                return None
            eq = next(iter(eq.values()))
        return float(eq.as_double())
    except Exception:
        return None


def contract_qty(
    budget_usd: float,
    stop_points: float,
    multiplier: int,
    round_trip_cost_usd: float,
    equity_usd: float | None,
    price: float | None,
    margin_init_pct: float,
    margin_fraction_cap: float,
    max_contracts: int,
) -> int:
    if stop_points <= 0 or budget_usd <= 0:
        return 0
    per_contract_risk = stop_points * multiplier + round_trip_cost_usd
    if per_contract_risk <= 0:
        return 0
    qty = int(budget_usd // per_contract_risk)
    if equity_usd and price:
        margin_per_contract = margin_init_pct * price * multiplier
        if margin_per_contract > 0:
            qty = min(qty, int((margin_fraction_cap * equity_usd) // margin_per_contract))
    qty = min(qty, max_contracts)
    return max(qty, 0)
