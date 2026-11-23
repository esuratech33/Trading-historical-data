# Esura Trading Bot — Master Validation Report

Validation Project v2.0 · 2026-11-20 · Independent validation of
Bot E (IBS Oversold Bounce) and Bot B + Bot C3 for possible
Tradeify deployment. **Nothing in this package authorizes a
purchase or live trading.** Companion documents: BOT_E report,
BOT_B_C3 report, TRADEIFY_RULES_AND_COMPLIANCE, FIVE_ACCOUNT_
PORTFOLIO_SIMULATION, MONTE_CARLO_AND_STRESS_TESTS, FORWARD_PAPER_
TRADING_PROTOCOL, FINAL_STRATEGY_DECISION.

## 1. Phase 1 — Audit of all previous tests

**What the previous tests were.** Both strategies were implemented
by Muse in NautilusTrader 1.231.0 (Python 3.12.3, isolated venv)
and actually executed — code, run logs, and result JSONs exist for
every round. Bot B's rules come from Esura's master plan; Bot C3 is
Bot C plus two labeled modifications (min stop 8 pts, 2R cap);
Bot E's rules and parameters come from published research.

**Data used previously (and again here — see §2).** MNQ bars from a
GitHub redistribution of the TopstepX/ProjectX feed: 1-minute file
Jan 20 – Apr 15 2026 (84,077 bars, 61 RTH sessions used) and a daily
file Mar 24 2025 – Apr 14 2026 (270 sessions). Validation performed
in earlier rounds: no duplicates, monotonic timestamps, no OHLC
violations, closes on the 0.25 grid, repo daily closes match the
1-minute file's session closes exactly on 59/59 overlapping days.
**Provenance is identified but not independently verified** against
CME or a second vendor (attempts via Yahoo/Stooq were blocked from
this environment). Two large weekend gaps (Mar 15 +158 pts, Mar 22
−303 pts) around the March contract roll remain unexplained —
continuous-series splice vs genuine move unresolved; low impact on
intraday strategies, noted for the record.

**Costs previously used:** $1.00/contract/side placeholder
commission (all-in guess; the real exchange + NFA + broker schedule
was never inserted) + exactly 1 tick slippage per fill. No spread
model beyond that tick; fills at next-bar open for Bot E and
market/stop mechanics for the intraday bots; no lookahead found —
signals are computed on completed bars and filled on the next bar.
**Parameter-selection leakage:** Bot B — none (rules predate
testing). Bot E — none (published parameters). **Bot C3 — yes,
material:** its two modifications were selected after viewing Bot
C's results on the same 61 sessions later used to report C3's
performance. Its "out-of-sample" split is therefore not a clean
holdout for those choices.

**Reproduction results (this project, independent re-runs +
an independent metrics recomputation from raw captures):**

| Claim | Result |
|---|---|
| Bot E PF 6.05, win ~86%, 270 sessions | **Reproduced exactly** (PF 6.052, 86%, 29 trades, nets to the cent at 1/2/3 contracts; pandas cross-check PF identical, net within $57) |
| Pair $250: $108–113/day, DD $3,256 | **Reproduced exactly** ($107.90/day by UTC-close attribution; $113.47 on the original session-date basis) |
| Pair $375: $117–174/day, DD $4,666 | **Reproduced exactly** |
| Pair $500: ~$215/day, DD $6,202 | **Reproduced exactly** ($215.36) |
| $375 bar-level drawdown $4,912 | **Reproduced exactly** (twice) |

Classification: all prior headline results = **verified/reproduced**.
Two prior figures are corrected by this audit: (1) Bot E's drawdown
was effectively unreported (a metrics defect printed $0; the true
mark-to-market figure is $9,748 at 2 contracts); (2) the "2.5
months per evaluation" estimate ignored losing paths (Monte Carlo
median at $250 risk: 85 trading days; see §4).

## 2. Phase 2 — Historical data: status and the binding constraint

**No new data was acquired in this project**, because the only
credible route to multi-year CME data (Databento GLBX.MDP3) requires
Esura to open an account and provide an API key. Prior research
(Nov 17) estimated 15 years of NQ 1-minute continuous data at
roughly $0–5 after Databento's signup credit, with daily data
effectively free at this scale; that quote must be re-confirmed at
purchase. Tick data exists locally only for Mar 9 – Apr 15 2026.

