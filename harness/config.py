"""
Central configuration for the MNQ master-plan research project.

EVERY number here that is not a contract specification is an ASSUMPTION
or a PENDING DECISION, labeled as such. Replace assumptions with Esura's
actual broker / prop-firm schedule before any result is taken seriously.
Nothing in this file is a strategy result.
"""

from nautilus_trader.model.currencies import USD
from nautilus_trader.model.objects import Money

# --- Venue / instrument identity -------------------------------------------
VENUE_NAME = "GLBX"                 # CME Globex (Nautilus/Databento convention)
CONTRACT_SYMBOL = "MNQZ26"          # Dec 2026 MNQ contract (front contract at build time)
UNDERLYING = "NQ"

# --- MNQ contract specifications (CME published specs — facts, not assumptions)
TICK_SIZE = 0.25                    # index points
MULTIPLIER = 2                      # USD per index point per contract
TICK_VALUE_USD = TICK_SIZE * MULTIPLIER   # $0.50 per tick per contract

# --- Cost model --------------------------------------------------------------
# ASSUMPTION (placeholder): $1.00 per contract per side, all-in
# (commission + exchange + NFA + clearing). Typical retail micro-futures
# all-in costs run roughly $0.60–$1.50 per side depending on broker.
# DECISION NEEDED: Esura's actual broker / prop-firm fee schedule.
COMMISSION_PER_SIDE = Money(1.00, USD)

# ASSUMPTION (conservative): every fill slips exactly one tick ($0.50).
# Implemented with Nautilus's FillModel(prob_slippage=1.0).
SLIPPAGE_TICKS = 1

# --- Account -----------------------------------------------------------------
# Planning figure from the master plan §5 ($25k–$50k self-funded range).
STARTING_BALANCE = Money(50_000, USD)
MARGIN_INIT_PCT = "0.05"            # ASSUMPTION: ~5% of notional initial margin
MARGIN_MAINT_PCT = "0.04"           # ASSUMPTION: ~4% maintenance

# --- Session (America/New_York) ----------------------------------------------
SESSION_OPEN = "09:30"              # RTH open
SESSION_CLOSE = "16:00"             # RTH close
FLATTEN_TIME = "15:59"              # flatten everything by this time
TIMEZONE = "America/New_York"
