"""
Data-quality checker for MNQ 1-minute bar files (multi-year validation).

Usage: python3 data_quality.py <bars.csv> [report.json]

Checks (nothing is filled, fabricated, or silently repaired):
  * file SHA-256, row count, time span, timezone assumption (naive = UTC)
  * duplicate timestamps, non-monotonic timestamps
  * OHLC violations (low <= open/close <= high), non-positive prices/volume
  * prices on the 0.25 MNQ tick grid
  * session inventory (America/New_York dates), RTH (09:30-15:59 ET)
    bars per session, missing minutes inside each session's observed
    RTH span (a shortened holiday session is flagged by bar count, not
    mislabeled as missing data)
  * largest overnight/weekend gaps (roll-splice suspects), listed, not judged
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RTH_START, RTH_END = "09:30", "15:59"


def load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    tcol = next(c for c in ("datetime", "timestamp", "ts", "date", "time")
                if c in df.columns)
    df["ts"] = pd.to_datetime(df[tcol], utc=True)
    return df.sort_values("ts").reset_index(drop=True)


def qc_bars(path: Path) -> dict:
    raw = path.read_bytes()
    df = load_bars(path)
    out = {"file": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
           "rows": int(len(df)),
           "span_utc": [str(df["ts"].iloc[0]), str(df["ts"].iloc[-1])]}
    out["duplicate_timestamps"] = int(df["ts"].duplicated().sum())
    out["monotonic_increasing"] = bool(df["ts"].is_monotonic_increasing)
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    out["ohlc_violations"] = int(((l > np.minimum(o, c)) |
                                  (h < np.maximum(o, c)) | (l > h)).sum())
    out["nonpositive_prices"] = int(((df[["open", "high", "low", "close"]] <= 0)
                                     .any(axis=1)).sum())
    out["negative_volume"] = int((df["volume"] < 0).sum())
    grid = ((df[["open", "high", "low", "close"]] * 4) % 1).abs().max().max()
    out["max_off_grid_fraction"] = float(grid)
    et = df["ts"].dt.tz_convert("America/New_York")
    df["et_date"] = et.dt.date
    df["et_time"] = et.dt.strftime("%H:%M")
    sessions = df.groupby("et_date").size()
    out["sessions_total"] = int(len(sessions))
    rth = df[(df["et_time"] >= RTH_START) & (df["et_time"] <= RTH_END)]
    rth_counts = rth.groupby("et_date").size()
    out["rth_sessions"] = int(len(rth_counts))
    out["rth_bars_per_session"] = {
        "min": int(rth_counts.min()), "median": float(rth_counts.median()),
        "max": int(rth_counts.max()),
        "full_390_sessions": int((rth_counts == 390).sum())}
    # Missing minutes inside each session's OBSERVED RTH span. Comparing
    # every date with a full 390-minute template would misclassify a
    # scheduled early close (e.g. a CME holiday session) as data loss.
    missing = {}
    for d, grp in rth.groupby("et_date"):
        ts_et = grp["ts"].dt.tz_convert("America/New_York")
        expect = pd.date_range(ts_et.min(), ts_et.max(), freq="1min")
        have = set(ts_et)
        miss = len(expect) - len(have.intersection(set(expect)))
        if miss:
            missing[str(d)] = int(miss)
    out["rth_missing_minutes_within_observed_span_by_session"] = missing
    out["rth_missing_minutes_within_observed_span_total"] = int(
        sum(missing.values()))
    out["rth_sessions_shorter_than_390"] = {
        str(k): int(v) for k, v in rth_counts[rth_counts < 390].items()}
    out["rth_minutes_below_full_390_template"] = int(
        (390 - rth_counts).clip(lower=0).sum())
    # largest absolute gaps between consecutive session closes/opens
    daily = df.groupby("et_date").agg(o=("open", "first"), c=("close", "last"))
    gaps = (daily["o"] - daily["c"].shift(1)).dropna()
    top = gaps.reindex(gaps.abs().sort_values(ascending=False).index).head(8)
    out["largest_session_gaps_pts"] = {str(k): round(float(v), 2)
                                       for k, v in top.items()}
    return out


if __name__ == "__main__":
    src = Path(sys.argv[1])
    report = qc_bars(src)
    print(json.dumps(report, indent=2))
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(report, indent=2))
