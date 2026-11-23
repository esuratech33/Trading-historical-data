# Dataset notes — TopstepX MNQ data via GitHub

**Source:** GitHub repo `axb0306/cme-futures-ohlc` (downloaded 2026-11-19).
The repo's data was produced from the **TopstepX / ProjectX Gateway API**
(a real CME feed served by the Topstep prop-firm platform) and is
redistributed there without a license file. Internal research use only.
**Provenance status: identified but NOT independently verified** against
CME or a second vendor (external cross-checks via Yahoo/Stooq were
unreachable from this machine on 2026-11-19).

**Freshness warning:** the repo claims nightly updates, but its last
push was 2026-04-15. This data is **not current** and cannot feed live
paper trading.

## Files acquired

| File | Coverage | Size |
|---|---|---|
| `MNQ_1min_20260120_20260415.csv` | 2026-01-20 13:27 UTC → 2026-04-15 23:29 UTC | 84,077 bars |
| `MNQ_daily_20250324_20260414.csv` | 2025-03-24 → 2026-04-14 | 268 rows |
| `MNQ_1h_20250321_20260415.csv` | 2025-03-21 → 2026-04-15 | — |
| `MNQ_tick_20260309_20260415.csv` | 2026-03-09 → 2026-04-15 | 30 MB |

Timestamps are UTC. The series is the platform's continuous front-month
stream (not a single contract) — treat roll behavior with care (below).

## Validation performed 2026-11-19 (1-minute file)

- 0 duplicate timestamps; strictly monotonic.
- 0 OHLC violations (low ≤ open/close ≤ high on every bar).
- All closes exactly on the 0.25 tick grid; no zero/negative volume.
- 74 trading days; median 1,380 bars/day (a full 23-hour Globex day).
- Completeness: only **3 missing minutes** in the whole file
  (2026-02-05, ~01:51–01:53 ET overnight). Every other gap is the
  daily 17:00–18:00 ET halt or the Presidents Day early close.
- Internal consistency: the repo's daily close equals the 1-minute
  file's 16:59 ET close **exactly (0.00 pts) on all 59 overlapping
  days** — the daily and 1-minute files agree perfectly.
- Overnight continuity: median |session-to-session jump| 0.5 points.

## Flags (read before using)

1. **Two large weekend jumps are externally unverified:**
   Sun 2026-03-15 reopen +158.25 pts and Sun 2026-03-22 reopen
   −303.00 pts vs the prior Friday close. They may be genuine weekend
   moves, continuous-contract splice effects around the March
   expiration (2026-03-20), or both. Bot A is intraday (flat by
   15:59 ET), so these gaps cannot enter its trades directly; they
   only touch Monday's opening range, which is formed from Monday's
   own traded bars. Resolve before any strategy that holds overnight
   or uses multi-day features spanning those dates.
2. **History is short:** ~3 months of 1-minute data (61 usable RTH
   sessions). Enough for pipeline validation and a first-pass,
   low-statistical-power Bot A evaluation with an in/out split.
   NOT enough for the master plan's multi-regime / walk-forward
   standard — that still requires a deep archive (Databento).
3. **First day is partial** (starts mid-session, 2026-01-20 13:27 UTC)
   and the last day ends 2026-04-15 23:29 UTC.
4. Contract identity: the backtest harness currently loads bars
   against a named contract (MNQZ26). Real-data runs must map these
   continuous bars to the contract actually in force on each date, or
   use a continuous instrument definition, so roll dates are handled
   explicitly rather than silently.
