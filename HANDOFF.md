# MNQ Strategy Research — AI Handoff Package

**Purpose.** This repository is a complete handoff of Esura's MNQ (Micro
E-mini Nasdaq-100 futures) day-trading strategy research, packaged so that
any AI collaborator (ChatGPT, Grok, Perplexity, Gemini, DeepSeek, Muse)
can test new strategies with the **same data, same harness, same cost
model, and same account rules** that produced the results below — and get
comparable numbers.

**Read this whole document before running or citing anything.** The
caveats are part of the results.

---

## 1. Project overview

- **What this is:** algorithmic day-trading strategy research on MNQ
  1-minute bars, run in NautilusTrader. Multiple strategy families have
  been implemented and tested against one prop-firm account target
  (Tradeify Select 25K, §5).
- **Research objective:** ~$1,000/day in gross profit across a total of
  **six accounts** (Esura's stated aspiration, 2026-11-19). **This
  objective is NOT achieved and is not supported by any tested
  strategy.** The best verified pace on the settled account is
  $17.01/day (B+C3 pair at $50 risk). See the results ledger (§7).
- **Current status (2026-11-23):**
  - No strategy is approved for live trading. Nothing has been
    purchased; no prop-firm account has been bought; nothing is live.
  - The leading candidate (Bot B + C3 pair) holds a **CONDITIONAL PASS
    to forward paper trading only** — not to an evaluation.
  - Before any evaluation purchase: a paper-trading gate (≥30 RTH
    sessions AND ≥90 trades on a live feed, PF ≥ 1.10 after *real*
    fees, degradation ≤ 25% vs backtest) must be passed.
  - Multi-year validation of B+C3 is still **inconclusive** — the
    multi-year data has not yet been acquired (§2.4).
- **Working style:** independent multi-AI collaboration. Research,
  implementation, and auditing are kept separate; disagreement and
  cross-checking are deliberate reliability mechanisms. Esura is the
  sole decision-maker and approval authority. **Never accept a PASS
  from another AI's report alone — re-verify.**

## 2. Data

### 2.1 Files in `data/`

| File | Coverage | Rows |
|---|---|---|
| `MNQ_1min_20260120_20260415.csv` | 1-minute bars, 2026-01-20 → 2026-04-15 (61 RTH sessions used) | 84,077 bars |
| `MNQ_daily_20250324_20260414.csv` | Daily bars, 2025-03-24 → 2026-04-14 | 270 rows |
| `MNQ_1h_20250321_20260415.csv` | 1-hour bars, 2025-03-21 → 2026-04-15 | 6,272 rows |
| `DATA_NOTES.md`, `MNQ_DATA_README.md` | Provenance and format notes from the source | — |

**SHA-256 of the 1-minute CSV:**
`129623f45308a98a1a345473ac5fe4d03d5d53f7dd177a608d946eb3d3d6ea99`

A tick file also exists in the source dataset —
`MNQ_tick_20260309_20260415.csv` (~29 MB, 528,939 rows, 2026-03-09 →
2026-04-15) — but is **not** included in this repo (size). It is in the
public source repo below if needed.

### 2.2 Provenance — read carefully

- The data was pulled from the **TopstepX / ProjectX Gateway API** (a
  real CME feed via the Topstep prop platform) and redistributed,
  **without a license**, in the public GitHub repository
  **https://github.com/axb0306/cme-futures-ohlc**. Any collaborator can
  clone that repo to obtain the identical source files.
- **Internal research only.** Do not redistribute further or use
  commercially.
- Provenance is *identified but NOT independently verified* against CME
  or a second vendor.

### 2.3 Validation performed

- 0 duplicate timestamps, monotonic, 0 OHLC violations, all closes on
  the 0.25 grid, only 3 missing minutes inside observed RTH spans.
- Daily-file closes match the 1-minute file's 16:59 ET session closes
  exactly on **59/59** overlapping days.
- 2026-02-16's short session (210 bars) is the Presidents Day early
  close, not data loss.

### 2.4 Flags and limits — attach these to every result

- **Two large weekend jumps are unverified:** Sun 2026-03-15 **+158.25
  pts** and Sun 2026-03-22 **−303.00 pts** (around the March contract
  roll; continuous-series splice vs genuine move unresolved). Low
  impact on intraday strategies; noted for the record.
- **The data ends 2026-04-15. It is NOT current.**
- **Only 61 RTH sessions of 1-minute data.** That is ~8% of a 3-year
  minimum sample. **Never present results on this sample as multi-year
  evidence.**
- **Selection bias (important):** Bot C's "C3" parameters (§6) were
  partly *selected after seeing results on this same 61-session
  sample*. Every figure involving C3 — including the headline B+C3
  pair numbers — is therefore partly in-sample and must be disclosed
  as such wherever it appears.
- **Multi-year validation is still pending.** The planned route is the
  Databento web portal: Esura signs up, orders `NQ.c.0` + `MNQ.c.0`
  OHLCV-1m as CSV split by month (est. ~$30–35, inside the $125 signup
  credit), and supplies the files. Until that happens, all credibility
  grades in this package are provisional. (MNQ itself launched
  2019-05-06, so ~7.5 years of MNQ history is the maximum that exists;
  NQ 1-minute data reaches back to 2010-06-06 and moves point-for-point
  with MNQ, making it a legitimate backtest stretch.)

### 2.5 Related dataset (crypto scalping tests)

The BTC tests in §7.5 used the public repo
**https://github.com/alessiostomeo/btc-cycle-data** — Bitstamp BTC/USD
daily/1h/1min 2012–2026, Binance BTCUSDT 1min/1h/1day 2018–2026, plus
Binance funding rate and open interest 2022–2026. Clone it from the
source; it is not mirrored here.

## 3. Environment and engine

- **NautilusTrader 1.231.0** on **Python 3.12.3** (isolated venv).
- Strategies are Nautilus `Strategy` classes consuming 1-minute bars.
  Signals are computed on completed bars and filled on the next bar —
  no lookahead was found in any audited run.
- **Slippage:** `FillModel(prob_slippage=1.0, random_seed=7)` — exactly
  **1 tick of slippage on every fill**.
- **Contract (MNQ):** $2.00 per point per micro contract; tick size
  0.25 points (= $0.50 per tick per micro).
- Harness code is in `harness/` (§10). Note the venv quirk in the
  original environment: the Nautilus venv python has pyarrow but no
  matplotlib; system python3 has matplotlib/pandas but no pyarrow.

## 4. Cost model — used in EVERY test in this package

- **Commission: $1.00 per contract per side** — a *placeholder*.
  Esura's real broker/prop-firm MNQ fee schedule is still an open
  input; real Tradeify/Rithmic fees will differ and will trim every
  pace figure in §7.
- **Slippage: 1 tick on every fill** (see §3).
- No spread model beyond that tick.
- **Any result reported without this cost model stated is incomplete.**
  When you run new tests, state the cost model in the report header.

## 5. The account — Tradeify Select 25K (SETTLED)

Esura settled the starting account on 2026-11-22: **Tradeify Select
25K**. Do not propose changing it.

### Evaluation rules (as modeled in the harness)

- Start $25,000; **profit target +$1,500**.
- **Drawdown: $1,000 EOD-trailing**, enforced *in real time* on net
  liquidation including unrealized P&L — a momentary touch of the
  trailing floor fails the account.
- **Flex** funded rules (not Daily); **no daily loss limit**.
- **40% evaluation consistency:** a pass is credited only at an
  end-of-day where cumulative profit ≥ $1,500 **and** the best single
  day ≤ 40% of cumulative profit **and** day ≥ 3.
- **Max position: 10 micros.** Micros only at this size class.
- **All positions flat by the close; no overnight holds.**
- **Idle rule:** at least 1 trade per week per account.
- **Bots:** permitted only if solely owned by the trader and used only
  within Tradeify (the same bot at another firm is prohibited); not
  HFT; ownership must be provable.
- Connection chosen at purchase is permanent: it must be **Rithmic**
  (Tradovate's API is closed to prop/eval accounts).

### Funded-account payout rules (Select Flex)

- The funded account **restarts at $25,000** — evaluation profit does
  **not** carry over.
- A payout can be requested after **5 winning days** (a winning day =
  ≥ **$100** profit that day).
- Request amount = **50% of total profit**, minimum request **$250**,
  cap **$1,250 per request**; profit split **90/10** in Esura's favor.
- Requesting a payout locks the funded drawdown floor at start + $100.
- **Microscalping payout rule (funded):** BOTH > 50% of trades held
  > 10 seconds AND > 50% of profits from trades held > 10 seconds,
  or no payout.

### If/when Esura says she is about to buy (reminders)

1. Promo code **NOV** (price with code: **$60**).
2. Pick the **Rithmic** connection.
3. **Flex**, not Daily.
4. The **40%** consistency option.

## 6. Strategy catalog

All strategy code is in `strategies/`. One file per bot.

- **Bot A — Opening Range Breakout** (`orb.py`). Break of the first
  30-minute opening range; stop at the opposite range edge; 2R target.
  **Dropped from the portfolio:** its stop is the full range width
  ($62–$182/contract), which usually exceeds small risk budgets — at
  0.50% risk on $50k it could afford only 10 trades in 61 sessions, and
  zero trades at $50–$150 risk. Standalone at $200: 5 trades, PF 2.31
  — too few trades to mean anything, and it fails the idle rule.
- **Bot B — Trend Pullback Scalper** (`pullback.py`). EMA20/50 trend +
  VWAP alignment; pullback entries; 1.5R target. Median hold ~300 s.
  The strongest standalone intraday performer after costs. (MNQ charges
  flat per-contract fees, which is why its math survives where the
  percentage-fee crypto tests died.)
- **Bot C — Failed Breakout / Mean Reversion** (`failed_breakout.py`),
  and its **C3 variant**: C plus (i) a relative range guard — only
  trade when the setup's range ≤ 1.5× the trailing-20-session median
  range, (ii) a minimum stop of 8 points, (iii) a 2R target cap.
  **C3's parameters were partly selected on the test sample itself —
  selection bias; disclose it wherever C3 figures appear.**
- **Bot D — VWAP Snapback Fade** (`vwap_fade.py`). **Dead** — no edge;
  dropped early.
- **Bot E — IBS Oversold Bounce** (`ibs_bounce.py`). Daily bars:
  Internal Bar Strength ≤ 0.20 → buy next open; exit at IBS ≥ 0.80 or
  after 5 sessions; long only. On MNQ daily: PF 6.05, 29 trades, 86%
  win — small-sample inflation; the published long-run expectation for
  this effect is PF ≈ 1.9–2.1. Its true mark-to-market drawdown is
  $9,748 at 2 contracts, and it **holds overnight for days, so it is
  structurally banned at Tradeify** — personal-account candidate only
  (paper first). Its edge is intraday, not overnight (overnight
  segments −136.8 pts vs intraday +6,135.2 pts on the sample).
- **Bot F — Momentum Scalper** (`momentum_scalp.py`). EMA-cross + VWAP
  momentum with an 8-point stop cap. **Never trades:** a signal audit
  found 123 qualifying signals, but MNQ 5-minute ATR(14) at those
  signals ran 17.1–84.1 pts (median ~47), so the 8-pt cap rejected
  100% of them. An 8-pt stop is 2–6× smaller than MNQ's actual 5-min
  volatility.
- **Bot G — Midday VWAP Mean Reversion** (`vwap_midday_mr.py`).
  **Dead:** 55 trades, PF 0.538, −$34.45/day at $50. VWAP fading has
  now failed on three markets in this project (BTC, US equities, MNQ).
- **Bot K — 15-Minute Trend Rider** (`bot_k_trend_rider.py`). ADX/EMA50
  direction, chandelier trailing stop, no fixed target. **The only new
  family with an edge:** at $100 risk, 13 trades, +$1,688, $27.67/day,
  PF 3.49. **Not usable as-is:** a 30-session no-trade stretch fails
  the idle rule, and 13 trades is thin evidence.
- **Bot L — Squeeze Breakout** (`bot_l_squeeze_breakout.py`).
  Bollinger-inside-Keltner release, 5-min. **Dead** (PF 0.92, fails
  idle rule).
- **Bot M — Last-Hour Momentum** (`bot_m_last_hour.py`). **Dead:**
  only 7 qualifying trades in 61 sessions, PF 0.757.
- **Bot N — Prior-Day High/Low Acceptance Breakout**
  (`bot_n_prior_day.py`). **Dead — the worst strategy tested in this
  project:** PF 0.29–0.32, −$67 to −$86/day.
- **Payout-sprint families** (all **dead or unusable**, P(payout ≤ 10
  trading days) = 0.00% at every size): VWAP Trend Rider
  (`bot_p_vwap_rider.py`, PF 0.90–0.93), First-Hour Momentum
  (`bot_q_first_hour.py`, PF collapses to 0.70), Gap
  Continuation/Fade (`bot_r_gap.py`, PF 0.30–0.70, rarely trades at
  legal sizes), Bot B-HF (a 1R/tighter-cadence redesign of Bot B that
  destroys B's edge: PF 0.77–0.81), short opening-range breakouts
  (5/15-min — same affordability wall as Bot A), and Bot KX (Bot K +
  an activity partner; does not fix K's idle defect at any viable
  size).

## 7. Results ledger (exact figures; cost model of §4 throughout)

### 7.1 The headline candidate — Bot B + C3 pair

On the Select 25K state machine (fit test, 61 sessions):

| Risk/trade | Trades | Net | $/day | PF | Notes |
|---|---|---|---|---|---|
| $25 | 34 (162 signals skipped) | $225.76 | $3.70 | 1.728 | Non-starter — most stops unaffordable |
| **$50** | 171 | **$1,037.80** | **$17.01** | **1.283** | Trough DD $396; max 3 micros; MC P(pass) 96.8–96.9%, P(fail) ~2%, median ~99–100 days |
| $75 | 194 | $1,189.74 | $19.50 | 1.194 | ~2× the drawdown of $50 — poor exchange |
| $100 | 197 | $2,295.80 | $37.64 | 1.255 | Fails the Select trailing floor historically (2026-02-16) |

Sizing **skips** a trade when one micro's stop exceeds the budget; it
never rounds up. That is why trade counts fall as risk shrinks.

On the larger Validation V2 test base ($250 risk): pair net
**$6,581.60, $107.90/day, PF 1.251**, EOD-trough drawdown **$3,379**,
intraday DD $3,618; Monte Carlo P(pass a $5,000-limit eval) **88.0%**,
median 85 days. At $200: $79.93/day, trough $2,674 — the prudent
setting; $250 is the ceiling; **$375 and $500 are rejected** (median
MC path breaches at $375). Verdict: **CONDITIONAL PASS at $200–$250
to paper trading only.** Break-even degradation ≈ 11% — the edge is
real on this sample but not thick.

### 7.2 The $1,000/day challenge (42 runs, 2026-11-19)

Best configuration (combined portfolio, $50k, 0.50% risk,
stop-at-$1,000 mode): **+$8,023.26, $131.53/day, PF 1.304**, reaching
$1,000 on only **6.6% of days**; out-of-sample PF **1.146**, below the
1.20 screening bar. **Verdict: $1,000/day NOT supported.**

### 7.3 Fast-pass sweep (can anything pass in 7–14 days?)

**No.** Best 14-day pass probability anywhere: 35.7% (B+C3 @ $250)
with a 55.4% failure probability — and that size is illegal on the
Select 25K (18 micros vs the 10 cap; $3,379 trough vs the $1,000
limit). Best *legal* 14-day odds: Bot K @ $150 at **7.0%**, with a
58.0% failure rate. Ranked by efficiency ($/day per $1,000 of trough
drawdown), **B+C3 @ $50 wins at 42.98** and is the only fully
compliant candidate in the field.

### 7.4 Payout sprint (can anything pay out within ~10 trading days?)

**No — nothing reaches even a 1% chance.** The test models both
phases: pass the eval, then the funded account restarts at $25,000
and must stack 5 winning days (≥$100) plus ≥$500 profit. Best legal
configuration: B+C3 @ $150, P(payout ≤ 10 trading days) = **0.03%**,
median 31 days among the rare successful paths, 43% eval-failure
rate. Best anywhere (illegal size): B+C3 @ $250 at 0.56%. At the safe
$50 size, median time-to-first-payout is **~152 trading days**. The
theoretical minimum payout day under *any* strategy is day 8 (3-day
eval minimum + 5 winning days). The binding constraints are the
funded restart and the five-winning-day count — properties of the
account's arithmetic, not of strategy choice.

### 7.5 Related strategy research (same protocol, other markets)

- **BTC scalping suite (Binance BTCUSDT 1-min, 4,562,315 bars,
  2018–2026): ALL 8 variants killed** (VWAP fade, Donchian breakout,
  RSI(2) mean reversion, Bollinger fade × 1m/5m) — negative under
  every cost scenario, in- and out-of-sample, every year. Least-bad:
  RSI(2) 5m at −$1,191/day, PF 0.157. A small gross edge exists
  ($4–$24/trade) but percentage-fee round-trip costs run $99–$524 per
  trade. Data: §2.5.
- **US equity scalping (SPY/QQQ):** costs stop being the problem and
  expose an *edge* problem — every intraday variant died. Only three
  **daily** variants survived, all tiny: RSI(2) SPY daily +$1.04/day
  (PF 1.778, max DD $1,498, positive 29/34 years), RSI(2) QQQ daily
  +$0.39/day (PF 1.228), Donchian QQQ daily +$0.48/day (PF 1.105).
- **IBS (Bot E rules) on index daily bars — the strongest daily edge
  found:** SPY 1993–2026: 943 trades, **PF 1.539, +$26,609,
  +$2.15/day**, max DD −$3,858, profitable 31/34 years, total fees
  $194.81 across all 943 trades. QQQ 1999–2026: **PF 1.416,
  +$2.59/day**, max DD −$5,483. On BTC daily the same rules are
  feed-dependent and **not established** (Bitstamp PF 1.095 vs Binance
  PF 0.875 — negative even at zero cost on Binance). Still ~$2/day at
  tested size — not a $1,000/day engine. **Esura PARKED the US-stocks
  IBS line on 2026-11-21. Do not reopen its follow-ups unless she
  does.**

## 8. Testing protocol — how to test a new strategy so results are comparable

This protocol is the transferable method. Deviating from it makes
numbers incomparable with §7.

1. **Complete fixed spec first.** A strategy is tested only if its
   rules are completely specified *in writing before running*: entry,
   exit, stop, target, timeframe, instrument, sizing rule. **Never
   invent missing rules.** (A creator's system shared with this
   project in Nov 2026 — Madame Trend Trades — was rejected as
   untestable for exactly this reason: the entry was specified but no
   stop-loss or profit-target rule exists anywhere in her free
   material.) If a spec has a gap, stop and flag the gap.
2. **Run on the 61-session sample** in `data/` with the §4 cost model,
   in NautilusTrader (§3) or a runner you have verified reproduces a
   known control figure exactly (the standard control: B+C3 @ $50 on
   the Select state machine = net $1,037.80, min floor distance
   $604.26).
3. **Sizing discipline:** position size comes from the risk budget
   and the stop distance; when one micro's stop exceeds the budget,
   the trade is **skipped, never rounded up**.
4. **Compliance checklist — a candidate failing ANY item is NOT
   USABLE, regardless of profit:** ≤ 10 micros peak; flat by close /
   zero overnight holds (verify from fill timestamps); funded
   microscalping rule (>50% of trades AND >50% of gross profit from
   holds > 10 s); idle rule (no 5+ consecutive sessions without a
   trade); 40% eval consistency at the pass point; no simultaneous
   opposing positions.
5. **Monte Carlo, not just the historical path:** block bootstrap
   (block size 5, 10,000 paths, 250-session horizon) through the eval
   state machine (and the funded phase, if payout timing matters).
   Report P(pass), P(fail), median days — a single historical path
   proves almost nothing on 61 sessions.
6. **Report per size tested:** net, $/day, profit factor, trade
   count, trough (peak-to-trough) drawdown, peak micros, P(pass),
   P(fail), median days, and the compliance result per rule.
7. **State the sample's limits in every report:** 61 sessions, one
   market regime slice (Jan–Apr 2026), C3 selection bias where
   relevant, placeholder fees, 1-tick slippage assumption. A result
   that hides its caveats will be sent back.

## 9. Standing constraints (not authorized by this document)

- **No live trading, no purchases, no account changes** are authorized
  by this handoff. Research only.
- The **Select 25K is the settled starting account** (§5). Do not
  re-propose alternatives.
- **Paper trading precedes any evaluation** (gate in §1).
- Risk settings approved for *research*: $100 / $150 / $200 / $250 per
  trade; $250 is the ceiling — do not exceed it without Esura's
  separate approval. (The Select-account fit work used $25–$100
  because that account's $1,000 floor binds sooner.)
- **Never substitute a short dataset and present it as a multi-year
  test.** If multi-year data cannot be obtained, report the missing
  data, its cost, and what is needed instead.
- The separate **crypto E001–E007 project** (Binance, sealed harness,
  Data Readiness NO / BLOCKED) is gated and **out of scope** for this
  package. Nothing here authorizes touching it.

## 10. Repository layout

- `HANDOFF.md` — this document.
- `README.md` — short index.
- `data/` — the MNQ dataset (§2): 1-minute, 1-hour, and daily CSVs
  plus the source's own notes/readme. (Tick file not included — see
  §2.1.)
- `strategies/` — every strategy implementation (§6), one `.py` per
  bot: `orb.py` (A), `pullback.py` (B), `failed_breakout.py` (C/C3),
  `vwap_fade.py` (D), `ibs_bounce.py` (E), `momentum_scalp.py` (F),
  `vwap_midday_mr.py` (G), `bot_k_trend_rider.py`,
  `bot_l_squeeze_breakout.py`, `bot_m_last_hour.py`,
  `bot_n_prior_day.py`, `bot_p_vwap_rider.py`,
  `bot_q_first_hour.py`, `bot_r_gap.py`.
- `harness/` — the evaluation machinery:
  - `select_eval_fast.py` — Select 25K eval state machine with the
    40% consistency rule enforced + Monte Carlo (fast-pass sweep).
  - `payout_eval.py` — two-phase (eval → funded) state machine that
    models time-to-first-payout (payout-sprint study).
  - `analysis.py`, `data_quality.py`, `run_shakedown.py` — the
    multi-year validation harness (built and shakedown-verified
    against the 61-session figures; awaiting multi-year data).
  - `config.py`, `instruments.py`, `sizing.py`, `controller.py` —
    the MNQ plan's shared configuration: contract spec, fee model,
    sizing, and portfolio controller.
- `results/` — the study reports behind §7:
  - `validation_v2_report.md` — Master Validation V2 (headline
    verdicts for B+C3 and Bot E).
  - `account_fit_test_report.md` — B+C3 fit tests across Tradeify
    account types, incl. the Select 25K ladder in §7.1.
  - `fast_pass_report.md` — the 7–14-day fast-pass + efficiency sweep
    (§7.3).
  - `payout_sprint_report.md` — the two-phase time-to-payout study
    (§7.4).
  - `challenge_report_2026-11-19.md` — the original 42-run $1,000/day
    challenge (§7.2).

*Package assembled 2026-11-23. Figures are as reported in the studies
cited; where a number appears in two studies with slightly different
Monte Carlo draws (e.g. P(pass) 96.8% vs 96.9%), both are within RNG
tolerance of the same underlying result.*
