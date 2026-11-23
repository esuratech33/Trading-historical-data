# MNQ Historical Data — validated dataset for the Esura Trading Bot

Uploaded to Dropbox 2026-11-20 so Esura, Muse, and other AI collaborators
(ChatGPT, etc.) can reuse the same data in later research. This is the
dataset behind the $1,000/day MNQ profitability research challenge
(NautilusTrader 1.231.0 backtests, 2026-11-19).

## Source

Public GitHub repository **axb0306/cme-futures-ohlc** (32 stars, last updated
2026-04-15). The data comes from the **TopstepX / ProjectX Gateway API** —
a real CME feed delivered through the Topstep prop-trading platform —
redistributed on GitHub. The source repo has **no license**: treat this as
**internal research data only; do not redistribute**.

Downloaded 2026-11-19. Timestamps are **UTC**. Continuous front-month
series (the March 2026 contract roll sits inside the data).

## Instrument

MNQ — Micro E-mini Nasdaq-100 futures.
Contract multiplier $2 per index point; minimum tick 0.25 points;
tick value $0.50 per contract.

## Files

| File | Rows | Coverage | Size | SHA-256 |
|---|---|---|---|---|
| MNQ_1min_20260120_20260415.csv | 84,077 | 2026-01-20 → 2026-04-15 | 4,904,282 | 129623f45308a98a1a345473ac5fe4d03d5d53f7dd177a608d946eb3d3d6ea99 |
| MNQ_daily_20250324_20260414.csv | 270 | 2025-03-24 → 2026-04-14 | 16,681 | ea1671eac8041405db1b87caddaf0d23d23ba4ffa8e70ebf74c0c9c98c29a5c6 |
| MNQ_1h_20250321_20260415.csv | 6,272 | 2025-03-21 → 2026-04-15 | 376,087 | 2ef39fbb73f0fe661a7f404c129ed73ec8f2f8449f847af8ac5bffbbbb0deec9 |
| MNQ_tick_20260309_20260415.csv | 528,939 | 2026-03-09 → 2026-04-15 | 29,979,112 | 0db60ca733f6d47c69230485b0ecb0d3f250c50e19f762fcd544d22fbb30a244 |
| DATA_NOTES.md | — | validation detail | 3,317 | bea402f183b7c76f1708ce9aeba7f5d2fac992e56953f8d71dc1c26021e22426 |

Verify a downloaded copy with `sha256sum` against the hashes above.

## Validation (done 2026-11-19, see DATA_NOTES.md)

- 0 duplicate timestamps, monotonic, 0 OHLC violations, all closes on the
  0.25 tick grid, no zero/negative volume.
- 74 trading days in the 1-minute file; median 1,380 bars/day (full Globex
  day). Only **3 missing minutes** total (2026-02-05 ~01:51–01:53 ET);
  all other gaps are the daily halt or the Presidents Day early close.
- Repository daily closes match the 1-minute file's 16:59 ET closes
  **exactly (0.00 pts) on 59/59 overlapping days**.

## Known flags — read before using

1. **Two large weekend jumps are unverified**: Sun 2026-03-15 +158.25 pts
   and Sun 2026-03-22 −303.00 pts vs the prior Friday closes. Genuine move
   vs a continuous-contract splice around the 2026-03-20 expiration is
   unresolved. Low impact on intraday strategies; do not use these files
   for overnight/weekend-gap research without resolving this.
2. **Provenance is identified, not independently verified.** A Yahoo
   Finance cross-check timed out and Stooq served a bot-check from the
   research VM on 2026-11-19. Treat the data as good for the intraday
   research it was validated for, not as exchange-certified.
3. **Not current.** The source repo stopped updating 2026-04-15. The
   1-minute file covers only ~3 months / **61 RTH sessions** — enough for
   a train/validation/out-of-sample split, but a thin one (one volatility
   regime, small trade counts). Do not claim high statistical confidence
   from this window alone.
4. RTH sessions are 09:30–16:00 ET; strategies in this project flatten
   at 15:59 ET and never hold overnight.

## How it was used

Loaded into NautilusTrader as MNQM26.GLBX (activation 2025-12-01,
expiration 2026-06-19) for the $1,000/day research challenge:
three strategies (Opening Range Breakout, Trend Pullback, Failed
Breakout), $50,000 / $25,000 accounts, dynamic risk sizing, $1.00
per-contract-per-side commission (assumed) and 1 tick of slippage.
Full results: `results/challenge_2026-11-19.json` (42 runs).
