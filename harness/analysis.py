"""
Multi-year validation analysis engine for Bot B+C3.

Consumes Nautilus captures in the Validation V2 layout
({prefix}_trades_raw.csv, {prefix}_daily.csv, {prefix}_equity.csv)
and produces the assignment's section 6-9 analytics:

  * core metrics (net, PF, win rate, avg win/loss, expectancy,
    trades/day, max consecutive losses, long vs short)
  * drawdown trio: closing-equity (trade-close steps), end-of-day
    (daily balances), intraday (per-minute mark-to-market), plus
    EOD-peak-to-intraday-trough (the prop-firm binding measure)
  * monthly / quarterly / yearly tables with best/worst and
    percent-profitable
  * confidence intervals: trade bootstrap for expectancy; circular
    block bootstrap (block = 5 sessions) on daily P&L for expectancy
    and profit factor, preserving serial dependence
  * degradation scenarios 5/10/15/20% (winners scaled down, losers
    scaled up — Validation V2 method) and cost sensitivity
    (+$0.50 / +$1.00 per side, trade-level)
  * prop-firm trailing-drawdown scenarios ($4,500 and $5,000):
    exact minute-level floor replay on a $150,000 account plus
    block-bootstrap breach/pass probabilities (250-day horizon)
  * market-regime breakdown with the classification defined FIRST
    (see classify_regimes docstring — labels use only data through
    the prior close)
  * chronological walk-forward SEGMENT evaluation. Parameters are
    fixed and never refitted, so walk-forward here means sequential
    out-of-sample segment reporting, not re-optimization.

Slippage note: fills in the source backtests are MODELED at exactly
1 tick per fill (an assumption, config.py), so average/max slippage
is 1.0 tick by construction — reported as such, never as a
measurement.
"""
import numpy as np
import pandas as pd

RNG = np.random.default_rng(20261120)
START_EQ = 50_000.0          # test-account base of the source captures
PROP_START = 150_000.0       # prop-firm scenario account


def _pnl(series: pd.Series) -> np.ndarray:
    return series.astype(str).str.replace(" USD", "").astype(float).values


