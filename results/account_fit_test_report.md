# Tradeify Account-Fit Tests — Bot B+C3 (unchanged)

**Date:** 2026-11-22 · **Strategies:** Bot B (Trend Pullback) + Bot C3 (Failed Breakout v3), unchanged
**Data:** TopstepX MNQ 1-minute, 2026-01-20 → 2026-04-15 (61 RTH sessions; 74 equity-curve days)
**Costs:** $1.00/contract/side placeholder commission + 1 tick slippage per fill (modeled, as in Validation V2)
**Engine:** NautilusTrader 1.231.0, same runner as Validation V2 (`validation_v2/capture_bc3.py`)

**Control check:** the risk$250 re-run in this job reproduced the preserved Validation V2 capture
*exactly* — 196 trades, net $6,581.60, identical equity curve and identical trade P&Ls.

## New captures (risk = $ per trade on the $50k test base)

| Risk | Trades | vs 196 @ $250 | Net (61 sess) | $/day | PF | Max qty | κ (intraday adj.) |
|---|---|---|---|---|---|---|---|
| $25 | **34** | **−162 skipped** | $225.76 | $3.70 | 1.728 | 1 micro | 2.401 |
| $50 | 171 | −25 | $1,037.80 | $17.01 | 1.283 | 3 | 1.274 |
| $75 | 194 | −2 | $1,189.74 | $19.50 | 1.194 | 5 | 1.025 |
| $100 (preserved V2) | 197 | +1 | $2,295.80 | $37.64 | 1.255 | 7 | 1.056 |

**Why trades disappear at small budgets:** sizing returns 0 contracts whenever one micro's
risk (stop points × $2 + $2 round-trip cost) exceeds the budget — the trade is skipped, never
rounded up. At a $25 budget, any stop wider than ~11.5 points is unaffordable, which removes
162 of the ~196 signals (83%). At $50, 25 signals are lost; at $75, only 2. (The $100 level
taking one *more* trade than $250 is path dependence, not a skip.) Note also that $75 earns
barely more than $50 despite 50% more risk — the extra budget mostly buys slightly larger
size on the same trades, and its drawdown is roughly double ($814 vs $396 EOD-peak-to-trough).

Max position never binds: 7 micros at $100 vs the 10-micro (10K) / 20-micro (25K) caps.

## 1. Miami V2 10K — start $10,000 · target +$1,000 · STATIC floor $9,500 · soft DLL $300

Historical race at minute resolution (FAIL = intraday touch of $9,500 before PASS at $11,000;
DLL truncates a day at −$300). Monte Carlo: block bootstrap, 250-session horizon.

| Risk | Historical (intraday) | Min dist. to floor | Historical (EOD-only) | MC P(pass) | MC P(fail) | MC median days to pass |
|---|---|---|---|---|---|---|
| $25 | ALIVE — neither | $337.00 | ALIVE | 14.1% | 0.0% | 228 |
| $50 | **PASS 2026-03-27** | $229.28 | PASS 2026-03-30 | **94.9%** | 5.0% | 64 |
| $75 | **PASS 2026-03-25** | **$65.76** | PASS 2026-03-25 | 70.3% | 29.7% | 36 |
| $100 | **FAIL 2026-02-13** | −$43.48 | FAIL 2026-02-16 | — | — | — |

Context — preserved ladder through the same Miami 10K machine (historical only, no MC):

| Risk | Intraday | EOD-only |
|---|---|---|
| $150 | FAIL 2026-02-10 | FAIL 2026-02-10 |
| $200 | PASS 2026-01-26 | FAIL 2026-02-09 |
| $250 | PASS 2026-01-26 | PASS 2026-01-27 |
| $300 | PASS 2026-01-25 | PASS 2026-01-25 |
| $375 | PASS 2026-01-21 | PASS 2026-01-25 |
| $500 | PASS 2026-01-21 | PASS 2026-01-21 |

