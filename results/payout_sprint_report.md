# Payout Sprint — First Payout Within ~10 Trading Days on the Select 25K? (2026-11-23)

**Question (Esura's requirement, extended):** the 2026-11-22 fast-pass
sweep showed no strategy can pass the Tradeify Select Flex 25K
*evaluation* in 7–14 days. This job asks the harder, full question:
can any strategy configuration produce an actual **first payout**
within **~10 trading days** (two calendar weeks) on the complete
eval → funded path — and if not, what are the closest legal
approaches, with honest probabilities?

**Answer: NO — and it is not close.** Across 66 configurations tested
(11 candidates × 6 sizes), the probability of a first payout within
10 trading days is:

- **Best account-legal configuration: 0.03%** — the legacy B+C3 pair
  at $150/trade (3 paths in 10,000). At the recommended $50 size it is
  **0.00%**.
- **Best configuration anywhere, legal or not: 0.56%** — B+C3 at
  $250/trade, which is illegal on this account (18 micros vs the
  10-micro cap) and carries a 55.5% eval failure rate.
- **Nothing — legal or illegal — reaches even a 25% chance of a
  two-week payout. Nothing reaches 1%.**

Every brand-new family built for this sprint (short opening-range
breakouts, VWAP trend rider, first-hour momentum, gap
continuation/fade, high-frequency Bot B variant, Bot K + activity
partner) has P(payout ≤ 10 days) = **0.00% at every size**, and most
have P(payout ≤ 20 days) = 0.00% as well. Five of the six new
families lose money outright on the sample.

Data: the same validated 61-session TopstepX MNQ 1-min sample
(2026-01-20 → 2026-04-15), standard cost model ($1.00/contract/side
placeholder + 1-tick slippage). New families ran fresh Nautilus
captures (max 10 micros enforced in the engine); B+C3 controls reuse
their existing Miami/Validation-V2 captures. MC: circular block
bootstrap, block 5, 10,000 sims, 250-session horizon, seed 20261122 —
the fast-pass method, extended to two phases.

---

## The two-phase model (new for this job)

The fast-pass state machine was extended from eval-only to the full
path, with the funded rules as specified:

- **Eval:** start $25,000; pass at the first EOD where cumulative
  profit ≥ $1,500 **and** the best single day ≤ 40% of cumulative
  profit **and** day ≥ 3; fail on a real-time touch of the
  EOD-trailing $1,000 floor; max 10 micros; flat by close.
- **Funded (only after a pass):** the account **restarts at $25,000
  fresh — eval profit does not carry over.** Same trailing-floor
  failure rule. **First payout** at the first EOD with **≥ 5 winning
  days** (a winning day = ≥ $100 net that day) **and** cumulative
  funded profit ≥ **$500** (the Flex request is 50% of total profit
  with a $250 minimum request, so $500 of profit is the smallest
  requestable base). The post-payout floor lock is ignored; the
  clock stops at the first payout.
- **Compliance gates** (a candidate failing any is NOT USABLE):
  ≤ 10 micros peak; zero overnight holds; funded microscalping rule
  (>50% of trades **and** >50% of gross profit from holds > 10 s);
  idle rule (no 5+ consecutive sessions without a trade, checked over
  the full sample and within the historical phase windows).

**Control gate — passed exactly.** Before any new output was
trusted, the extended state machine had to reproduce the known
B+C3 @ $50 Select figures from the existing capture: net **$1,037.80**
✓ (exact), minimum floor distance **$604.26** ✓ (exact), $75 net
$1,189.74 ✓, $100 net $2,295.80 ✓, single-phase MC P(pass) 0.9726 vs
fast-pass 0.968 and median 100 vs 99 days (RNG-stream position only).
Historical two-phase paths use the actual per-minute prints in both
phases; the MC uses the capture's kappa (intraday-trough/EOD ratio)
exactly as in fast_pass.

---

## Why the arithmetic forbids it — the structural conclusion

A payout by day 10 requires **all five** of these to happen in
sequence:

1. **Eval pass by day 5 at the latest** (any later and the funded
   phase cannot fit five winning days into the window). That means
   +$1,500 in ≤ 5 days — ≥ $300/day average — while no single day
   exceeds 40% of the total (best day ≤ $600 at exactly $1,500), so
   the profit must arrive *smoothly*, not in one spike.
2. **No touch of the $1,000 trailing floor during those days** —
   at the sizes that can average $300/day, the historical
   peak-to-trough drawdown is $1,868–$3,379, i.e. 1.9–3.4× the floor.
3. **A fresh $25,000 funded account** — the eval's $1,500 is gone;
   the payout clock restarts from zero.
4. **Five winning days (≥ $100 each) inside the remaining ≤ 5 funded
   days** — i.e. *every* funded day must be a $100+ winner, and
5. **≥ $500 cumulative funded profit with no floor touch** in the
   funded phase either.

The theoretical floor is day 8 (3-day eval minimum + 5 winning
funded days). Each gate is individually improbable against MNQ's
daily P&L distribution at any size the $1,000 floor tolerates; the
joint probability is what the table shows: at best ~1-in-300 for a
legal configuration, ~1-in-180 for an illegal one. This is a
property of the two-gate account arithmetic — $1,500 target /
$1,000 floor / restart-at-zero / five-winning-days — not of strategy
choice. No entry logic changes it, because the binding constraints
are the *funded restart* and the *five-winning-day count*, which no
strategy can compress below five separate profitable days.

For scale: the fastest *median* time-to-payout anywhere in the study
is **19 days** (B+C3 @ $250, illegal, 55% eval-fail) and the fastest
for a legal configuration is **31 days** (B+C3 @ $150, with a 43%
eval-fail rate). The recommended B+C3 @ $50 configuration's median
time-to-payout among paths that ever get one is **152 days**, with
P(payout ≤ 20 days) = 0.00%.

---

## Master table — Monte Carlo, two-phase (10,000 paths, 250-session horizon)

P(pass ≤5 / ≤10) = eval pass within 5 / 10 trading days.
P(pay ≤10 / ≤20) = first payout within 10 / 20 trading days **total**
(both phases). MedPay = median total days to payout among paths that
receive one within the horizon. FailE / FailF = P(fail) in the eval
phase / in the funded phase after passing. "Usable" = passes all
four compliance gates (it does **not** mean drawdown-safe — see the
trough column).

### Control — Bot B+C3 pair (legacy)

| Size | Trades | Net | Trough | Peak µ | P(pass ≤5) | P(pass ≤10) | P(pay ≤10) | P(pay ≤20) | MedPay | FailE | FailF | Usable |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| $50 | 171 | $1,038 | $396 | 3 | 0.0% | 0.0% | **0.00%** | 0.00% | 152 | 1.8% | 0.9% | ✓ |
| $75 | 194 | $1,190 | $814 | 5 | 0.0% | 0.0% | **0.00%** | 0.00% | 96 | 25.1% | 8.5% | ✓ |
| $100 | 197 | $2,296 | $1,168 | 7 | 0.0% | 1.6% | **0.00%** | 1.02% | 52 | 24.7% | 8.8% | ✓ |
| $150 | 197 | $3,389 | $1,868 | 10 | 1.3% | 11.5% | **0.03%** | 5.56% | 31 | 43.0% | 17.2% | ✓ |
| $200 | 197 | $4,876 | $2,674 | **14 ✗** | 7.0% | 20.8% | **0.15%** | 11.48% | 23 | 50.7% | 19.4% | ✗ cap |
| $250 | 196 | $6,582 | $3,379 | **18 ✗** | 15.5% | 27.6% | **0.56%** | 12.54% | 19 | 55.5% | 23.0% | ✗ cap |

Historical path: $50 alive (never passed in 61 sessions); $75 alive;
$100 FAIL 2026-02-16; $150 FAIL 2026-02-09; $200 FAIL 2026-02-06;
$250 FAIL 2026-01-29. No B+C3 size reached the funded phase on the
actual sample.

### NEW — short opening-range breakouts (opposite-edge stop)

| Config | Size | Trades | Net | PF | Trough | P(pass ≤10) | P(pay ≤10) | P(pay ≤20) | FailE | Usable |
|---|---|---|---|---|---|---|---|---|---|---|
| ORB-5 1R | $50–$100 | 0–3 | −$170…$49 | — | $0–$219 | 0.0% | **0.00%** | 0.00% | 0–14% | ✗ idle |
| ORB-5 1R | $150 | 21 | −$1,067 | 0.41 | $1,144 | 0.0% | **0.00%** | 0.00% | 100.0% | ✗ |
| ORB-5 1R | $250 | 53 | $95 | 1.02 | $1,157 | 0.0% | **0.00%** | 0.12% | 75.7% | ✓* |
| ORB-5 1.5R | $150 | 21 | −$858 | 0.57 | $1,028 | 0.0% | **0.00%** | 0.00% | 99.8% | ✗ |
| ORB-5 1.5R | $250 | 53 | $531 | — | $2,135 | 0.0% | **0.00%** | 0.82% | 68.7% | ✓* |
| ORB-15 1R | $50–$100 | 0 | $0 | — | $0 | 0.0% | **0.00%** | 0.00% | 0.0% | ✗ idle |
| ORB-15 1R | $250 | 29 | $553 | 1.24 | $969 | 0.0% | **0.00%** | 0.00% | 50.6% | ✗ idle |
| ORB-15 1.5R | $250 | 29 | $1,112 | — | $1,106 | 0.0% | **0.00%** | 0.00% | 39.2% | ✗ idle |

\* compliance gates pass at $250, but the strategy is expectancy-flat
(PF ≈ 1.0) with a >$1,100 trough — "usable" on rules only.

The 5- and 15-minute opening ranges are *narrower* than Bot A's
30-minute range, but the stop is still the full range width, so at
$50–$100 the same affordability wall appears (0–3 trades — one
contract's risk exceeds the budget on most days). Where they do
trade, they lose: the 1R/1.5R targets do not rescue a break that
keeps running into the opposite-edge stop. ORB-15 1.5R @ $250 is the
only new candidate that passed the eval on the historical path
(2026-03-06, best-day share 21.3%) — and then **breached the funded
floor on funded day 32 with only 3 winning days banked and −$888 of
funded profit**: a complete, concrete demonstration of the second
gate killing a fast eval pass. It also fails the idle rule
(10-session stretch), so it is not usable regardless.

### NEW — Bot P: VWAP trend-day rider (multiple entries, trailing stop)

| Size | Trades | Net | PF | Trough | Peak µ | P(pass ≤10) | P(pay ≤10) | P(pay ≤20) | FailE | Usable |
|---|---|---|---|---|---|---|---|---|---|---|
| $50 | 111 | −$415 | ~0.90 | $1,238 | 3 | 0.0% | **0.00%** | 0.00% | 92.8% | ✓* |
| $100 | 129 | −$601 | 0.91 | $2,298 | 7 | 0.0% | **0.00%** | 0.00% | 89.0% | ✓* |
| $150 | 129 | −$795 | 0.93 | $3,656 | 10 | 0.5% | **0.00%** | 0.01% | 88.5% | ✓* |
| $250 | 126 | −$769 | — | $5,853 | 10 | 1.9% | **0.00%** | 0.05% | 89.9% | ✓* |

\* fully compliant (trades most days, 100%/100% microscalping,
no overnight) — and negative expectancy at every size. Riding every
VWAP pullback in the trend direction pays the spread/slippage toll
~2× per round trip with no compensating edge on this data: PF
0.90–0.93, historical FAIL at every size. **Dead.**

### NEW — Bot Q: first-hour momentum continuation (trailing stop)

| Size | Trades | Net | PF | Trough | Peak µ | P(pass ≤10) | P(pay ≤10) | P(pay ≤20) | FailE | Usable |
|---|---|---|---|---|---|---|---|---|---|---|
| $50 | 106 | −$99 | 0.97 | $882 | 4 | 0.0% | **0.00%** | 0.00% | 76.8% | ✓* |
| $100 | 108 | −$2,157 | 0.70 | $2,803 | 8 | 0.2% | **0.00%** | 0.00% | 91.2% | ✓* |
| $150 | 108 | −$3,723 | 0.69 | $4,965 | 10 | 0.7% | **0.00%** | 0.02% | 91.9% | ✓* |
| $250 | 107 | −$6,352 | 0.70 | $8,637 | 10 | 0.2% | **0.00%** | 0.00% | 96.4% | ✓* |

\* compliant and active (~1.8 trades/day), but the first-hour break
is a *losing* signal on this sample at any meaningful size — PF
collapses to 0.70 as soon as position size makes the losses real.
**Dead — the worst expectancy of any active new family.**

### NEW — Bot R: overnight-gap continuation / fade (first 90 minutes)

| Config | Size | Trades | Net | PF | Trough | P(pay ≤10) | P(pay ≤20) | FailE | Usable |
|---|---|---|---|---|---|---|---|---|---|
| Continuation | $50–$75 | 0 | $0 | — | $0 | **0.00%** | 0.00% | 0.0% | ✗ idle |
| Continuation | $150 | 10 | −$599 | 0.30 | $764 | **0.00%** | 0.00% | 99.2% | ✗ idle |
| Continuation | $250 | 29 | −$1,281 | 0.61 | $1,761 | **0.00%** | 0.00% | 99.5% | ✗ idle |
| Fade | $50–$100 | 0 | $0 | — | $0 | **0.00%** | 0.00% | 0.0% | ✗ idle |
| Fade | $150 | 13 | −$827 | 0.37 | $827 | **0.00%** | 0.00% | 99.3% | ✗ idle |
| Fade | $250 | 26 | $153 | 1.06 | $751 | **0.00%** | 0.00% | 66.6% | ✗ idle (5) |

Both directions of the gap trade fail. Qualifying gaps (≥ 10 pts)
with an affordable first-5-minute-range stop are rare (0 trades at
$50–$100 — the affordability wall again), and where they trade,
both continuation and fade lose (PF 0.30–0.70 at mid sizes). **Dead.**

### NEW — Bot B-HF: Bot B pullback logic, 1R target, tighter cadence

| Size | Trades | Net | PF | Trough | Peak µ | P(pay ≤10) | P(pay ≤20) | FailE | Usable |
|---|---|---|---|---|---|---|---|---|---|
| $50 | 138 | −$519 | 0.81 | $874 | 3 | **0.00%** | 0.00% | 97.8% | ✓* |
| $100 | 136 | −$1,483 | 0.77 | $2,244 | 7 | **0.00%** | 0.00% | 99.9% | ✓* |
| $150 | 136 | −$2,255 | 0.77 | $3,320 | 10 | **0.00%** | 0.00% | 99.1% | ✓* |
| $250 | 132 | −$3,117 | 0.80 | 4,783 | 10 | **0.00%** | 0.02% | 95.9% | ✓* |

\* compliant (it does produce frequent trades, as designed) — but
the redesign destroys the edge it was built from. Bot B's edge lives
in its 1.5R target and its 3–25 pt stop band; cutting the target to
1R, widening the cadence to 6 entries/day and shortening the time
stop to 45 minutes turns PF 1.28 (as a pair component) into PF
0.77–0.81 standalone at every size, with ~98–100% eval failure in
MC. Producing frequent $100+ *winning days* was the design goal; it
instead produces frequent *trading* days and a steadily declining
balance. **Dead — and a useful negative result: B's parameters are
not a dial that can be turned toward frequency.**

### NEW — Bot KX: Bot K trend rider + ORB-15 1R activity partner

| Size | Trades (K + ORB) | Net | PF | Trough | Peak µ | P(pass ≤10) | P(pay ≤10) | P(pay ≤20) | FailE | FailF | Usable |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $50 | 0 | $0 | — | $0 | 0 | 0.0% | **0.00%** | 0.00% | 0.0% | — | ✗ idle |
| $75 | 3 + 0 | −$449 | 0.05 | $846 | 1 | 0.0% | **0.00%** | 0.00% | 85.8% | — | ✗ idle |
| $100 | 13 + 0 | $1,688 | 3.49 | $846 | 1 | 1.9% | **0.00%** | 0.02% | 27.6% | 22.2% | ✗ idle (30) |
| $150 | 44 + 2 | $884 | 1.24 | $1,691 | 2 | 2.7% | **0.00%** | 0.00% | 62.3% | 23.7% | ✗ idle (7) |
| $200 | 64 + 15 | $2,373 | 1.30 | $2,948 | 3 | 3.0% | **0.00%** | 0.23% | 66.6% | 15.9% | ✓† |
| $250 | 68 + 24 | $1,331 | 1.13 | $3,838 | 4 | 3.3% | **0.00%** | 0.42% | 75.1% | 13.0% | ✓† |

† the four compliance gates pass at $200/$250 only because the
partner's extra trades break up the idle stretches — at troughs of
$2,948/$3,838 (2.9–3.8× the account limit) and 67–75% eval-failure
rates. Compliance-legal, economically non-viable.

The combination was built to fix Bot K's one defect (its 30-session
idle stretch). It does not fix it at any size that matters: the
ORB-15 partner's stop is the full 15-minute range, so at $50–$100
the partner takes **zero** trades (the affordability wall), at $150
it adds 2 trades and the idle stretch only falls to 7, and by the
sizes where it trades often enough to matter ($200+) the combined
trough is ~3× the limit. K's edge survives in the blend (PF 3.49 at
$100 is K alone, untouched) but the idle defect is a *sizing*
problem, not a *strategy-mix* problem. **Verdict: NOT USABLE at any
viable size; the K idle problem remains unsolved.**