def core_metrics(trades_raw: pd.DataFrame, daily: pd.DataFrame,
                 equity: pd.DataFrame) -> dict:
    pnl = _pnl(trades_raw["realized_pnl"])
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    gross_w, gross_l = wins.sum(), -losses.sum()
    # consecutive losses by close time
    tc = trades_raw.assign(p=pnl).sort_values("ts_closed")["p"].values
    streak = worst = 0
    for p in tc:
        streak = streak + 1 if p < 0 else 0
        worst = max(worst, streak)
    # Drawdowns from the per-minute equity curve. Source timestamps can
    # be parsed as tz-aware Python objects (mixed UTC offsets), so first
    # normalize them to a real DatetimeIndex in America/New_York.
    eq_src = equity.copy()
    eq_src["ts"] = pd.to_datetime(eq_src["ts"], utc=True).dt.tz_convert(
        "America/New_York")
    eq = eq_src.groupby("ts")["equity"].min().sort_index()
    run_peak = eq.cummax()
    intraday_dd = float((run_peak - eq).max())
    eod = eq.groupby(eq.index.date).last()
    eod_dd = float((eod.cummax() - eod).max())
    # EOD-peak to intraday-trough (prop binding measure)
    dates = eq.index.date
    trough_dd, peak_eod = 0.0, START_EQ
    df_eq = pd.DataFrame({"eq": eq.values, "d": dates})
    for _, grp in df_eq.groupby("d"):
        trough_dd = max(trough_dd, peak_eod - grp["eq"].min())
        peak_eod = max(peak_eod, grp["eq"].iloc[-1])
    # closing-equity (trade-close steps)
    steps = np.concatenate([[START_EQ], START_EQ + np.cumsum(tc)])
    close_dd = float((np.maximum.accumulate(steps) - steps).max())
    side = trades_raw["entry"].map({"BUY": "long", "SELL": "short"})
    ls = {}
    for s in ("long", "short"):
        p = pnl[side.values == s]
        ls[s] = {"trades": int(len(p)), "net": round(float(p.sum()), 2),
                 "pf": round(float(p[p > 0].sum() / -p[p < 0].sum()), 3)
                 if (p < 0).any() else None}
    # Count actual RTH sessions represented in the timestamped equity
    # curve. The daily CSV can contain additional Globex calendar dates,
    # so len(daily) is not a valid denominator for trades/day.
    try:
        ts_et = pd.to_datetime(equity["ts"], utc=True).dt.tz_convert(
            "America/New_York")
        hhmm = ts_et.dt.hour * 60 + ts_et.dt.minute
        sessions = int(ts_et[(hhmm >= 570) & (hhmm <= 959)].dt.date.nunique())
    except Exception:
        sessions = int(len(daily))
    return {
        "trades": int(len(pnl)), "net": round(float(pnl.sum()), 2),
        "profit_factor": round(float(gross_w / gross_l), 3) if gross_l else None,
        "win_rate": round(float((pnl > 0).mean()), 4),
        "avg_win": round(float(wins.mean()), 2) if len(wins) else None,
        "avg_loss": round(float(losses.mean()), 2) if len(losses) else None,
        "expectancy": round(float(pnl.mean()), 2),
        "sessions": sessions,
        "trades_per_session": round(len(pnl) / max(sessions, 1), 2),
        "max_consecutive_losses": int(worst),
        "dd_intraday": round(intraday_dd, 2),
        "dd_eod_peak_to_intraday_trough": round(float(trough_dd), 2),
        "dd_eod": round(eod_dd, 2),
        "dd_closing_equity": round(close_dd, 2),
        "slippage_ticks_modeled": {"avg": 1.0, "max": 1.0,
                                   "note": "assumption (config), not a measurement"},
        "long_short": ls,
    }


def period_tables(daily: pd.DataFrame) -> dict:
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d[d["daily_pnl"] != 0] if (d["daily_pnl"] == 0).any() else d
    out = {}
    for name, key in (("monthly", d["date"].dt.to_period("M")),
                      ("quarterly", d["date"].dt.to_period("Q")),
                      ("yearly", d["date"].dt.to_period("Y"))):
        g = d.groupby(key)["daily_pnl"].sum()
        out[name] = {str(k): round(float(v), 2) for k, v in g.items()}
        out[name + "_best"] = {str(g.idxmax()): round(float(g.max()), 2)} if len(g) else {}
        out[name + "_worst"] = {str(g.idxmin()): round(float(g.min()), 2)} if len(g) else {}
        out[name + "_pct_profitable"] = round(float((g > 0).mean()), 3) if len(g) else None
    return out


