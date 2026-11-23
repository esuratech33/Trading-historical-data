"""Payout-sprint research — TWO-PHASE Select Flex 25K evaluation
(2026-11-23).

Extends fast_pass/select_eval_fast.py's state machine (copied verbatim
where noted) from eval-only to the full eval -> funded -> first-payout
path:

  EVAL phase: start $25,000; PASS at the first EOD where cumulative
  profit >= $1,500 AND best single day <= 40% of cumulative profit
  AND day >= 3 (40% consistency ENFORCED, as in fast_pass); FAIL if a
  print touches the real-time EOD-trailing $1,000 floor.

  FUNDED phase (only after a pass): account restarts at $25,000
  fresh — eval profit does NOT carry over. Same trailing-floor
  failure rule. FIRST PAYOUT at the first EOD with >= 5 winning days
  (a winning day = >= $100 net that day) AND cumulative funded profit
  >= $500 (the Flex request is 50% of total profit with a $250
  minimum request, so $500 of profit is the smallest requestable
  base). The floor-locks-at-start+$100 effect after a payout is
  ignored — the clock stops at the first payout.

Method: historical path through both phases on the actual 61-session
capture, then Monte Carlo circular block bootstrap (block 5, 10,000
sims, 250-session horizon, seed 20261122 — the fast_pass method),
with intraday drawdown from the capture's kappa (trough/EOD ratio),
exactly as in mc_select.

CONTROL GATE: before any candidate is trusted, the copied state
machine must reproduce the known B+C3 @ $50 Select figures from the
existing Miami capture — net $1,037.80 and min floor distance
$604.26 — exactly. The script asserts this and aborts otherwise.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
HERE = Path(__file__).parent
SPRINT = HERE / "data_outputs"
MIAMI = ROOT / "miami_fit_test" / "data_outputs"
V2 = ROOT / "validation_v2" / "data_outputs"
BASE = 50_000.0
RNG = np.random.default_rng(20261122)

ACCT = {"name": "Select Flex 25K (3-day min)", "start": 25_000.0,
        "target_profit": 1_500.0, "floor_mode": "trailing",
        "limit": 1_000.0, "dll": None, "min_days": 3,
        "consistency": 0.40, "max_micros": 10}
WIN_DAY_MIN = 100.0      # funded winning day = >= $100 net
WIN_DAYS_NEEDED = 5      # Flex payout gate
PAYOUT_MIN_PROFIT = 500.0  # 50% request >= $250 minimum -> profit >= $500


# ----------------------------------------------------------------------
# capture loading / metrics (copied from fast_pass/select_eval_fast.py)
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
# state machine pieces (copied from fast_pass/select_eval_fast.py,
# which copied miami_fit_test/miami_eval.py)
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
    """Single-phase (eval-only) race — copied verbatim from fast_pass;
    used ONLY for the control verification gate."""
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
    """Single-phase MC — copied verbatim from fast_pass; used ONLY for
    the control verification gate."""
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
# TWO-PHASE historical race (new for this job)
# ----------------------------------------------------------------------
def race_two_phase(per_ts: pd.Series, acct: dict) -> dict:
    """Historical path through eval, then (on a pass) the funded phase
    on the FOLLOWING sessions of the same capture, fresh $25,000.
    Breach checks use the actual per-minute prints in both phases."""
    days = day_walk(per_ts, acct["dll"])
    start, limit = acct["start"], acct["limit"]
    # ---- phase 1: eval (identical logic to race_select) ----
    floor = start - limit
    peak_eod = start
    cum, best = 0.0, -np.inf
    eval_res = {"outcome": "ALIVE_NEITHER", "day": None, "date": None,
                "best_day_share_at_pass": None}
    funded_start = None
    min_dist = np.inf
    for i, d in enumerate(days):
        eff = d["eff"]
        if len(eff):
            min_dist = min(min_dist, float(eff.min()) - floor)
            if (eff <= floor).any():
                eval_res.update({"outcome": "FAIL_BREACH", "day": i + 1,
                                 "date": d["date"]})
                break
        cum += d["result"]
        best = max(best, d["result"])
        if cum >= acct["target_profit"]:
            share = best / cum if cum > 0 else np.inf
            if i >= acct["min_days"] - 1 and share <= acct["consistency"]:
                eval_res.update({"outcome": "PASS", "day": i + 1,
                                 "date": d["date"],
                                 "best_day_share_at_pass": round(float(share), 4)})
                funded_start = i + 1
                break
        peak_eod = max(peak_eod, d["day_end"])
        floor = max(floor, peak_eod - limit)
    eval_res["min_distance_to_floor"] = round(float(min_dist), 2) if np.isfinite(min_dist) else None
    eval_days_used = eval_res["day"] if eval_res["day"] is not None else len(days)
    out = {"eval": eval_res, "funded": None, "payout_total_day": None,
           "eval_days_used": eval_days_used, "funded_days_used": 0}
    if funded_start is None:
        return out
    # ---- phase 2: funded, fresh start, following sessions ----
    bal = start
    floor2 = start - limit
    peak2 = start
    wins = 0
    cum2 = 0.0
    min_dist2 = np.inf
    funded_res = {"outcome": "ALIVE_NEITHER", "day": None, "date": None,
                  "winning_days_at_end": 0, "profit_at_end": None}
    for j in range(funded_start, len(days)):
        d = days[j]
        fprints = bal + (d["eff"] - d["day_start"])
        if len(fprints):
            min_dist2 = min(min_dist2, float(fprints.min()) - floor2)
            if (fprints <= floor2).any():
                funded_res.update({"outcome": "FAIL_BREACH",
                                   "day": j - funded_start + 1, "date": d["date"]})
                break
        res = d["result"]
        cum2 += res
        bal += res
        if res >= WIN_DAY_MIN:
            wins += 1
        if wins >= WIN_DAYS_NEEDED and cum2 >= PAYOUT_MIN_PROFIT:
            funded_res.update({"outcome": "PAYOUT",
                               "day": j - funded_start + 1, "date": d["date"],
                               "winning_days_at_end": wins,
                               "profit_at_end": round(cum2, 2),
                               "first_request_usd": round(0.5 * cum2, 2),
                               "trader_share_90pct_usd": round(0.9 * 0.5 * cum2, 2)})
            out["payout_total_day"] = j + 1
            break
        peak2 = max(peak2, bal)
        floor2 = max(floor2, peak2 - limit)
    funded_res["winning_days_at_end"] = wins
    funded_res["profit_at_end"] = round(cum2, 2)
    funded_res["min_distance_to_floor"] = round(float(min_dist2), 2) if np.isfinite(min_dist2) else None
    out["funded"] = funded_res
    out["funded_days_used"] = funded_res["day"] if funded_res["day"] is not None \
        else max(0, len(days) - funded_start)
    return out


# ----------------------------------------------------------------------
# TWO-PHASE Monte Carlo (new for this job; same bootstrap as fast_pass)
# ----------------------------------------------------------------------
def mc_two_phase(acct: dict, daily_pnl: np.ndarray, kappa: float) -> dict:
    BIG = 10**9
    paths = _paths(daily_pnl, acct["dll"])
    S, H = paths.shape
    eq = np.cumsum(paths, axis=1)
    # ---- eval phase (vectorized, identical rules to mc_select) ----
    peak = np.maximum.accumulate(
        np.hstack([np.zeros((S, 1)), eq]), axis=1)[:, :-1]
    dd_adj = (peak - eq) * kappa
    breach = dd_adj > acct["limit"]
    runmax = np.maximum.accumulate(paths, axis=1)
    day_idx = np.arange(H)[None, :]
    pass_mask = (eq >= acct["target_profit"]) \
        & (runmax <= acct["consistency"] * eq) \
        & (day_idx >= acct["min_days"] - 1)
    fb = np.where(breach.any(1), breach.argmax(1), BIG)
    fp = np.where(pass_mask.any(1), pass_mask.argmax(1), BIG)
    eval_fail = fb < fp
    eval_pass = fp < fb
    eval_days = np.where(eval_pass, fp + 1, BIG)
    # ---- funded phase: continue each passed path from day fp+1 ----
    k_idx = np.arange(H)[None, :]
    src = fp[:, None] + 1 + k_idx                # original day index of funded day k
    valid = eval_pass[:, None] & (src < H)
    src_c = np.clip(src, 0, H - 1)
    eq_f = np.take_along_axis(eq, src_c, axis=1)
    eq_at_pass = np.where(eval_pass, eq[np.arange(S), np.clip(fp, 0, H - 1)], 0.0)
    cum2 = eq_f - eq_at_pass[:, None]            # funded cumulative P&L at funded day k EOD
    daily2 = np.take_along_axis(paths, src_c, axis=1)
    wincount = np.cumsum((daily2 >= WIN_DAY_MIN) & valid, axis=1)
    peak2 = np.maximum.accumulate(
        np.hstack([np.zeros((S, 1)), cum2]), axis=1)[:, :-1]
    dd2 = (peak2 - cum2) * kappa
    breach2 = valid & (dd2 > acct["limit"])
    payout_mask = valid & (wincount >= WIN_DAYS_NEEDED) & (cum2 >= PAYOUT_MIN_PROFIT)
    fpay = np.where(payout_mask.any(1), payout_mask.argmax(1), BIG)
    fbr2 = np.where(breach2.any(1), breach2.argmax(1), BIG)
    funded_fail = eval_pass & (fbr2 < fpay)
    payout = eval_pass & (fpay < fbr2)
    total_days = np.where(payout, fp + 1 + fpay + 1, BIG)
    pay_days = total_days[payout]
    return {
        "p_eval_pass": round(float(eval_pass.mean()), 4),
        "p_eval_pass_le_5d": round(float((eval_pass & (eval_days <= 5)).mean()), 4),
        "p_eval_pass_le_10d": round(float((eval_pass & (eval_days <= 10)).mean()), 4),
        "p_eval_fail": round(float(eval_fail.mean()), 4),
        "p_funded_fail_after_pass": round(float(funded_fail.mean()), 4),
        "p_payout": round(float(payout.mean()), 4),
        "p_payout_le_10d_total": round(float((total_days <= 10).mean()), 4),
        "p_payout_le_20d_total": round(float((total_days <= 20).mean()), 4),
        "median_days_to_payout": int(np.median(pay_days)) if payout.any() else None,
        "p10_days_to_payout": int(np.percentile(pay_days, 10)) if payout.any() else None,
        "median_eval_days_among_passed": int(np.median(eval_days[eval_pass])) if eval_pass.any() else None,
    }


# ----------------------------------------------------------------------
# broker-rules compliance (copied from fast_pass, + phase idle windows)
# ----------------------------------------------------------------------
def _longest_idle(session_dates: list[str], trade_dates: set) -> int:
    longest = run = 0
    for sd in session_dates:
        if sd in trade_dates:
            run = 0
        else:
            run += 1
            longest = max(longest, run)
    return int(longest)


def compliance(cap: dict, hist2: dict) -> dict:
    folder, prefix = Path(cap["folder"]), cap["prefix"]
    tr_f = folder / f"{prefix}_trades_raw.csv"
    session_dates = cap["session_dates"]
    out = {"max_peak_qty_micros": cap["max_peak_qty"],
           "position_within_10_micros": bool(cap["max_peak_qty"] <= ACCT["max_micros"])}
    if not tr_f.exists() or cap["trades"] == 0:
        out.update({"trades": cap["trades"], "zero_overnight_holds": None,
                    "pct_trades_held_over_10s": None,
                    "pct_gross_profit_from_trades_over_10s": None,
                    "microscalping_rule_ok_both_over_50pct": False,
                    "longest_no_trade_stretch_sessions": len(session_dates),
                    "idle_rule_ok_under_5_sessions": False,
                    "note": "no trades in capture"})
        return out
    tr = pd.read_csv(tr_f)
    tr["ts_opened"] = pd.to_datetime(tr["ts_opened"], utc=True).dt.tz_convert("America/New_York")
    tr["ts_closed"] = pd.to_datetime(tr["ts_closed"], utc=True).dt.tz_convert("America/New_York")
    tr["pnl"] = tr["realized_pnl"].astype(str).str.replace(" USD", "").astype(float)
    same_day = (tr["ts_opened"].dt.date == tr["ts_closed"].dt.date)
    dur_s = tr["duration_ns"] / 1e9 if "duration_ns" in tr else pd.Series(dtype=float)
    over10 = dur_s > 10
    gross = float(tr.loc[tr["pnl"] > 0, "pnl"].sum())
    gross_over10 = float(tr.loc[over10 & (tr["pnl"] > 0), "pnl"].sum())
    trade_dates = {d.isoformat() for d in tr["ts_opened"].dt.date}
    longest = _longest_idle(session_dates, trade_dates)
    # phase windows from the historical two-phase path (dates, not idx:
    # session_dates are RTH dates; day_walk dates can include the same
    # dates in the same order for this dataset)
    eval_dates = session_dates[: hist2["eval_days_used"]]
    idle_eval = _longest_idle(eval_dates, trade_dates)
    idle_funded = None
    if hist2["funded"] is not None:
        f0 = hist2["eval_days_used"]
        f1 = f0 + hist2["funded_days_used"]
        idle_funded = _longest_idle(session_dates[f0:f1], trade_dates)
    out.update({
        "trades": int(len(tr)),
        "zero_overnight_holds": bool(same_day.all()),
        "pct_trades_held_over_10s": round(float(over10.mean()), 4) if len(dur_s) else None,
        "pct_gross_profit_from_trades_over_10s": round(gross_over10 / gross, 4) if gross > 0 else None,
        "microscalping_rule_ok_both_over_50pct": bool(
            len(dur_s) and over10.mean() > 0.5 and gross > 0 and (gross_over10 / gross) > 0.5),
        "longest_no_trade_stretch_sessions": longest,
        "idle_rule_ok_under_5_sessions": bool(longest < 5),
        "idle_stretch_eval_phase_hist": idle_eval,
        "idle_stretch_funded_phase_hist": idle_funded,
    })
    return out


def usable(comp: dict, cap: dict) -> bool:
    return bool(comp.get("position_within_10_micros")
                and comp.get("zero_overnight_holds")
                and comp.get("microscalping_rule_ok_both_over_50pct")
                and comp.get("idle_rule_ok_under_5_sessions"))


# ----------------------------------------------------------------------
# CONTROL VERIFICATION — must reproduce the known B+C3 Select figures
# ----------------------------------------------------------------------
def verify_control() -> dict:
    cap50 = load_capture(MIAMI, "BC3_risk50")
    cap75 = load_capture(MIAMI, "BC3_risk75")
    cap100 = load_capture(V2, "BC3_risk100")
    assert cap50 is not None and cap75 is not None and cap100 is not None, \
        "control captures missing"
    per_ts = per_minute(cap50["equity_df"], ACCT["start"])
    hist = race_select(per_ts, ACCT)
    days = day_walk(per_ts, ACCT["dll"])
    daily_pnl = np.array([d["result"] for d in days])
    mc = mc_select(ACCT, daily_pnl, cap50["kappa"])
    checks = {
        "BC3_risk50_net_expected": 1037.80, "BC3_risk50_net_got": cap50["net"],
        "BC3_risk50_min_dist_expected": 604.26,
        "BC3_risk50_min_dist_got": hist["min_distance_to_floor"],
        "BC3_risk50_hist_outcome": hist["outcome"],
        "BC3_risk75_net_expected": 1189.74, "BC3_risk75_net_got": cap75["net"],
        "BC3_risk100_net_expected": 2295.80, "BC3_risk100_net_got": cap100["net"],
        "BC3_risk50_mc_p_pass_fastpass": 0.968, "BC3_risk50_mc_p_pass_got": mc["p_pass"],
        "BC3_risk50_mc_median_days_fastpass": 99,
        "BC3_risk50_mc_median_days_got": mc["median_days_to_pass"],
    }
    assert cap50["net"] == 1037.80, f"CONTROL FAIL net: {cap50['net']}"
    assert hist["min_distance_to_floor"] == 604.26, \
        f"CONTROL FAIL min_dist: {hist['min_distance_to_floor']}"
    assert cap75["net"] == 1189.74, f"CONTROL FAIL net75: {cap75['net']}"
    assert cap100["net"] == 2295.80, f"CONTROL FAIL net100: {cap100['net']}"
    assert abs(mc["p_pass"] - 0.968) <= 0.01, f"CONTROL FAIL mc p_pass: {mc['p_pass']}"
    assert mc["median_days_to_pass"] is not None and abs(mc["median_days_to_pass"] - 99) <= 3, \
        f"CONTROL FAIL mc median: {mc['median_days_to_pass']}"
    print("CONTROL VERIFIED:", json.dumps(checks, indent=2), flush=True)
    return checks


# ----------------------------------------------------------------------
# candidates
# ----------------------------------------------------------------------
CANDIDATES = {
    "BC3": {"name": "Bot B+C3 pair (legacy control)",
            "sizes": {50: (MIAMI, "BC3_risk50"), 75: (MIAMI, "BC3_risk75"),
                      100: (V2, "BC3_risk100"), 150: (V2, "BC3_risk150"),
                      200: (V2, "BC3_risk200"), 250: (V2, "BC3_risk250")}},
    "ORB5A": {"name": "ORB-5 1R — 5-min opening range breakout, 1R target, opposite-edge stop (NEW)",
              "sizes": {u: (SPRINT, f"ORB5A_risk{u}") for u in (50, 75, 100, 150, 200, 250)}},
    "ORB5B": {"name": "ORB-5 1.5R — 5-min opening range breakout, 1.5R target, opposite-edge stop (NEW)",
              "sizes": {u: (SPRINT, f"ORB5B_risk{u}") for u in (50, 75, 100, 150, 200, 250)}},
    "ORB15A": {"name": "ORB-15 1R — 15-min opening range breakout, 1R target, opposite-edge stop (NEW)",
               "sizes": {u: (SPRINT, f"ORB15A_risk{u}") for u in (50, 75, 100, 150, 200, 250)}},
    "ORB15B": {"name": "ORB-15 1.5R — 15-min opening range breakout, 1.5R target, opposite-edge stop (NEW)",
               "sizes": {u: (SPRINT, f"ORB15B_risk{u}") for u in (50, 75, 100, 150, 200, 250)}},
    "PVW": {"name": "Bot P — VWAP trend-day rider, multiple pullback entries, trailing stop (NEW)",
            "sizes": {u: (SPRINT, f"PVW_risk{u}") for u in (50, 75, 100, 150, 200, 250)}},
    "QFH": {"name": "Bot Q — first-hour momentum continuation, trailing stop (NEW)",
            "sizes": {u: (SPRINT, f"QFH_risk{u}") for u in (50, 75, 100, 150, 200, 250)}},
    "RGAPC": {"name": "Bot R-C — overnight-gap continuation, first 90 minutes (NEW)",
              "sizes": {u: (SPRINT, f"RGAPC_risk{u}") for u in (50, 75, 100, 150, 200, 250)}},
    "RGAPF": {"name": "Bot R-F — overnight-gap fade, first 90 minutes (NEW)",
              "sizes": {u: (SPRINT, f"RGAPF_risk{u}") for u in (50, 75, 100, 150, 200, 250)}},
    "BHF": {"name": "Bot B-HF — Bot B pullback logic, 1R target, tighter cadence (NEW variant)",
            "sizes": {u: (SPRINT, f"BHF_risk{u}") for u in (50, 75, 100, 150, 200, 250)}},
    "KX": {"name": "Bot KX — Bot K trend rider + ORB-15 1R activity partner (NEW combined)",
           "sizes": {u: (SPRINT, f"KX_risk{u}") for u in (50, 75, 100, 150, 200, 250)}},
}


def main() -> None:
    control = verify_control()
    summary = {
        "job": "Payout sprint — can ANY strategy configuration produce a FIRST "
               "PAYOUT within ~10 trading days on the Tradeify Select 25K "
               "eval + funded path?",
        "account_model": {
            "eval": "start $25,000; pass at EOD cum profit >= $1,500 with best "
                    "day <= 40% of cum profit and day >= 3; fail on real-time "
                    "touch of the EOD-trailing $1,000 floor; max 10 micros; "
                    "flat by close; no overnight",
            "funded": "restarts at $25,000 fresh (eval profit does not carry "
                      "over); same trailing-floor failure rule; first payout "
                      "at first EOD with >= 5 winning days (>= $100 net each) "
                      "AND cum funded profit >= $500 (Flex request = 50% of "
                      "profit, $250 minimum request)",
            "structural_minimum": "eval >= 3 days + funded >= 5 winning days "
                                  "=> first payout cannot occur before day 8 "
                                  "under any strategy"},
        "data": "TopstepX MNQ 1-min, 2026-01-20 to 2026-04-15, 61 RTH sessions",
        "costs": "$1.00/contract/side placeholder commission + 1 tick slippage per fill (modeled)",
        "mc": "circular block bootstrap, block=5 sessions, 10,000 sims, "
              "250-session horizon, seed 20261122 (fast_pass method); intraday "
              "drawdown via capture kappa",
        "control_verification": control,
        "candidates": {},
    }
    rows = []
    for key, cand in CANDIDATES.items():
        entry = {"name": cand["name"], "sizes": {}}
        for usd in sorted(cand["sizes"]):
            folder, prefix = cand["sizes"][usd]
            cap = load_capture(folder, prefix)
            if cap is None:
                print(key, usd, "CAPTURE MISSING", flush=True)
                continue
            per_ts = per_minute(cap["equity_df"], ACCT["start"])
            hist2 = race_two_phase(per_ts, ACCT)
            days = day_walk(per_ts, ACCT["dll"])
            daily_pnl = np.array([d["result"] for d in days])
            mc2 = mc_two_phase(ACCT, daily_pnl, cap["kappa"])
            comp = compliance(cap, hist2)
            use = usable(comp, cap)
            size_entry = {
                "trades": cap["trades"], "net": cap["net"],
                "avg_daily_net": cap["avg_daily_net"],
                "profit_factor": cap["profit_factor"],
                "dd_trough": cap["dd_trough"], "dd_eod": cap["dd_eod"],
                "kappa": cap["kappa"], "max_peak_qty": cap["max_peak_qty"],
                "historical_two_phase": hist2,
                "monte_carlo_two_phase": mc2,
                "compliance": comp, "usable": use,
            }
            entry["sizes"][f"risk{usd}"] = size_entry
            rows.append({"candidate": key, "name": cand["name"], "risk_usd": usd,
                         "usable": use, "trades": cap["trades"], "net": cap["net"],
                         "dd_trough": cap["dd_trough"],
                         "max_peak_qty": cap["max_peak_qty"],
                         **{f"mc_{k}": v for k, v in mc2.items()}})
            print(key, f"risk{usd}", "| net", cap["net"], "tr", cap["trades"],
                  "trough", cap["dd_trough"], "peakqty", cap["max_peak_qty"],
                  "| HIST eval:", hist2["eval"]["outcome"], hist2["eval"]["date"],
                  "funded:", (hist2["funded"] or {}).get("outcome"),
                  "payout_day:", hist2["payout_total_day"],
                  "| MC pass<=5/<=10:", mc2["p_eval_pass_le_5d"], mc2["p_eval_pass_le_10d"],
                  "payout<=10/<=20:", mc2["p_payout_le_10d_total"], mc2["p_payout_le_20d_total"],
                  "failE/failF:", mc2["p_eval_fail"], mc2["p_funded_fail_after_pass"],
                  "medPay:", mc2["median_days_to_payout"], "usable:", use, flush=True)
        summary["candidates"][key] = entry
    rows_sorted = sorted(rows, key=lambda r: -r["mc_p_payout_le_10d_total"])
    summary["ranking_by_p_payout_le_10d"] = rows_sorted
    usable_rows = [r for r in rows_sorted if r["usable"]]
    summary["best_usable_by_p_payout_le_10d"] = usable_rows[0] if usable_rows else None
    summary["any_usable_payout_le_10d_ge_25pct"] = bool(
        any(r["mc_p_payout_le_10d_total"] >= 0.25 for r in usable_rows))
    summary["any_config_payout_le_10d_ge_25pct"] = bool(
        any(r["mc_p_payout_le_10d_total"] >= 0.25 for r in rows))
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print("\nBEST USABLE:", json.dumps(summary["best_usable_by_p_payout_le_10d"],
                                       indent=2, default=str))
    print("ANY USABLE >= 25% payout<=10d:", summary["any_usable_payout_le_10d_ge_25pct"])
    print("ANY CONFIG >= 25% payout<=10d:", summary["any_config_payout_le_10d_ge_25pct"])
    print("Wrote", HERE / "summary.json")


if __name__ == "__main__":
    main()