---

## The closest legal approaches, ranked honestly

By P(first payout ≤ 10 trading days), compliance-usable
configurations only:

| # | Configuration | P(pay ≤10) | P(pay ≤20) | Median days to payout | P(eval fail) | P(funded fail) | Historical |
|---|---|---|---|---|---|---|---|
| 1 | **B+C3 @ $150** | **0.03%** | 5.56% | 31 | 43.0% | 17.2% | FAIL 2026-02-09 |
| 2 | Everything else usable | 0.00% | ≤ 1.02% (B+C3 @ $100) | 52–152 | — | — | — |

That is the whole list. The single "closest" legal configuration
still (a) pays out within two weeks in 3 of 10,000 simulated paths,
(b) fails the evaluation 43% of the time, and (c) failed on the
actual historical sample. The illegal configurations are not
meaningfully better: B+C3 @ $250 reaches 0.56% for ≤10 days and
12.5% for ≤20 days at the price of an 18-micro position and a 55%
eval-failure rate.

**Does anything reach even a 25% chance of a two-week payout? No.**
The maximum over all 66 configurations is 0.56% — short of 25% by a
factor of ~45. Even relaxing the target to a two-week *eval pass*
(ignoring the funded phase entirely), the maximum is 27.6% (B+C3 @
$250, illegal) and the best legal figure is 11.5% (B+C3 @ $150) —
and an eval pass is not a payout: the funded restart plus the
five-winning-day rule is exactly where those paths go to die
(17–23% of B+C3's eval passes at $150–$250 then fail in the funded
phase, and most of the rest simply cannot stack five $100+ days
fast enough).

