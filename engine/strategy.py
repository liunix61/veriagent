"""Decision policy: perception → Decision or reject.

Risk rules mirror VeriAgentVault.sol's on-chain policy engine so an
on-chain-compliant decision is also off-chain-compliant — and vice versa.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .models import Decision
from .perception import PerceptionSnapshot


@dataclass
class RiskPolicy:
    max_slippage_bps: int = 50
    max_position_usd: float = 10_000.0
    min_liquidity_usd: float = 100_000.0
    max_spread_bps: float = 30.0
    decision_ttl_sec: int = 60


class DecisionReject(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class DecisionPolicy:
    """Produces buy/sell signals with hard risk gates."""

    def __init__(self, policy: RiskPolicy | None = None):
        self.policy = policy or RiskPolicy()
        self._nonce = 0

    def _signal(self, snap: PerceptionSnapshot) -> str:
        # placeholder signal for the demo loop: mean-reversion-ish on spread
        return "buy" if snap.spread_bps < self.policy.max_spread_bps / 2 else "sell"

    def decide(self, agent_id: str, snap: PerceptionSnapshot,
               amount: int, action: str | None = None) -> Decision:
        p = self.policy

        if snap.liquidity_usd < p.min_liquidity_usd:
            raise DecisionReject("INSUFFICIENT_LIQUIDITY")
        if snap.spread_bps > p.max_spread_bps:
            raise DecisionReject("SPREAD_TOO_WIDE")

        action = action or self._signal(snap)
        risk_score = int(min(snap.spread_bps / p.max_spread_bps, 1.0) * 10_000)

        self._nonce += 1
        return Decision(
            agent_id=agent_id,
            chain=snap.chain,
            action=action,
            venue=snap.venue,
            asset=snap.asset,
            amount=amount,
            max_slippage_bps=p.max_slippage_bps,
            risk_score=risk_score,
            context_hash=snap.context_hash,
            nonce=self._nonce,
            expires_at=int(time.time()) + p.decision_ttl_sec,
        )
