# Esura Trading Bot — $1,000/Day Profitability Research Challenge
## Final report (Section 13 deliverable)

Run: 2026-11-19 · Engine: NautilusTrader 1.231.0 · 42 backtest runs, all
reproduced exactly on re-run (nets match to the cent).

**Data:** MNQ 1-minute, TopstepX feed via GitHub (axb0306/cme-futures-ohlc),
2026-01-20 → 2026-04-15, 84,077 bars, **61 RTH sessions**. Chronological
reporting split: train Jan 20–Feb 27 · validation Feb 28–Mar 24 ·
out-of-sample Mar 25–Apr 15. **No parameter was optimized on any period** —
every rule was fixed in advance, so the splits are purely evaluative.
Costs: $1.00/contract/side commission (**assumed placeholder** — the real
broker schedule is still an open decision) + exactly 1 tick slippage per
fill. Sizing: dynamic % of current equity, contracts =
floor(budget / (stop pts × $2 + $2 round-trip)), margin ceiling 90% of
equity, budget never exceeded (a trade that cannot afford one contract is
skipped). Controls on every run: max 6 entries/day, 2% daily kill switch
on equity (realized + unrealized), one position at a time.

---

## The 10 answers

1. **Best individual strategy:** Bot B (Trend Pullback) is the only one
   whose edge is *distributed* — see the concentration evidence below.
   Bot C posts higher headline numbers but fails the concentration screen.
2. **Best combined portfolio:** $50,000 account, 0.50% risk, original
   exits, **stop-at-$1,000 mode**: net **+$8,023.26**, PF **1.304**,
   165 trades, avg **$131.53/day**.
3. **Best starting capital:** **$50,000.** The $25,000 account cannot fund
   Bot A at all at ≤0.50% risk (its full-range stop exceeds a $125 budget)
   and roughly halves every dollar result.
4. **Best risk configuration:** **0.50% per trade.** 0.25% starves Bot A
   completely (0 trades). 1.00% *breaks* the combined portfolio
   out-of-sample (OOS PF 0.836, OOS net −$988) — more risk made it worse.
5. **Best exits:** the **original rules** for Bots A and B (every B
   variation was worse; A's 3R gain rests on 10 trades). One labeled
   exception worth a next-round test: Bot C with a **2R target cap**
   gave up little net (+$5,334 vs +$6,384) for a far better profile
   (max DD 2.91% vs 7.95%, Sharpe 3.63 vs 1.80, losing streak 5 vs 15).
6. **Average net daily profit (best configuration): $131.53.**
7. **Percentage of days reaching $1,000 (best configuration): 6.6%.**
   The best any run managed was 18.0% (Bot C at 1% risk, with a 15.9%
   drawdown attached).
8. **Maximum drawdown (best configuration): $2,707 (4.81%)**, daily-close
   basis. The worst in the matrix: Bot C at 1% risk, $9,334 (15.9%).
9. **Out-of-sample profit factor (best configuration): 1.146** — below
   the challenge's own 1.20 acceptance bar.
10. **Does the system support $1,000/day? NO.** The best configuration
    averages ~$132/day — about one-eighth of the target — and the levers
    that would be needed to close the gap are exactly the ones the data
    punishes: raising risk to 1% degraded the portfolio out-of-sample,
    and Bot B's expectancy (~$33/trade at 0.5% risk, ~2 trades/day)
    would need ~30 trades/day against a 6-entry cap, or ~7.5% risk per
    trade, to reach $1,000/day. Neither is survivable. The honest
    conclusion: on this data, with these strategies and these accounts,
    $1,000/day is not achievable without unacceptable risk.

## Concentration evidence (why the headline numbers mislead)

Share of each base run's net profit contributed by its single largest /
top-3 trades ($50k, 0.5%, re-run verified):

| Run | Net | Top 1 | Top 3 | Net without top 3 |
|---|---|---|---|---|
| Bot A (10 trades) | +$218.50 | 194% | 528% | −$935.50 |
| Bot B (125 trades) | +$4,135.00 | 9% | 26% | **+$3,078.94** |
| Bot C (71 trades) | +$6,384.04 | **90%** | 150% | −$3,174.28 |
| Combined (174) | +$7,717.10 | 70% | 117% | −$1,345.48 |

Bot C's result is one $5,755 trade plus noise, and the combined portfolio
inherits that dependence. Bot B is the only strategy that stays solidly
profitable with its best trades removed.

## Regime evidence

The combined portfolio is a **sideways-market machine**: sideways regime
+$13,580 (PF 3.37) vs high-volatility −$4,656 (PF 0.54), low-volatility
−$2,017 (PF 0.73), trending +$450 (PF 1.10). Bot C alone: sideways
+$11,522 (PF 6.00), trending −$2,724 (PF 0.15). Almost all profit in this
window came from range-bound conditions; the system has no demonstrated
edge in trending or volatile markets. Bot C's validation-period PF was
below 1.0 in **every** configuration (0.83–0.89) — its train-period
(February) spike carried the totals.

## Other findings

- **Bot A is structurally starved.** Its stop is the full opening-range
  width; at 0.25% risk it cannot afford a single trade on either account,
  and at $50k/0.5% it traded only 10 of 61 sessions. Its 1%-risk numbers
  (51 trades, PF 1.423, OOS PF 1.683) hint at an edge the risk budget
  usually forbids. (Note: yesterday's fixed-$100 runs silently exceeded
  their budget on wide ranges via a minimum-1-contract clamp; the
  challenge sizing enforces the budget strictly, which is why trade
  counts differ.)
- **Stop-at-$1,000 mode helped slightly** (combined +$8,023 vs +$7,717;
  Bot C +$7,140 vs +$6,384) by locking out late-day entries on the few
  days the target was reached. It never triggered for Bots A or B.
- **Adverse costs** (+$0.50/contract/side, modeling worse execution):
  Bot B −38% (+$4,135 → +$2,548), Bot C −6%, Bot A −5%. Bot B's edge is
  real but thin enough that the actual broker fee schedule matters —
  it remains the single most important missing input.
- **Diversification is not supported.** The combined portfolio's OOS PF
  (1.12–1.15) is *below* Bot B's alone (1.32–1.37): Bots A and C dilute
  B out-of-sample, and C dominates the portfolio's risk.

## Data sufficiency — stated plainly

61 sessions is not enough to establish statistical confidence in any of
this. One volatility regime dominates the window, Bot A's sample is
10–51 trades, and the out-of-sample period is 16 sessions. These results
are *indicative research findings*, not validated performance. A
multi-year archive (the standing Databento decision) is the binding
constraint on every conclusion above; walk-forward testing is not
meaningful until it exists.

## Configuration reference

Full per-run metrics (Sharpe, Sortino, monthly, regime, period splits):
`challenge_2026-11-19.json` (42 runs). Strategies: original master-plan
rules preserved; Bot C uses the labeled v2 relative-range guard
(disclosed 2026-11-19). No live trading was performed or is authorized
by this research.
