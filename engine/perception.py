"""Market perception layer.

Produces PerceptionSnapshot objects from a MarketDataSource. Mock source for
demo/tests; real sources (RPC price feeds, Robinhood oracle) plug in behind
the same interface in W2 integration.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Protocol


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

    @property
    def spread_bps(self) -> float:
        if self.mid_price <= 0:
            return float("inf")
        return (self.ask - self.bid) / self.mid_price * 10_000

    @property
    def context_hash(self) -> str:
        """Deterministic hash of the market context behind a decision."""
        raw = f"{self.chain}|{self.venue}|{self.asset}|{self.mid_price:.8f}|{self.bid:.8f}|{self.ask:.8f}|{self.liquidity_usd:.2f}"
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
