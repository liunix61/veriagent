"""Decision policy: perception → Decision or reject.

Risk rules mirror VeriAgentVault.sol's on-chain policy engine so an
on-chain-compliant decision is also off-chain-compliant — and vice versa.

Tokenized-equity session gate (SEC Innovation Exemption, 2026-09-17):
  - HALTED: hard reject — TSV venues must stop trading concurrently with
    any halt/suspension in the underlying stock.
  - CLOSED: tradable on 24/7 venues, but thin-liquidity risk is added to
    the decision risk score so the audit trail records the elevated risk.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .models import Decision
from .perception import MarketSession, PerceptionSnapshot


@dataclass
class RiskPolicy:
    max_slippage_bps: int = 50
    max_position_usd: float = 10_000.0
    min_liquidity_usd: float = 100_000.0
    max_spread_bps: float = 30.0
    decision_ttl_sec: int = 60
    # ── tokenized-equity session rules ──
    enforce_session: bool = True          # HALTED → reject (SEC condition)
    closed_market_risk_bps: int = 3000    # risk-score add-on when CLOSED
    closed_max_spread_bps: float = 90.0   # widened spread tolerance after hours


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

    def decide(self, agent_id: int, snap: PerceptionSnapshot,
               amount: int, action: str | None = None,
               reason: str | None = None,
               model_id: str = "strategy-v1") -> Decision:
        p = self.policy
        session = getattr(snap, "session", MarketSession.OPEN)

        # ── session gate: primary-market halt is a hard compliance stop ──
        if p.enforce_session and session == MarketSession.HALTED:
            raise DecisionReject("MARKET_HALTED")
        # CLOSED: 24/7 venues still trade, but liquidity is thin —
        # tolerate a wider spread and carry the elevated risk in the score.
        eff_max_spread = p.closed_max_spread_bps if session == MarketSession.CLOSED \
            else p.max_spread_bps

        if snap.liquidity_usd < p.min_liquidity_usd:
            raise DecisionReject("INSUFFICIENT_LIQUIDITY")
        if snap.spread_bps > eff_max_spread:
            raise DecisionReject("SPREAD_TOO_WIDE")

        action = action or self._signal(snap)
        risk_score = int(min(snap.spread_bps / eff_max_spread, 1.0) * 10_000)
        if session == MarketSession.CLOSED:
            risk_score = min(risk_score + p.closed_market_risk_bps, 10_000)

        self._nonce += 1
        return Decision(
            agent_id=agent_id,
            reason=reason or f"{action} {snap.asset} spread={snap.spread_bps:.1f}bps "
                             f"liq={snap.liquidity_usd:.0f} "
                             f"session={session.value}",
            model_id=model_id,
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