**Read this carefully — survival is non-monotonic in size on this single path.** The sample
opens with a strong run (late January), so $200–$500 sizes reach +$1,000 within the first
2–6 days, before the mid-February drawdown arrives; the static floor never trails, so those
early passes stand. That is a race won on timing, not robustness: the same levels' full-sample
trough drawdowns are $2,674–$6,509, i.e. 5–13× the $500 band. At the sizes actually sized for
this account: **$75 is the largest level that passes, clearing the floor by only $65.76**;
$50 passes with $229.28 to spare and has by far the best Monte Carlo (94.9% pass / 5.0% fail);
$100 and $150 fail outright in February; $25 survives everything but earns only $225.76 in 61
sessions — it would need ~4.4× the sample just to reach the target, and its MC pass rate
inside 250 sessions is only 14.1%. The $200 intraday-pass / EOD-fail split shows enforcement
basis matters: it touched $11,000 intraday on Jan 26 but never *closed* a day there, then
closed below $9,500 on Feb 9.

## 2. Miami V2 25K — start $25,000 · target +$2,000 · STATIC floor $24,000 · soft DLL $600

| Risk | Historical (intraday) | Min dist. to floor | Historical (EOD-only) | MC P(pass) | MC P(fail) | MC median days to pass |
|---|---|---|---|---|---|---|
| $25 | ALIVE — neither | $837.00 | ALIVE | 0.0% | 0.0% | — |
| $50 | ALIVE — neither | $729.28 | ALIVE | 94.7% | 0.3% | 134 |
| $75 | ALIVE — neither | $565.76 | ALIVE | 86.2% | 9.0% | 98 |
| $100 | **PASS 2026-03-26** | $247.52 | PASS 2026-03-26 | 89.2% | 10.7% | 53 |

The wider $1,000 static band makes this account far more forgiving: nothing fails historically,
and even $75 keeps $565.76 of clearance. The binding constraint here is the +$2,000 target —
$25/$50/$75 don't reach it inside the 61 sessions (full-sample nets $225.76 / $1,037.80 /
$1,189.74), so their historical verdict is "alive, unfinished," and the MC does the talking:
$50 is the safest profile (94.7% pass, 0.3% fail, but a slow median 134 days); $100 is the
fastest credible route (89.2% pass, median 53 days, 10.7% fail); $25 is a non-starter
(0.0% pass within 250 sessions at $3.70/day).

## 3. Select Flex 25K (3-day minimum) — start $25,000 · target +$1,500 · EOD-TRAILING $1,000, enforced in real time · NO DLL · 40% eval consistency

| Risk | Historical (intraday) | Min dist. to floor | Historical (EOD-only) | MC P(pass) | MC P(fail) | MC median days to pass |
|---|---|---|---|---|---|---|
| $25 | ALIVE — neither | $799.50 | ALIVE | 0.0% | 0.0% | 239 |
| $50 | ALIVE — neither | $604.26 | ALIVE | **96.9%** | 2.0% | 100 |
| $75 | ALIVE — neither | $186.26 | ALIVE | 76.0% | 23.9% | 63 |
| $100 | **FAIL 2026-02-16** | −$136.98 | FAIL 2026-02-16 | 75.4% | 24.6% | 33 |

The trailing floor is the binding constraint: it ratchets up behind the January run, so the
February drawdown — harmless under Miami's static floor — breaches at $100 (and the EOD-only
variant fails the same day; this is not an intraday artifact). No level passes historically:
$50/$75 stall below the +$1,500 target inside the sample despite never being in real danger
at $50 (min distance $604.26). **Consistency:** no historical pass occurred at any level, so
there is no at-pass best-day share to report (the 40% test was not failed — it never arose).
Monte Carlo (passes credited no earlier than day 3): $50 is again the standout — 96.9% pass,
2.0% fail, median 100 days. $75 and $100 carry ~24–25% MC failure rates.

