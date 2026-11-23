# Trading Historical Data — MNQ Strategy Research Handoff

This repo holds the complete MNQ day-trading strategy research package
(data, strategies, evaluation harness, and results) so Esura's AI
collaborators can test new strategies on identical footing.

**Start here: [HANDOFF.md](HANDOFF.md)** — project overview, data
provenance and limits, cost model, the settled Tradeify Select 25K
account rules, the strategy catalog, the full results ledger, and the
testing protocol new work must follow.

## Contents

- MASTER_RESEARCH_PROMPT.md — the controlling multi-AI research brief (objectives, protocol, deliverables).
- `data/` — MNQ 1-minute / 1-hour / daily bars (TopstepX-sourced,
  Jan–Apr 2026 core sample; internal research only, no license).
- `strategies/` — all strategy implementations (Bots A–R).
- `harness/` — Tradeify Select 25K eval and two-phase payout state
  machines, Monte Carlo, and the multi-year validation harness.
- `results/` — the study reports: Validation V2, account fit tests,
  fast-pass sweep, payout sprint, and the $1,000/day challenge.

Research only — nothing in this repo authorizes live trading or any
purchase.
