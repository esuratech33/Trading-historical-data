"""
Shakedown driver — runs the multi-year validation harness against the
EXISTING 61-session Validation V2 captures to prove the pipeline
reproduces known results before any new data exists.

THIS IS A PIPELINE VERIFICATION, NOT A MULTI-YEAR TEST. Every output
is labeled as such. The multi-year validation itself remains blocked
on data acquisition (see MULTIYEAR_VALIDATION_STATUS.md).
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import analysis as A
from data_quality import qc_bars

HERE = Path(__file__).parent
ROOT = HERE.parent
V2 = ROOT / "validation_v2" / "data_outputs"
OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)
LEVELS = ("BC3_risk100", "BC3_risk150", "BC3_risk200", "BC3_risk250")

# ---- 1. data quality on the existing 1-minute file -------------------
qc = qc_bars(ROOT / "data" / "topstepx_github" / "MNQ_1min_20260120_20260415.csv")
(OUT / "data_quality_existing_1min.json").write_text(json.dumps(qc, indent=2))
print("QC:", json.dumps({k: qc[k] for k in
      ("rows", "duplicate_timestamps", "ohlc_violations", "rth_sessions",
       "rth_missing_minutes_within_observed_span_total")}))

# ---- 2. per-level analytics ------------------------------------------
summary = {"shakedown": True,
           "warning": "Pipeline verification on the 61-session sample. "
                      "NOT a multi-year validation."}
for lvl in LEVELS:
    tr = pd.read_csv(V2 / f"{lvl}_trades_raw.csv")
    dy = pd.read_csv(V2 / f"{lvl}_daily.csv")
    eq = pd.read_csv(V2 / f"{lvl}_equity.csv", parse_dates=["ts"])
    m = A.core_metrics(tr, dy, eq)
    per = A.period_tables(dy)
    ci = A.block_bootstrap_ci(dy["daily_pnl"].values)
    pnl = A._pnl(tr["realized_pnl"])
    kappa = m["dd_eod_peak_to_intraday_trough"] / m["dd_eod"] if m["dd_eod"] else 1.0
    entry = {**m, "periods": per, "ci": ci,
             "trade_ci": A.trade_bootstrap_ci(pnl),
             "degradation_net": {f"{int(f*100)}pct": round(A.degrade(pnl, f), 2)
                                 for f in (0.05, 0.10, 0.15, 0.20)},
             "cost_sensitivity_net": {
                 "plus_0.50_per_side": round(A.cost_adjust(tr, 0.50), 2),
                 "plus_1.00_per_side": round(A.cost_adjust(tr, 1.00), 2)},
             "prop_4500_replay": A.prop_replay(eq, 4500.0),
             "prop_5000_replay": A.prop_replay(eq, 5000.0),
             "prop_4500_mc": A.prop_mc(dy["daily_pnl"].values, kappa, 4500.0),
             "prop_5000_mc": A.prop_mc(dy["daily_pnl"].values, kappa, 5000.0,
                                       target=9000.0)}
    summary[lvl] = entry
    print(lvl, "net", m["net"], "PF", m["profit_factor"],
          "intraDD", m["dd_intraday"], "troughDD",
          m["dd_eod_peak_to_intraday_trough"], "| prop5000 MC:",
          entry["prop_5000_mc"])

# ---- 3. session P&L (ET) for regimes + walk-forward (risk250) --------
eq = pd.read_csv(V2 / "BC3_risk250_equity.csv", parse_dates=["ts"])
eq["ts"] = pd.to_datetime(eq["ts"], utc=True).dt.tz_convert("America/New_York")
per_ts = eq.groupby("ts")["equity"].min().sort_index()
eod = per_ts.groupby(per_ts.index.date).last()
session_pnl_all = eod.diff()
# The first observed date's P&L is its EOD equity minus the starting
# equity; diff() alone would silently drop the first trading session.
session_pnl_all.iloc[0] = eod.iloc[0] - A.START_EQ
# Restrict regime / walk-forward accounting to dates that actually
# contain RTH bars in the 1-minute source file (61 sessions), rather
# than every Globex calendar date represented in the equity curve.
bars_1m = pd.read_csv(
    ROOT / "data" / "topstepx_github" / "MNQ_1min_20260120_20260415.csv",
    usecols=["datetime"])
bars_1m["ts"] = pd.to_datetime(bars_1m["datetime"], utc=True).dt.tz_convert(
    "America/New_York")
hhmm = bars_1m["ts"].dt.hour * 60 + bars_1m["ts"].dt.minute
rth_dates = sorted(bars_1m.loc[(hhmm >= 570) & (hhmm <= 959), "ts"].dt.date.unique())
session_pnl = session_pnl_all.reindex(rth_dates).fillna(0.0)
bars = pd.read_csv(ROOT / "data" / "topstepx_github" / "MNQ_daily_20250324_20260414.csv")
regimes = A.classify_regimes(bars)
summary["BC3_risk250"]["regimes"] = A.regime_breakdown(session_pnl, regimes)
summary["BC3_risk250"]["walk_forward_segments_20_10"] = \
    A.walk_forward_segments(session_pnl, initial=20, step=10)
print("regimes:", json.dumps(summary["BC3_risk250"]["regimes"], indent=1))

# ---- 4. CSV deliverables (risk250) ------------------------------------
dy = pd.read_csv(V2 / "BC3_risk250_daily.csv")
dy["date"] = pd.to_datetime(dy["date"])
monthly = dy.groupby(dy["date"].dt.to_period("M"))["daily_pnl"].sum()
monthly.rename("net").to_csv(OUT / "shakedown_monthly_risk250.csv")
yearly = dy.groupby(dy["date"].dt.to_period("Y"))["daily_pnl"].sum()
yearly.rename("net").to_csv(OUT / "shakedown_yearly_risk250.csv")
eqd = pd.DataFrame({"date": eod.index, "eod_equity_150k": 150_000 + (eod.values - 50_000)})
eqd["peak"] = eqd["eod_equity_150k"].cummax()
eqd["floor_5000"] = eqd["peak"] - 5_000
eqd["drawdown_eod"] = eqd["peak"] - eqd["eod_equity_150k"]
eqd.to_csv(OUT / "shakedown_daily_equity_dd_risk250.csv", index=False)
pd.read_csv(V2 / "BC3_risk250_trades.csv").to_csv(
    OUT / "shakedown_trades_risk250.csv", index=False)

# ---- 5. charts (risk250) ----------------------------------------------
fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
ax[0].plot(eqd["date"], eqd["eod_equity_150k"], lw=1.2)
ax[0].axhline(159_000, ls="--", lw=0.8)
ax[0].set_title("B+C3 $250 — equity on $150K account (61-session shakedown sample)")
ax[1].fill_between(eqd["date"], -eqd["drawdown_eod"], color="r", alpha=0.4)
ax[1].axhline(-5_000, ls="--", lw=0.8)
ax[1].set_title("End-of-day drawdown vs $5,000 limit")
fig.tight_layout(); fig.savefig(OUT / "chart_shakedown_equity_dd.png", dpi=110)
fig2, ax2 = plt.subplots(figsize=(8, 3.5))
monthly.plot(kind="bar", ax=ax2)
ax2.set_title("B+C3 $250 — monthly net (shakedown sample: 3 months only)")
fig2.tight_layout(); fig2.savefig(OUT / "chart_shakedown_monthly.png", dpi=110)

(OUT / "shakedown_summary.json").write_text(json.dumps(summary, indent=2, default=str))
print("\nWrote shakedown outputs to", OUT)