## 4. Growth 25K — identical to Select Flex except soft DLL $600, no consistency rule, no 3-day minimum

| Risk | Historical (intraday) | Min dist. to floor | Historical (EOD-only) | MC P(pass) | MC P(fail) | MC median days to pass |
|---|---|---|---|---|---|---|
| $25 | ALIVE — neither | $799.50 | ALIVE | 0.0% | 0.0% | 231 |
| $50 | ALIVE — neither | $604.26 | ALIVE | **97.4%** | 1.7% | 99 |
| $75 | ALIVE — neither | $186.26 | ALIVE | 75.5% | 24.4% | 64 |
| $100 | **FAIL 2026-02-16** | −$136.98 | FAIL 2026-02-16 | 74.1% | 25.9% | 34 |

**Growth and Select Flex are historically indistinguishable on this sample:** at risk ≤ $100
no day's intraday loss from day-start ever reaches $600, so Growth's DLL never triggers
(0 DLL days at every level) and every historical figure is identical. The plans separate only
in Monte Carlo, where resampled paths do produce −$600 days and the DLL clip buys Growth a
small edge at $50 (97.4% vs 96.9% pass). Any real difference between these two plans lives in
days worse than anything in this 61-session sample.

## Cross-plan summary at the practical sizes

- **$25/trade is too small everywhere:** 83% of signals unaffordable, $3.70/day, MC pass ≈ 0–14%.
- **$50/trade is the risk-efficient size on every plan tested** — best or near-best MC pass
  rate on all four accounts (94.9% / 94.7% / 96.9% / 97.4%), lowest failure rates, comfortable
  historical floor clearance ($229–$729). Its cost is speed (median 64–134 days to pass).
- **$75 trades safety for speed** and the exchange rate is poor: MC failure jumps to 9–30%
  depending on plan, and its Miami 10K historical pass clears the floor by only $65.76.
- **$100 is plan-dependent:** passes Miami 25K (Mar 26) but fails Miami 10K (Feb 13) and both
  trailing 25K plans (Feb 16). The trailing floor, not the static band, is what kills it.
- **Static vs trailing:** on this path the static floor's weakness is the early-race effect
  (big sizes "pass" in week 1); the trailing floor's weakness is that it converts a normal
  mid-sample drawdown into a failure at $100. At $50, both designs look workable.

## Method notes & caveats

- Historical races use the worst print per minute (two strategies report equity on the same
  timestamps); tick-level excursions inside a minute are not observable. Floor checks on the
  outcome day use that day's full-minute range, as in the Growth 150K assignment.
- DLL flatten is modeled as filling at exactly −$DLL; a real flatten can overshoot. Miami 10K
  $75's $65.76 clearance is inside any plausible overshoot — treat that pass as fragile.
- The backtest's internal 2%-of-$50k daily kill switch ($1,000) never binds at these sizes;
  plan DLLs are enforced at the state-machine layer, the same treatment as the Tradeify
  $3,750 DLL in the 150K assignment.
- Monte Carlo resamples the observed 61 sessions only (74 equity-curve days, block 5,
  10,000 sims, seed 20261122); it cannot invent regimes the sample never contained. Kappa
  intraday adjustment is per-level (table above); at $25 κ = 2.40 because its EOD drawdown
  is tiny ($83.50), which inflates its adjusted drawdowns — its MC failure rate is ~0% anyway.
- Everything here inherits the standing caveats: one 61-session sample, C3's parameters were
  partly selected on this same sample, placeholder $1.00/side fees (real Tradeify/Rithmic
  MNQ fees will differ), 1-tick slippage is an assumption, and no multi-year data yet.
  These are fit tests on past data, not pass guarantees.

**Files:** `run_miami_capture.py` (new risk-level runs), `miami_eval.py` (state machines + MC),
`miami_fit_summary.json` (full machine-readable results), `data_outputs/` (CSVs in V2 format).