## Bottom line

1. **A first payout within ~10 trading days does not exist** in
   anything tested — new or old, legal or not. The ceiling is 0.56%
   (illegal size, 55% blow-up rate); the legal ceiling is 0.03%.
2. **The constraint is structural, not strategic.** The funded
   account restarts at zero and demands five separate $100+ winning
   days plus $500 of profit inside the same $1,000 trailing floor.
   Even a hypothetical strategy that passed the eval on day 3 every
   time would still need five winning days — the payout cannot
   occur before day 8 under *any* strategy, and realistic MNQ daily
   P&L makes the joint event a ~1-in-300 long shot at best.
3. **All six new families are rejected on evidence**: VWAP rider,
   first-hour momentum, both gap variants and B-HF lose money at
   every size; the short-ORB family hits the same affordability wall
   as Bot A and loses where it trades; KX does not fix K's idle
   defect at any viable size.
4. **The recommendation is unchanged**: B+C3 at $50/trade on the
   Select 25K — the only fully compliant, positive-expectancy
   configuration — with a median time-to-*payout* (not just pass) of
   ~152 trading days among successful paths. If a sooner payout is
   the priority, the lever is the account (a plan whose funded phase
   does not restart the clock or demand five winning days), not the
   strategy. No strategy lever exists.

## Caveats (standing)
Single 61-session sample; C3's parameters were partly selected on
this same sample; fees are the $1.00/side placeholder, not Tradeify's
real schedule; MC resamples only the observed sample and cannot
invent regimes it never contained; candidates with < 30 trades
(ORB-15: 29 at its largest size, gap variants, KX's partner at most
sizes) carry wide uncertainty by construction — though for this
question the uncertainty is immaterial, since even their point
estimates sit at 0.00%. The multi-year validation remains the
confirming test for anything that survives this project's screens;
nothing new survived this one.

Files: `summary.json` (full per-size two-phase metrics, MC
distributions and compliance), `payout_eval.py` (two-phase state
machine + control gate), `run_captures.py`, `data_outputs/` (60 new
captures); strategies in `strategies/bot_p_vwap_rider.py`,
`bot_q_first_hour.py`, `bot_r_gap.py` (ORB variants reuse
`strategies/orb.py` with the specified 5/15-min ranges and 1R/1.5R
targets; B-HF reuses `strategies/pullback.py` with the specified
variant parameters; KX pairs `bot_k_trend_rider.py` with the ORB-15
1R partner).
