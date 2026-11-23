"""Fast-pass / efficiency sweep — Select Flex 25K evaluation of ALL
candidates: the brand-new Bots K/L/M/N (fresh captures) plus every
earlier strategy with legitimate existing captures (Bots A-G era:
A, B alone, C3 alone, B+C3, A+B+C3, F, G). No Nautilus re-runs for
the legacy candidates — metrics are computed from their captures.

Account: Select Flex 25K (3-day min) — start $25,000, target +$1,500,
EOD-trailing drawdown $1,000 enforced in real time, no DLL, 40%
evaluation consistency, max 10 micros.

Differences from the Miami / $100-day state machines (both copied
from miami_fit_test/miami_eval.py, same seed 20261122):
  * The 40% consistency rule is now ENFORCED, not just reported: a
    pass is credited only at the end of a day on which cumulative
    profit >= target AND the best single day <= 40% of cumulative
    profit AND the 3-day minimum is met. (Consistency is a property
    of daily results, so pass crediting is an EOD determination;
    breaches remain intraday/real-time. This is slightly more
    conservative than the earlier intraday-touch crediting.)
  * The Monte Carlo records the full days-to-pass distribution:
    P(pass <= 7 days), P(pass <= 14 days), P(fail), median days.
    A candidate MEETS Esura's fast-pass requirement only if
    MC P(pass <= 14 days) >= 50%.
  * Primary ranking is EFFICIENCY at the drawdown-safe size:
    efficiency = avg $/day per $1,000 of EOD-peak-to-intraday-trough
    drawdown, where the safe size is the largest tested size whose
    trough <= ~$700 (2/3 of the $1,000 limit), as in the $100-day job.
  * A broker-rules compliance checklist is computed per candidate
    from its trade capture at the evaluated size.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
HERE = Path(__file__).parent
FAST = HERE / "data_outputs"
HUND = ROOT / "hundred_dollar_day" / "data_outputs"
MIAMI = ROOT / "miami_fit_test" / "data_outputs"
V2 = ROOT / "validation_v2" / "data_outputs"
BASE = 50_000.0
SAFE_TROUGH = 700.0
RNG = np.random.default_rng(20261122)

ACCT = {"name": "Select Flex 25K (3-day min)", "start": 25_000.0,
        "target_profit": 1_500.0, "floor_mode": "trailing",
        "limit": 1_000.0, "dll": None, "min_days": 3,
        "consistency": 0.40, "max_micros": 10}

# candidate -> {size_usd: (folder, prefix)}
CANDIDATES = {
    "K": {"name": "Bot K — 15-min Trend Rider (NEW)",
          "sizes": {100: (FAST, "K_risk100"), 150: (FAST, "K_risk150")}},
    "L": {"name": "Bot L — Squeeze Breakout (NEW)",
          "sizes": {100: (FAST, "L_risk100"), 150: (FAST, "L_risk150")}},
    "M": {"name": "Bot M — Last-Hour Momentum (NEW)",
          "sizes": {100: (FAST, "M_risk100"), 150: (FAST, "M_risk150"),
                    200: (FAST, "M_risk200")}},
    "N": {"name": "Bot N — Prior-Day Level Acceptance (NEW)",
          "sizes": {100: (FAST, "N_risk100"), 150: (FAST, "N_risk150")}},
    "A": {"name": "Bot A — Opening Range Breakout (legacy)",
          "sizes": {u: (HUND, f"A_risk{u}") for u in (50, 100, 150, 200)}},
    "ABC3": {"name": "Bot A+B+C3 portfolio (legacy)",
             "sizes": {u: (HUND, f"ABC3_risk{u}") for u in (50, 100, 150, 200)}},
    "BC3": {"name": "Bot B+C3 pair (legacy)",
            "sizes": {25: (MIAMI, "BC3_risk25"), 50: (MIAMI, "BC3_risk50"),
                      75: (MIAMI, "BC3_risk75"), 100: (V2, "BC3_risk100"),
                      150: (V2, "BC3_risk150"), 200: (V2, "BC3_risk200"),
                      250: (V2, "BC3_risk250")}},
    "B": {"name": "Bot B — Trend Pullback alone (legacy, single capture)",
          "sizes": {250: (V2, "B_only_risk250")}},
    "C3": {"name": "Bot C3 — Failed Breakout alone (legacy, single capture)",
           "sizes": {250: (V2, "C3_only_risk250")}},
    "F": {"name": "Bot F — Momentum scalper, 8-pt stop cap (legacy)",
          "sizes": {u: (HUND, f"F_risk{u}") for u in (50, 100, 150, 200)}},
    "G": {"name": "Bot G — Midday VWAP mean reversion (legacy)",
          "sizes": {u: (HUND, f"G_risk{u}") for u in (50, 100, 150, 200)}},
}


# ----------------------------------------------------------------------
# capture loading / metrics (mirrors hundred_dollar_day/select_eval.py)
# ----------------------------------------------------------------------
def load_capture(folder: Path, prefix: str) -> dict | None:
    eq_f = folder / f"{prefix}_equity.csv"
    if not eq_f.exists():
        return None
    eq = pd.read_csv(eq_f)
    dy = pd.read_csv(folder / f"{prefix}_daily.csv")
    tr_f = folder / f"{prefix}_trades_raw.csv"
    net = round(float(dy["daily_pnl"].sum()), 2)
    trades, pf, max_qty = 0, None, 0
    if tr_f.exists():
        tr = pd.read_csv(tr_f)
        trades = int(len(tr))
        if trades:
            pnl = tr["realized_pnl"].astype(str).str.replace(" USD", "").astype(float)
            gl = -float(pnl[pnl < 0].sum())
            pf = round(float(pnl[pnl > 0].sum()) / gl, 3) if gl else None
            max_qty = int(tr["peak_qty"].max())
    eq2 = eq.copy()
    eq2["ts"] = pd.to_datetime(eq2["ts"], utc=True).dt.tz_convert("America/New_York")
    per = eq2.groupby("ts")["equity"].min().sort_index()
    eod = per.groupby(per.index.date).last()
    dd_eod = float((eod.cummax() - eod).max())
    trough, peak_eod = 0.0, BASE
    df_eq = pd.DataFrame({"eq": per.values, "d": per.index.date})
    for _, grp in df_eq.groupby("d"):
        trough = max(trough, peak_eod - float(grp["eq"].min()))
        peak_eod = max(peak_eod, float(grp["eq"].iloc[-1]))
    hhmm = eq2["ts"].dt.hour * 60 + eq2["ts"].dt.minute
    rth = eq2["ts"][(hhmm >= 570) & (hhmm <= 959)]
    session_dates = sorted({d.isoformat() for d in rth.dt.date})
    sessions = len(session_dates)
    return {"trades": trades, "net": net, "profit_factor": pf,
            "max_peak_qty": max_qty, "sessions": sessions,
            "session_dates": session_dates,
            "avg_daily_net": round(net / sessions, 2) if sessions else None,
            "dd_eod": round(dd_eod, 2),
            "dd_trough": round(float(trough), 2),
            "kappa": round(float(trough) / dd_eod, 4) if dd_eod else 1.0,
            "equity_df": eq, "folder": str(folder), "prefix": prefix}


# ----------------------------------------------------------------------
# state machine (copied from miami_fit_test/miami_eval.py, pass logic
# extended for the enforced 40% consistency rule)
# ----------------------------------------------------------------------
def per_minute(equity_df: pd.DataFrame, start: float) -> pd.Series:
    eq = equity_df.copy()
    eq["ts"] = pd.to_datetime(eq["ts"], utc=True).dt.tz_convert("America/New_York")
    eq["eq"] = start + (eq["equity"] - BASE)
    return eq.groupby("ts")["eq"].min().sort_index()


def eff_day(prints: np.ndarray, day_start: float, dll: float | None):
    if dll is None or len(prints) == 0:
        return prints, False
    below = np.nonzero(day_start - prints >= dll)[0]
    if len(below) == 0:
        return prints, False
    i = int(below[0])
    eff = prints[: i + 1].copy()
    eff[i] = day_start - dll
    return eff, True


def day_walk(per_ts: pd.Series, dll: float | None) -> list[dict]:
    days = []
    day_start = float(per_ts.iloc[0]) if len(per_ts) else 0.0
    start0 = None
    for date, grp in per_ts.groupby(per_ts.index.date):
        prints = grp.values.astype(float)
        if start0 is None:
            start0 = float(prints[0])
            day_start = start0
        eff, hit = eff_day(prints, day_start, dll)
        day_end = float(eff[-1]) if len(eff) else day_start
        days.append({"date": str(date), "prints": prints, "eff": eff,
                     "day_start": day_start, "day_end": day_end,
                     "result": day_end - day_start, "dll_hit": bool(hit)})
        day_start = day_end
    return days


def race_select(per_ts: pd.Series, acct: dict) -> dict:
    """Historical race: intraday breach vs the trailing floor; pass
    credited at the first EOD where cumulative profit >= target, the
    best day <= consistency x cumulative profit, and the minimum-days
    rule is met."""
    start, target_eq = acct["start"], acct["start"] + acct["target_profit"]
    limit, min_days, cons = acct["limit"], acct["min_days"], acct["consistency"]
    floor = start - limit
    peak_eod = start
    days = day_walk(per_ts, acct["dll"])
    min_dist, outcome, out_date = np.inf, "ALIVE_NEITHER", None
    cum, best = 0.0, -np.inf
    target_touch_date = None
    target_eod_date = None
    blocked = False
    share_at_pass = None
    i = -1
    for i, d in enumerate(days):
        eff = d["eff"]
        if len(eff):
            min_dist = min(min_dist, float(eff.min()) - floor)
            if target_touch_date is None and (eff >= target_eq).any():
                target_touch_date = d["date"]
            if (eff <= floor).any():
                outcome, out_date = "FAIL_BREACH", d["date"]
                break
        cum += d["result"]
        best = max(best, d["result"])
        if cum >= acct["target_profit"]:
            if target_eod_date is None:
                target_eod_date = d["date"]
            share = best / cum if cum > 0 else np.inf
            if i >= min_days - 1 and share <= cons:
                outcome, out_date = "PASS", d["date"]
                share_at_pass = round(float(share), 4)
                break
            blocked = True
        peak_eod = max(peak_eod, d["day_end"])
        floor = max(floor, peak_eod - limit)
    return {"outcome": outcome, "outcome_date": out_date,
            "min_distance_to_floor": round(float(min_dist), 2),
            "sessions_through_outcome": (i + 1) if days else 0,
            "target_first_touched_intraday_date": target_touch_date,
            "target_first_reached_eod_date": target_eod_date,
            "consistency_blocked_at_some_eod": bool(blocked and outcome != "PASS"),
            "best_day_share_at_pass_eod_basis": share_at_pass}


def _paths(daily_pnl: np.ndarray, dll: float | None,
           n_sims=10_000, horizon=250, block=5) -> np.ndarray:
    x = np.asarray(daily_pnl, float)
    if dll is not None:
        x = np.maximum(x, -dll)
    n = len(x)
    starts = RNG.integers(0, n, size=(n_sims, horizon // block + 1))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return x[idx.reshape(n_sims, -1)[:, :horizon]]


def mc_select(acct: dict, daily_pnl: np.ndarray, kappa: float) -> dict:
    """Block-bootstrap MC with the consistency-gated pass rule and the
    full days-to-pass distribution."""
    paths = _paths(daily_pnl, acct["dll"])
    eq = np.cumsum(paths, axis=1)
    peak = np.maximum.accumulate(
        np.hstack([np.zeros((len(paths), 1)), eq]), axis=1)[:, :-1]
    dd_adj = (peak - eq) * kappa
    breach = dd_adj > acct["limit"]
    runmax = np.maximum.accumulate(paths, axis=1)
    day_idx = np.arange(eq.shape[1])[None, :]
    pass_mask = (eq >= acct["target_profit"]) \
        & (runmax <= acct["consistency"] * eq) \
        & (day_idx >= acct["min_days"] - 1)
    fb = np.where(breach.any(1), breach.argmax(1), 10**9)
    fp = np.where(pass_mask.any(1), pass_mask.argmax(1), 10**9)
    fail = fb < fp
    ok = fp < fb
    days = fp[ok] + 1
    pass_days_all = np.where(ok, fp + 1, 10**9)
    shares = None
    if ok.any():
        rows = np.nonzero(ok)[0]
        shares = runmax[rows, fp[ok]] / eq[rows, fp[ok]]
    return {"p_pass": round(float(ok.mean()), 4),
            "p_pass_le_7d": round(float((pass_days_all <= 7).mean()), 4),
            "p_pass_le_14d": round(float((pass_days_all <= 14).mean()), 4),
            "p_fail": round(float(fail.mean()), 4),
            "p_undecided": round(float((~ok & ~fail).mean()), 4),
            "median_days_to_pass": int(np.median(days)) if ok.any() else None,
            "median_best_day_share_at_pass": round(float(np.median(shares)), 4) if shares is not None else None,
            "max_best_day_share_at_pass": round(float(np.max(shares)), 4) if shares is not None else None,
            "median_max_dd_adj": round(float(np.median(dd_adj.max(1))), 2)}


# ----------------------------------------------------------------------
# broker-rules compliance (from the trade capture)
# ----------------------------------------------------------------------
def compliance(cap: dict, session_dates: list[str]) -> dict:
    folder, prefix = Path(cap["folder"]), cap["prefix"]
    tr_f = folder / f"{prefix}_trades_raw.csv"
    out = {"max_peak_qty_micros": cap["max_peak_qty"],
           "position_within_10_micros": bool(cap["max_peak_qty"] <= ACCT["max_micros"]),
           "opposing_positions": "impossible by construction — single-strategy "
                                 "run on one NETTING account, entries only when flat"}
    if not tr_f.exists() or cap["trades"] == 0:
        out.update({"trades": cap["trades"], "zero_overnight_holds": None,
                    "pct_trades_held_over_10s": None,
                    "pct_gross_profit_from_trades_over_10s": None,
                    "longest_no_trade_stretch_sessions": len(session_dates),
                    "idle_rule_ok_under_5_sessions": False,
                    "note": "no trades in capture"})
        return out
    tr = pd.read_csv(tr_f)
    tr["ts_opened"] = pd.to_datetime(tr["ts_opened"], utc=True).dt.tz_convert("America/New_York")
    tr["ts_closed"] = pd.to_datetime(tr["ts_closed"], utc=True).dt.tz_convert("America/New_York")
    tr["pnl"] = tr["realized_pnl"].astype(str).str.replace(" USD", "").astype(float)
    same_day = (tr["ts_opened"].dt.date == tr["ts_closed"].dt.date)
    close_times = tr["ts_closed"].dt.hour * 60 + tr["ts_closed"].dt.minute
    dur_s = tr["duration_ns"] / 1e9 if "duration_ns" in tr else pd.Series(dtype=float)
    over10 = dur_s > 10
    gross = float(tr.loc[tr["pnl"] > 0, "pnl"].sum())
    gross_over10 = float(tr.loc[over10 & (tr["pnl"] > 0), "pnl"].sum())
    trade_dates = {d.isoformat() for d in tr["ts_opened"].dt.date}
    longest = run = 0
    for sd in session_dates:
        if sd in trade_dates:
            run = 0
        else:
            run += 1
            longest = max(longest, run)
    out.update({
        "trades": int(len(tr)),
        "zero_overnight_holds": bool(same_day.all()),
        "trades_closed_after_1555_et": int((close_times > 15 * 60 + 55).sum()),
        "latest_close_et": f"{int(close_times.max()) // 60:02d}:{int(close_times.max()) % 60:02d}",
        "pct_trades_held_over_10s": round(float(over10.mean()), 4) if len(dur_s) else None,
        "pct_gross_profit_from_trades_over_10s": round(gross_over10 / gross, 4) if gross > 0 else None,
        "microscalping_rule_ok_both_over_50pct": bool(
            len(dur_s) and over10.mean() > 0.5 and gross > 0 and (gross_over10 / gross) > 0.5),
        "longest_no_trade_stretch_sessions": int(longest),
        "idle_rule_ok_under_5_sessions": bool(longest < 5),
    })
    return out


# ----------------------------------------------------------------------
# evaluate everything
# ----------------------------------------------------------------------
summary = {
    "job": "Fast-pass + efficiency sweep — can any strategy pass the Select "
           "Flex 25K evaluation in 7-14 days, and which strategy makes the "
           "most money per unit of risk?",
    "account": {"start": 25_000.0, "target_profit": 1_500.0,
                "drawdown": "EOD-trailing $1,000, enforced in real time",
                "dll": None, "min_days": 3,
                "consistency": "40% ENFORCED at pass (EOD determination)",
                "max_micros": 10},
    "data": "TopstepX MNQ 1-min, 2026-01-20 to 2026-04-15, 61 RTH sessions",
    "costs": "$1.00/contract/side placeholder commission + 1 tick slippage per fill (modeled)",
    "safe_size_rule": "largest tested size with historical EOD-peak-to-intraday-trough DD <= $700",
    "efficiency": "avg $/day at safe size per $1,000 of trough drawdown at safe size",
    "fast_pass_requirement": "MC P(pass <= 14 days) >= 0.50",
    "mc": "circular block bootstrap, block=5 sessions, 10,000 sims, 250-session horizon, seed 20261122",
    "candidates": {},
}

for key, cand in CANDIDATES.items():
    sizes = {}
    caps = {}
    for usd, (folder, prefix) in cand["sizes"].items():
        cap = load_capture(folder, prefix)
        if cap is None:
            continue
        caps[usd] = cap
        sizes[usd] = {k: v for k, v in cap.items()
                      if k not in ("equity_df", "session_dates")}
    safe = None
    for usd in sorted(caps):
        if caps[usd]["dd_trough"] <= SAFE_TROUGH:
            safe = usd
    eval_usd = safe if safe is not None else (min(caps) if caps else None)
    entry = {"name": cand["name"], "sizes": {}, "safe_size_usd": safe,
             "evaluated_size_usd": eval_usd}
    for usd in sorted(caps):
        cap = caps[usd]
        per_ts = per_minute(cap["equity_df"], ACCT["start"])
        hist = race_select(per_ts, ACCT)
        days = day_walk(per_ts, ACCT["dll"])
        daily_pnl = np.array([d["result"] for d in days])
        mc = mc_select(ACCT, daily_pnl, cap["kappa"])
        entry["sizes"][f"risk{usd}"] = {
            "trades": cap["trades"], "net": cap["net"],
            "avg_daily_net": cap["avg_daily_net"],
            "profit_factor": cap["profit_factor"],
            "dd_trough": cap["dd_trough"], "dd_eod": cap["dd_eod"],
            "kappa": cap["kappa"], "max_peak_qty": cap["max_peak_qty"],
            "historical": hist, "monte_carlo": mc,
            "meets_fast_pass_requirement": bool(mc["p_pass_le_14d"] >= 0.50)}
        print(key, f"risk{usd}", "| $/day", cap["avg_daily_net"], "PF", cap["profit_factor"],
              "trough", cap["dd_trough"], "trades", cap["trades"],
              "| HIST:", hist["outcome"], hist["outcome_date"],
              "| MC pass<=7/<=14/fail:", mc["p_pass_le_7d"], mc["p_pass_le_14d"],
              mc["p_fail"], "med", mc["median_days_to_pass"], flush=True)
    if eval_usd is not None:
        cap = caps[eval_usd]
        ev = entry["sizes"][f"risk{eval_usd}"]
        eff = None
        if safe is not None and cap["dd_trough"] > 0 and cap["avg_daily_net"] is not None:
            eff = round(cap["avg_daily_net"] / (cap["dd_trough"] / 1000.0), 2)
        entry["headline"] = {
            "size_usd": eval_usd, "is_drawdown_safe_size": safe is not None,
            "avg_daily_net": cap["avg_daily_net"],
            "profit_factor": cap["profit_factor"], "trades": cap["trades"],
            "dd_trough": cap["dd_trough"],
            "efficiency_per_1000_trough": eff,
            "few_trades_flag": bool(cap["trades"] < 30),
            "exceeds_10_micro_cap": bool(cap["max_peak_qty"] > 10),
            "historical": ev["historical"], "monte_carlo": ev["monte_carlo"],
            "meets_fast_pass_requirement": ev["meets_fast_pass_requirement"],
            "compliance": compliance(cap, cap["session_dates"])}
    summary["candidates"][key] = entry

ranked = []
unranked = []
for key, e in summary["candidates"].items():
    h = e.get("headline")
    if not h:
        continue
    row = {"candidate": key, "name": e["name"], "safe_size_usd": e["safe_size_usd"],
           "avg_daily_net": h["avg_daily_net"],
           "efficiency_per_1000_trough": h["efficiency_per_1000_trough"],
           "dd_trough": h["dd_trough"], "trades": h["trades"],
           "mc_p_pass_le_7d": h["monte_carlo"]["p_pass_le_7d"],
           "mc_p_pass_le_14d": h["monte_carlo"]["p_pass_le_14d"],
           "mc_p_fail": h["monte_carlo"]["p_fail"],
           "mc_median_days": h["monte_carlo"]["median_days_to_pass"],
           "meets_fast_pass_requirement": h["meets_fast_pass_requirement"]}
    (ranked if h["efficiency_per_1000_trough"] is not None else unranked).append(row)
ranked.sort(key=lambda r: r["efficiency_per_1000_trough"], reverse=True)
summary["ranking_by_efficiency"] = ranked
summary["no_safe_size_candidates"] = unranked
summary["any_meets_fast_pass"] = bool(
    any(e["sizes"][s]["meets_fast_pass_requirement"]
        for e in summary["candidates"].values() for s in e["sizes"]))

(HERE / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
print("\nRANKING BY EFFICIENCY:", json.dumps(ranked, indent=2, default=str))
print("NO SAFE SIZE:", json.dumps(unranked, indent=2, default=str))
print("ANY MEETS FAST-PASS (any size):", summary["any_meets_fast_pass"])
print("Wrote", HERE / "summary.json")
