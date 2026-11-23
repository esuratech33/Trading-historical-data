# Fast-Pass + Efficiency Sweep — Select Flex 25K (2026-11-22)

**Question 1 (Esura's requirement):** can any strategy pass the Tradeify
Select Flex 25K evaluation — +$1,500 inside the $1,000 EOD-trailing
drawdown — within **7–14 trading days**?

**Answer: NO.** Nothing meets the requirement (MC P(pass ≤ 14 days) ≥ 50%)
at any size tested. The best 14-day pass probability anywhere in the study
is **35.7%** (B+C3 at $250/trade), and it comes with a **55.4%** probability
of blowing the account — and that size is not even legal on this account
(18 micros vs the 10-micro cap; $3,379 trough vs the $1,000 limit). Among
account-legal configurations the best 14-day odds are Bot K's **7.0%**
(at $150, with a 58.0% failure rate). The speed/safety exchange rate is
priced in full below.

**Question 2 (primary ranking):** which strategy makes the most money
per unit of risk — efficiency = $/day per $1,000 of drawdown at the
drawdown-safe size?

**Answer: a previously-tested strategy wins, plainly.** The legacy
**B+C3 pair** (identical numbers for the A+B+C3 portfolio, because Bot A
takes no trades at that size) at **$50/trade** is #1: **$17.01/day,
efficiency 42.98, trough $396**, MC P(pass) 96.8%, median 99 days.
None of the four brand-new families (K/L/M/N) outranks it; three of the
four have no drawdown-safe size at all, and all four fail Tradeify's
idle rule (see compliance).

Data: 61-session TopstepX MNQ 1-min sample (2026-01-20 → 2026-04-15),
standard cost model ($1.00/contract/side placeholder + 1-tick slippage).
New bots ran fresh Nautilus captures (max 10 micros enforced in the
engine); legacy candidates were computed from their existing captures —
no re-runs. MC: circular block bootstrap, block 5, 10,000 sims,
250-session horizon, seed 20261122.

**Method change vs prior jobs:** the 40% evaluation consistency rule is
now *enforced*, not just reported — a pass counts only at the end of a
day where cumulative profit ≥ $1,500 **and** the best single day is
≤ 40% of cumulative profit **and** the 3-day minimum is met. Breaches
remain real-time against the trailing floor. This makes pass crediting
an end-of-day determination (slightly more conservative than the
intraday-touch crediting used before; the B+C3 $50 baseline moved from
96.9% / median 100 to 96.8% / median 99, so the change is immaterial
for slow strategies and binding only for lumpy ones).

---

## Ranked by efficiency (at each candidate's drawdown-safe size)

Safe size = largest tested size whose historical EOD-peak-to-intraday-
trough drawdown ≤ ~$700 (≈ ⅔ of the $1,000 limit).

| # | Candidate | Safe size | $/day | Trough DD | Efficiency ($/day per $1k trough) | Trades | MC P(pass) | MC P(≤14d) | MC P(fail) | Median days |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **B+C3 pair (legacy)** | $50 | **17.01** | $396 | **42.98** | 171 | 96.8% | 0.0% | 2.2% | 99 |
| 1= | A+B+C3 portfolio (legacy) | $50 | 17.01 | $396 | 42.98 | 171 | 96.9% | 0.0% | 2.1% | 99 |
| 2 | Bot A — ORB (legacy) | $200 | 7.89 | $256 | 30.88 | **5** ⚠ | 58.8% | 0.0% | 11.9% | 152 |

⚠ Bot A's row rests on 5 trades in 61 sessions and it fails the idle
rule — it is ranked here on arithmetic, but it is **not usable** (below).

**No drawdown-safe size exists** (at any tested size) for: Bot K
(best trough $846 @ $100), Bot L ($1,367 @ $100), Bot M ($753 @ $100),
Bot N ($5,746 @ $100), Bot B alone ($2,353 @ its only capture, $250),
C3 alone ($1,683 @ $250), Bot G ($2,779 @ $50). Bot F never trades at
any size (trough $0, $0/day — efficiency undefined, and it fails the
idle rule by construction).

---

## The fast-pass table — what 7–14 days actually costs

Ranked by MC P(pass ≤ 14 days), all sizes, legal or not:

| Configuration | P(≤7d) | P(≤14d) | P(fail) | Median days | Legal on this account? |
|---|---|---|---|---|---|
| B+C3 @ $250 | 19.3% | **35.7%** | **55.4%** | 9 | **No** — 18 micros, $3,379 trough |
| A+B+C3 @ $200 | 13.4% | 34.7% | 48.3% | 11 | **No** — 14 micros, $2,362 trough |
| B+C3 @ $200 | 12.0% | 31.1% | 49.7% | 12 | **No** — 14 micros, $2,674 trough |
| C3 alone @ $250 | 4.7% | 21.8% | 54.3% | 15 | **No** — 11 micros, $1,683 trough |
| B alone @ $250 | 4.2% | 21.7% | 61.1% | 14 | **No** — 17 micros, $2,353 trough |
| B+C3 @ $150 | 4.7% | 21.1% | 43.0% | 18 | No — $1,868 trough > limit |
| **Bot K @ $150 (NEW)** | 1.0% | **7.0%** | **58.0%** | 27 | No — $1,691 trough > limit |
| **Bot K @ $100 (NEW)** | 0.7% | **4.4%** | **27.7%** | 50 | Trough $846 < limit, but fails idle rule |
| B+C3 @ $50 (the efficient one) | 0.0% | 0.0% | 2.2% | 99 | Yes — and fully compliant |

**The exchange rate, stated plainly:** passing in two weeks means making
$1,500 at roughly $110–$215/day. The most efficient strategy in this
project makes $17/day at the size the drawdown allows. Every
configuration that gets 14-day pass odds even to ~1-in-5 does so by
sizing into a trough drawdown 1.7–3.4× the account limit, at which point
the failure probability (43–61%) exceeds the fast-pass probability.
There is no point on the tested frontier where P(pass ≤ 14d) ≥ 50% —
the requirement is not a matter of strategy choice on this account;
the arithmetic of $1,500 / $1,000 / 61 sessions of MNQ does not contain
it. The 40% consistency rule, notably, is *not* the binding constraint:
median best-day share at simulated passes runs 11–37%, under the limit
almost everywhere. The binding constraint is raw pace vs the floor.

---

## The new families (K / L / M / N)

### Bot K — 15-Minute Trend Rider (NEW) — the only new bot with an edge, and still not usable
- **$100:** 13 trades ⚠, **+$1,688, $27.67/day, PF 3.49**, trough **$846**
  (over the $700 safe line, under the $1,000 limit). Historical race:
  **PASS on 2026-04-15** (the final session), best-day share at pass
  34.5% ✓. MC: P(pass) 72.3%, P(≤7d) 0.7%, P(≤14d) 4.4%, P(fail) 27.7%,
  median 50 days.
- **$150:** 44 trades, +$1,178, $19.31/day, PF 1.35, trough $1,691 —
  historical **FAIL 2026-02-26**; MC P(fail) 58.0%.
- **Compliance @ $100:** position ≤ 10 micros ✓ (max 1); zero overnight
  holds ✓ (latest close 15:55); microscalping rule ✓ (100% of trades
  and 100% of gross profit from holds > 10 s); opposing positions
  impossible ✓; **idle rule ✗ — longest no-trade stretch 30 sessions.**
  **Verdict: NOT USABLE as specified** (idle rule), and its edge rests
  on 13 trades. It is the one new idea worth remembering if the rules
  or the account ever change — nothing more.

### Bot L — Squeeze Breakout (NEW) — dead
- $100: 30 trades, −$192, PF 0.92, trough $1,367, historical FAIL
  2026-03-18, MC P(fail) 80.1%. $150: 47 trades, −$362, PF 0.92,
  trough $2,435, MC P(fail) 63.1% (it did pass historically on
  2026-03-06 at a 25.6% best-day share — on a losing full-sample
  strategy, which is luck, not edge).
- Compliance @ $100: position/overnight/microscalping ✓; **idle ✗ (7
  sessions)**. **Verdict: NOT USABLE** — negative expectancy and no
  safe size; the squeeze-release premise does not pay on this data.

### Bot M — Last-Hour Momentum (NEW) — dead
- Only **7 qualifying trades in 61 sessions** at every size ⚠ (the
  0.8×-median-range + agreement gate is very strict). PF 0.757,
  −$2.46/day @ $100, trough $753; $150/$200 fail historically
  (2026-03-02), MC P(fail) 93.5–96.8%.
- Compliance @ $100: position/overnight/microscalping ✓; **idle ✗
  (21 sessions)**. **Verdict: NOT USABLE** — too rare to satisfy the
  idle rule and what little it trades loses money.

### Bot N — Prior-Day Level Acceptance (NEW) — decisively dead
- 11 trades, **PF 0.29–0.32, −$66.94/day @ $100, −$86.12/day @ $150**,
  troughs $5,746 / $7,747 (5.7–7.7× the limit). Historical FAIL on
  2026-02-02 at both sizes; MC P(fail) **98.5–98.8%**. Two closes of
  "acceptance" above PDH/PDL were, on this sample, an invitation to
  be run over: price kept going through the level's stop or reversed
  long before the full-range target.
- Compliance @ $100: position (max exactly 10) ✓; overnight ✓;
  microscalping ✓; **idle ✗ (13 sessions)**. **Verdict: NOT USABLE** —
  the worst strategy tested in this project to date.

---

## Legacy candidates

### B+C3 pair / A+B+C3 portfolio — #1 efficiency, fully compliant, slow
Identical at the safe size ($50): 171 trades, $17.01/day, PF 1.283,
trough $396, max 3 micros. Historical: alive (neither passed nor
failed in-sample). MC: P(pass) ~97%, P(fail) ~2%, **median 99 days,
P(≤14d) 0.0%**. Compliance @ $50: **every check passes** — ≤10 micros
✓, zero overnight ✓ (latest close 15:50), microscalping 100%/100% ✓,
idle stretch 3 sessions ✓, median best-day share at simulated passes
11.4% (limit 40%) ✓, no opposing positions ✓. **Verdict: USABLE —
the recommendation stands, at the known price: months, not weeks.**
Bigger sizes buy speed at the priced exchange rate (see fast-pass
table): @ $100 the pair fails historically (2026-02-16) with MC
P(fail) 24.6%; @ $150, 43.0%.

### Bot A — Opening Range Breakout (legacy)
Trades only at $200 (its full-range stop is unaffordable below that):
5 trades ⚠, $7.89/day, PF 2.31, trough $256 → efficiency 30.88,
ranked #2 on arithmetic. Compliance @ $200: micros ✓ (max 1);
overnight ✓ (one trade closed 15:59 — the legacy config flattens at
15:59, not 15:55; still same-day); microscalping ✓ 100%/100%;
**idle ✗ — 21 sessions** (it trades ~1 day in 12). **Verdict: NOT
USABLE** (idle rule; 5-trade evidence base).

### Bot B alone / C3 alone (legacy, single $250 captures only)
No other sizes exist and P&L cannot be legitimately rescaled
(discrete sizing), so neither has a computable safe size. At $250:
B — $67.79/day, trough $2,353, **17 micros ✗**; C3 — $79.04/day,
trough $1,683, **11 micros ✗**. Both fail historically in February;
MC P(≤14d) ~22% each against P(fail) 54–61%. Both pass the
overnight/microscalping/idle checks. **Verdict: NOT USABLE on this
account at the only size ever captured** (position cap + drawdown);
their value is as components of the pair, where sizing keeps them
legal.

### Bot F — Momentum scalper, 8-pt stop cap (legacy)
Zero trades at every size (the 8-pt stop cap rejects every signal —
MNQ's 5-min ATR runs 17–84 pts). $0/day, trough $0, P(pass) 0%.
**Verdict: NOT USABLE** — it cannot satisfy the idle rule because it
cannot trade at all.

### Bot G — Midday VWAP mean reversion (legacy)
Loses at every size (PF 0.51–0.54; −$34.45/day at its smallest),
trough $2,779 @ $50, MC P(fail) 90.7%. Idle stretch 7 ✗.
**Verdict: NOT USABLE** — negative expectancy; VWAP fading is now
dead on three markets in this project (BTC, US equities, MNQ).

---

## Bottom line

1. **The 7–14 day pass does not exist** in anything tested — new or
   old, legal or not. The ceiling is ~36% (at an illegal size with a
   55% blow-up rate); within the account's actual rules it is ~7%.
   This is a property of the account's $1,500 target / $1,000 floor
   against MNQ's daily P&L distribution, not of any one strategy.
2. **On efficiency — money per unit of risk — the previously-tested
   B+C3 pair still wins** (42.98), and it is the only candidate that
   is both top-ranked and fully broker-compliant. The recommendation
   is unchanged: B+C3 at $50/trade on the Select 25K, median ~99
   trading days to pass at ~97% simulated probability.
3. Of the new families, only **Bot K** showed a real (if thin and
   idle-rule-breaking) edge: PF 3.49 at $100 on 13 trades, the highest
   $/day ($27.67) of any near-legal configuration. L, M and N are
   rejected on evidence.

## Caveats (standing)
Single 61-session sample; C3's parameters were partly selected on
this same sample; fees are the $1.00/side placeholder, not Tradeify's
real schedule; MC resamples only the observed sample and cannot
invent regimes it never contained; candidates with < 30 trades
(K @ $100: 13, M: 7, A: 5, N: 11) carry wide uncertainty by
construction. The multi-year validation remains the confirming test
for anything that survives this screen.

Files: `summary.json` (full per-size metrics, MC distributions and
compliance), `select_eval_fast.py`, `run_captures.py`, `data_outputs/`
(new K/L/M/N captures); strategies in `strategies/bot_k_trend_rider.py`,
`bot_l_squeeze_breakout.py`, `bot_m_last_hour.py`, `bot_n_prior_day.py`.