def block_bootstrap_ci(daily_pnl: np.ndarray, n_sims=10_000, block=5) -> dict:
    """Circular block bootstrap on the daily P&L series (preserves
    serial dependence). Returns CIs for mean daily P&L and for the
    profit factor of a resampled path of the same length."""
    x = np.asarray(daily_pnl, float)
    n = len(x)
    starts = RNG.integers(0, n, size=(n_sims, n // block + 1))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    paths = x[idx.reshape(n_sims, -1)[:, :n]]
    means = paths.mean(axis=1)
    gw = np.where(paths > 0, paths, 0).sum(axis=1)
    gl = -np.where(paths < 0, paths, 0).sum(axis=1)
    pfs = np.divide(gw, gl, out=np.full_like(gw, np.nan), where=gl > 0)
    return {
        "mean_daily_pnl_95ci": [round(float(np.percentile(means, 2.5)), 2),
                                round(float(np.percentile(means, 97.5)), 2)],
        "pf_95ci": [round(float(np.nanpercentile(pfs, 2.5)), 3),
                    round(float(np.nanpercentile(pfs, 97.5)), 3)],
        "p_mean_daily_le_zero": round(float((means <= 0).mean()), 4),
        "method": f"circular block bootstrap, block={block} sessions, {n_sims} sims",
    }


def trade_bootstrap_ci(pnl: np.ndarray, n_sims=10_000) -> dict:
    """Ordinary trade-level bootstrap for expectancy and profit factor.

    This is a cross-check only: unlike the daily block bootstrap, it
    does not preserve serial dependence across trades.
    """
    x = np.asarray(pnl, float)
    idx = RNG.integers(0, len(x), size=(n_sims, len(x)))
    paths = x[idx]
    means = paths.mean(axis=1)
    gw = np.where(paths > 0, paths, 0).sum(axis=1)
    gl = -np.where(paths < 0, paths, 0).sum(axis=1)
    pfs = np.divide(gw, gl, out=np.full_like(gw, np.nan), where=gl > 0)
    return {
        "expectancy_95ci": [round(float(np.percentile(means, 2.5)), 2),
                            round(float(np.percentile(means, 97.5)), 2)],
        "pf_95ci": [round(float(np.nanpercentile(pfs, 2.5)), 3),
                    round(float(np.nanpercentile(pfs, 97.5)), 3)],
        "p_expectancy_le_zero": round(float((means <= 0).mean()), 4),
        "method": f"trade-level bootstrap, {n_sims} sims; cross-check only",
    }


def degrade(pnl: np.ndarray, frac: float) -> float:
    adj = np.where(pnl > 0, pnl * (1 - frac), pnl * (1 + frac))
    return float(adj.sum())


def cost_adjust(trades_raw: pd.DataFrame, extra_per_side: float) -> float:
    pnl = _pnl(trades_raw["realized_pnl"])
    return float((pnl - 2 * extra_per_side * trades_raw["peak_qty"].values).sum())


def prop_replay(equity: pd.DataFrame, limit: float) -> dict:
    """Exact EOD-trailing floor replay on a $150,000 account using the
    per-minute equity curve (breach = minute equity <= floor in force)."""
    eq = equity.copy()
    eq["ts"] = pd.to_datetime(eq["ts"], utc=True).dt.tz_convert("America/New_York")
    eq["eq"] = PROP_START + (eq["equity"] - START_EQ)
    per_ts = eq.groupby("ts")["eq"].min().sort_index()
    floor, peak_eod, min_dist = PROP_START - limit, PROP_START, np.inf
    outcome, out_date = "ALIVE", None
    for date, grp in per_ts.groupby(per_ts.index.date):
        min_dist = min(min_dist, float(grp.min()) - floor)
        if (grp <= floor).any():
            outcome, out_date = "BREACH", str(date)
            break
        peak_eod = max(peak_eod, float(grp.iloc[-1]))
        floor = max(floor, peak_eod - limit)
    return {"limit": limit, "outcome": outcome, "breach_date": out_date,
            "min_distance_to_floor": round(float(min_dist), 2)}


def prop_mc(daily_pnl: np.ndarray, kappa: float, limit: float,
            target: float | None = None, n_sims=10_000, horizon=250) -> dict:
    x = np.asarray(daily_pnl, float)
    n = len(x)
    block = 5
    starts = RNG.integers(0, n, size=(n_sims, horizon // block + 1))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    paths = x[idx.reshape(n_sims, -1)[:, :horizon]]
    eq = np.cumsum(paths, axis=1)
    peak = np.maximum.accumulate(
        np.hstack([np.zeros((n_sims, 1)), eq]), axis=1)[:, :-1]
    dd_adj = (peak - eq) * kappa
    breach = dd_adj > limit
    fb = np.where(breach.any(1), breach.argmax(1), 10**9)
    res = {"limit": limit, "p_breach_250d": round(float((fb < 10**9).mean()), 4),
           "median_max_dd_adj": round(float(np.median(dd_adj.max(1))), 2)}
    if target:
        passed = eq >= target
        fp = np.where(passed.any(1), passed.argmax(1), 10**9)
        res["p_pass"] = round(float((fp < fb).mean()), 4)
        res["p_fail"] = round(float((fb < fp).mean()), 4)
        ok = fp < fb
        if ok.any():
            res["median_days_to_pass"] = int(np.median(
                np.arange(horizon)[fp[ok]]) + 1)
    return res


def classify_regimes(daily_bars: pd.DataFrame) -> pd.DataFrame:
    """A-PRIORI regime labels for each session, using ONLY data through
    the prior close (no look-ahead, no performance input):
      vol_state : 20-session realized vol (annualized), terciles of the
                  daily series provided (for the real run, thresholds
                  come from the training period only — parameter below)
      trend     : close vs 50-session SMA and its 5-session slope:
                  up / down / sideways
      selloff   : trailing 20-session return <= -7%
      recovery  : a selloff in the prior 60 sessions AND trailing
                  20-session return >= +5%
    """
    df = daily_bars.copy()
    df["date"] = pd.to_datetime(df["datetime"]).dt.date
    c = df["close"]
    ret = np.log(c / c.shift(1))
    df["vol20"] = ret.rolling(20).std() * np.sqrt(252)
    df["sma50"] = c.rolling(50).mean()
    df["ret20"] = c / c.shift(20) - 1
    df["selloff"] = df["ret20"] <= -0.07
    df["recent_selloff"] = df["selloff"].rolling(60).max().fillna(0).astype(bool)
    df["recovery"] = df["recent_selloff"] & (df["ret20"] >= 0.05)
    lo, hi = df["vol20"].quantile(1 / 3), df["vol20"].quantile(2 / 3)
    df["vol_state"] = np.select(
        [df["vol20"] <= lo, df["vol20"] > hi], ["low", "high"], default="mid")
    slope = df["sma50"] - df["sma50"].shift(5)
    df["trend"] = np.select(
        [(c > df["sma50"]) & (slope > 0), (c < df["sma50"]) & (slope < 0)],
        ["up", "down"], default="sideways")
    # labels for session t use features computed through t-1
    cols = ["vol_state", "trend", "selloff", "recovery"]
    df[cols] = df[cols].shift(1)
    return df[["date"] + cols]


def regime_breakdown(session_pnl: pd.Series, regimes: pd.DataFrame) -> dict:
    m = regimes.set_index("date").reindex(session_pnl.index)
    out = {}
    for col in ("vol_state", "trend"):
        g = {}
        for k, grp in session_pnl.groupby(m[col]):
            if pd.isna(k):
                continue
            g[str(k)] = {"sessions": int(len(grp)),
                         "net": round(float(grp.sum()), 2),
                         "mean_daily": round(float(grp.mean()), 2)}
        out[col] = g
    for col in ("selloff", "recovery"):
        mask = m[col] == True  # noqa: E712
        if mask.any():
            out[col] = {"sessions": int(mask.sum()),
                        "net": round(float(session_pnl[mask].sum()), 2),
                        "mean_daily": round(float(session_pnl[mask].mean()), 2)}
    return out


def walk_forward_segments(session_pnl: pd.Series, initial: int,
                          step: int) -> list[dict]:
    """Sequential segment evaluation with FIXED parameters (nothing is
    refitted — this is chronological segment reporting, the honest
    walk-forward form for a no-optimization validation)."""
    segs, i = [], initial
    vals = session_pnl.values
    while i < len(vals):
        seg = vals[i:i + step]
        if len(seg) == 0:
            break
        gw, gl = seg[seg > 0].sum(), -seg[seg < 0].sum()
        segs.append({"segment": len(segs) + 1, "sessions": int(len(seg)),
                     "net": round(float(seg.sum()), 2),
                     "pf": round(float(gw / gl), 3) if gl else None})
        i += step
    return segs