**Consequence, stated plainly:** every conclusion in this package
rests on 61 intraday sessions (one regime cluster: a choppy
winter–spring 2026) and 270 daily sessions (13 months, no bear
market). Formal walk-forward across regimes and a final untouched
holdout are **impossible on this data** and were not faked:
chronological train/validation/out-of-sample splits were used
instead, and both strategies' statistical credibility is graded
accordingly (Bot E: moderate-low; Bot B + C3: low). The single
highest-value next investment in this project is the multi-year
dataset, not more testing on this one.

## 3. What this project executed (Phases 3–15, condensed)

- Rebuilt/verified both strategies from the preserved originals;
  no rule changes. New labeled versions created only for Bot E's
  deployment question (v1.1 flat-by-close, v2.0 single-day, v2.1
  RTH-only) — v1.0 untouched.
- Chronological splits for both strategies (in their reports).
- Parameter sensitivity: Bot E 125-cell grid (all profitable;
  neighborhood min PF 1.228); Bot C3 min-stop inert across 6–10 pts,
  target plateau 2.0–2.5R; Bot B target peaks at its original 1.5R.
- Cost scenarios: adverse (+$0.50/side) cuts pair net 21–24% and
  makes the $375 historical path breach Tradeify's limit.
- Full statistics, concentration, regime caveats: pair top-3 share
  23% (healthy); Bot E profit in 13/14 months.
- Monte Carlo (10,000 block-bootstraps) + Tradeify evaluation
  simulation + degradation to break-even (~11% for the pair).
- Tradeify rules re-verified on the firm's own help center;
  secondary firms checked (compliance report).

## 4. Headline findings

1. **Both prior backtests were legitimate and reproduce exactly.**
   The doubts were not about honesty; they are about sample size
   and risk measurement.
2. **$375 risk is rejected.** Its $88 historical headroom was a
   favorable draw: the median Monte Carlo path at $375 breaches
   the $5,000 limit (median max DD $6,309; P(fail) 27.9%).
3. **$250 risk is the ceiling, $200 the prudent setting.** At $250:
   P(pass) 88%, median 85 days to pass, historical EOD-trough
   $3,379 (68% of the limit).
4. **Five accounts are one bet.** P(all 5 pass) ≈ P(1 passes);
   expected funded 4.42 of 5 at $250; expected total evaluation
   spend ≈ $2,000; first payouts realistically month 6–8.
5. **$1,000/day is not achievable** inside Tradeify's rules with
   these strategies. Defensible planning figure at $250 × 5
   accounts: ~$430–490/day net to Esura while funded accounts live.
6. **Bot E's edge is intraday, not overnight** (overnight segments
   −2.3% of gross). Its flat-by-close form (v1.1) preserves the
   result in replication (+$24,091 vs +$23,820) — but v1.0's true
   mark-to-market drawdown ($9,748 at 2 ct; 76% of resamples breach
   $5,000) bars the original from any $5,000-limit firm, and the
   published long-run expectation for this effect is PF ≈ 2 with
   losing bear years, not PF 6.

## 5. Verdicts (detail in FINAL_STRATEGY_DECISION)

- **Bot B + C3: CONDITIONAL PASS at $200–$250 risk** — to forward
  paper trading only.
- **Bot E: CONDITIONAL PASS as a personal-account strategy** (paper
  first); **FAIL for prop deployment in v1.0 form**; v1.1 is a
  research candidate, not a deployment candidate.
- **$375 and $500 risk settings: FAIL** for Tradeify deployment.

## 6. Reproduction instructions

Environment: `~/workspace/nautilus/.venv` (nautilus_trader 1.231.0,
Python 3.12.3). Code: `~/workspace/nautilus/mnq_plan/` (originals
untouched; this project's scripts in `validation_v2/`:
capture_bc3.py, summarize_bc3.py, bot_e_analysis.py, bot_e_rth.py,
monte_carlo.py, sensitivity_bc3.py, run_bote_nautilus.py).
Data: Dropbox "MNQ Historical Data" (SHA-256 of the 1-minute file
129623f4…). Outputs: `validation_v2/data_outputs/` — trade-level
CSVs, daily P&L CSVs, equity paths for the headline runs, all
summary JSONs, uploaded with this package.
