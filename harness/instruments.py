"""MNQ futures contract definition for Nautilus (CME specs)."""

from datetime import datetime, timezone
from decimal import Decimal

from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.objects import Price, Quantity

import config


def _ns(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000_000)


def make_mnq_contract(
    symbol: str | None = None,
    activation: datetime | None = None,
    expiration: datetime | None = None,
) -> FuturesContract:
    """MNQ contract with CME specifications.

    Defaults to the front contract from config (MNQZ26). Pass an explicit
    symbol and active window when loading historical data from a period
    when a different contract was in force — Nautilus rejects orders for
    contracts outside their activation/expiration window.
    """
    symbol = symbol or config.CONTRACT_SYMBOL
    return FuturesContract(
        instrument_id=InstrumentId(Symbol(symbol), Venue(config.VENUE_NAME)),
        raw_symbol=Symbol(symbol),
        asset_class=AssetClass.INDEX,
        currency=USD,
        price_precision=2,
        price_increment=Price.from_str(str(config.TICK_SIZE)),
        multiplier=Quantity.from_int(config.MULTIPLIER),
        lot_size=Quantity.from_int(1),
        underlying=config.UNDERLYING,
        activation_ns=_ns(activation or datetime(2026, 9, 1, tzinfo=timezone.utc)),
        expiration_ns=_ns(expiration or datetime(2026, 12, 18, 16, 0, tzinfo=timezone.utc)),
        ts_event=0,
        ts_init=0,
        margin_init=Decimal(config.MARGIN_INIT_PCT),
        margin_maint=Decimal(config.MARGIN_MAINT_PCT),
        exchange="CME",
    )
