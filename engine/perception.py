"""Market perception layer.

Produces PerceptionSnapshot objects from a MarketDataSource. Mock source for
demo/tests; real sources (RPC price feeds, Robinhood oracle) plug in behind
the same interface in W2 integration.

RWA tokenized-equity layer (bStocks on Robinhood Chain):
  - MarketSession: primary-market session state. SEC Innovation Exemption
    (2026-09-17) requires tokenized venues to halt trading concurrently with
    any halt/suspension in the underlying stock — HALTED is a hard gate.
    CLOSED (after-hours) remains tradable on 24/7 TSV venues but carries
    thin-liquidity risk, surfaced in the risk score.
  - EquitySessionCalendar: maps wall-clock time to MarketSession for US
    equities (regular session 09:30-16:00 America/New_York).
  - MockTokenizedEquitySource: deterministic bStocks data source carrying
    session + dividend metadata through to the decision audit trail.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Protocol


class MarketSession(str, Enum):
    """Primary-market session state for a tokenized equity."""
    OPEN = "OPEN"       # regular trading hours — normal operation
    CLOSED = "CLOSED"   # after-hours/weekend — TSV 24/7 trading allowed,
                        # thin-liquidity risk added to the risk score
    HALTED = "HALTED"   # primary market halted/suspended — trading MUST stop
                        # (SEC TSV condition: concurrent halt)


@dataclass
class TokenizedEquity:
    """Metadata for one bStocks (tokenized equity) instrument."""
    symbol: str                 # underlying ticker, e.g. "AAPL"
    token_address: str          # ERC-20 bStocks token on Robinhood Chain
    venue: str = "bstocks"
    chain: str = "robinhood-chain"
    dividend_per_share: float = 0.0   # last announced DPS (USD)
    onchain_rights: bool = True       # SEC "No Synthetics": voting+dividend
                                      # rights preserved on-chain


@dataclass
class PerceptionSnapshot:
    asset: str
    mid_price: float
    bid: float
    ask: float
    liquidity_usd: float
    venue: str
    chain: str
    ts: float = field(default_factory=time.time)
    # ── RWA tokenized-equity fields (default: plain crypto asset) ──
    session: MarketSession = MarketSession.OPEN
    underlying: str = ""        # underlying ticker when asset is tokenized
    dividend_per_share: float = 0.0

    @property
    def spread_bps(self) -> float:
        if self.mid_price <= 0:
            return float("inf")
        return (self.ask - self.bid) / self.mid_price * 10_000

    @property
    def context_hash(self) -> str:
        """Deterministic hash of the market context behind a decision.

        Includes session state so the on-chain audit trail can prove what
        market conditions the agent saw when it decided.
        """
        raw = (f"{self.chain}|{self.venue}|{self.asset}|{self.mid_price:.8f}|"
               f"{self.bid:.8f}|{self.ask:.8f}|{self.liquidity_usd:.2f}|"
               f"{self.session.value}|{self.underlying}")
        return "0x" + hashlib.sha256(raw.encode()).hexdigest()


class MarketDataSource(Protocol):
    def snapshot(self, chain: str, venue: str, asset: str) -> PerceptionSnapshot: ...


class MockMarketDataSource:
    """Deterministic pseudo-random walk — reproducible demos and tests."""

    def __init__(self, seed: int = 42, base_price: float = 100.0):
        self._seed = seed
        self._base_price = base_price
        self._tick = 0

    def snapshot(self, chain: str, venue: str, asset: str) -> PerceptionSnapshot:
        self._tick += 1
        # simple deterministic walk
        drift = ((self._seed * 31 + self._tick * 17) % 1000) / 10_000 - 0.05
        mid = self._base_price * (1 + drift)
        half_spread = mid * 0.0006  # 6 bps half-spread
        return PerceptionSnapshot(
            asset=asset,
            mid_price=mid,
            bid=mid - half_spread,
            ask=mid + half_spread,
            liquidity_usd=5_000_000 + (self._tick % 7) * 100_000,
            venue=venue,
            chain=chain,
        )


# ── RWA tokenized-equity session calendar ────────────────────────

class EquitySessionCalendar:
    """US-equity regular-session calendar for tokenized venues.

    Regular session: 09:30-16:00 America/New_York, Mon-Fri.
    EST = UTC-5, EDT = UTC-4; this calendar uses the standard-estimation
    approach of testing both offsets (deterministic, no tz database needed:
    a timestamp is in-session if it falls in 14:30-21:00 UTC (EDT window)
    OR 13:30-20:00 UTC (EST window) on a weekday — the union errs toward
    OPEN, which is the safe direction for availability).

    Halt overrides: `halted_until` lets an operator/oracle push an explicit
    HALTED window (e.g. LULD halt, news suspension) that overrides the
    time-based session until it expires.
    """

    def __init__(self, halted_until: float = 0.0,
                 holidays: set[str] | None = None):
        self.halted_until = halted_until
        # US market holidays as "YYYY-MM-DD" strings (settable by operator)
        self.holidays = holidays or set()

    def mark_halt(self, until_ts: float) -> None:
        """Operator/oracle hook: primary market halted until `until_ts`."""
        self.halted_until = until_ts

    def session_at(self, ts: float | None = None) -> MarketSession:
        now = ts if ts is not None else time.time()
        if self.halted_until > now:
            return MarketSession.HALTED
        dt_utc = datetime.fromtimestamp(now, tz=timezone.utc)
        if dt_utc.strftime("%Y-%m-%d") in self.holidays:
            return MarketSession.CLOSED
        if dt_utc.weekday() >= 5:  # Sat/Sun
            return MarketSession.CLOSED
        # in-session if within either the EST or EDT regular-hours window
        minutes = dt_utc.hour * 60 + dt_utc.minute
        in_est_window = 13 * 60 + 30 <= minutes < 20 * 60   # 13:30-20:00 UTC
        in_edt_window = 14 * 60 + 30 <= minutes < 21 * 60   # 14:30-21:00 UTC
        if in_est_window or in_edt_window:
            return MarketSession.OPEN
        return MarketSession.CLOSED


class MockTokenizedEquitySource:
    """Deterministic bStocks data source: price walk + session + dividend.

    Carries the equity metadata (session, underlying ticker, DPS) into the
    PerceptionSnapshot so decisions and their on-chain audit hashes capture
    the tokenized-equity context.
    """

    def __init__(self, equity: TokenizedEquity,
                 calendar: EquitySessionCalendar | None = None,
                 seed: int = 42, base_price: float = 200.0,
                 session_override: MarketSession | None = None,
                 liquidity_usd: float = 8_000_000.0):
        self.equity = equity
        self.calendar = calendar or EquitySessionCalendar()
        self._seed = seed
        self._base_price = base_price
        self._tick = 0
        self._session_override = session_override
        self.liquidity_usd = liquidity_usd

    def snapshot(self, chain: str, venue: str, asset: str) -> PerceptionSnapshot:
        self._tick += 1
        drift = ((self._seed * 31 + self._tick * 17) % 1000) / 10_000 - 0.05
        mid = self._base_price * (1 + drift)
        session = self._session_override or self.calendar.session_at()
        # spread widens when the primary market is closed (thin liquidity)
        spread_mult = 3.0 if session == MarketSession.CLOSED else 1.0
        half_spread = mid * 0.0006 * spread_mult
        # closed-hours liquidity shown as thinner (30% of regular)
        liq = self.liquidity_usd * (0.3 if session == MarketSession.CLOSED else 1.0)
        return PerceptionSnapshot(
            asset=asset,
            mid_price=mid,
            bid=mid - half_spread,
            ask=mid + half_spread,
            liquidity_usd=liq,
            venue=venue or self.equity.venue,
            chain=chain or self.equity.chain,
            session=session,
            underlying=self.equity.symbol,
            dividend_per_share=self.equity.dividend_per_share,
        )
