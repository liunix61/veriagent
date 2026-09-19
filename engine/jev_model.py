"""Jev (TypeSafe AI System One Model) adapter for VeriAgent.

TypeSafe AI released Jev on 2026-09-16: a System One Model that outputs
typed decisions (not text) with calibrated confidence — $42/B tokens,
~2 orders of magnitude faster/cheaper than LLMs, zero hallucinations by
construction (https://typesafe.ai).

The jev-trader community (jarrodwatts/jev-trader, 1.1k stars in 3 days)
runs raw Jev decisions straight into order placement — every Monad block,
buy or sell, no questions asked. That is exactly the trust gap VeriAgent
exists to close: a Jev decision enters the SAME credential pipeline as any
other model decision — four on-chain hashes + JSONL hash chain — so the
decision-maker can be audited after the fact.

Architecture:
    PerceptionSnapshot -> JevModel.decide() -> JevDecision {action, confidence}
        -> DecisionPolicy integration (confidence -> risk_score, model_id=
           "jev-systemone") -> Decision four-hash credential -> recorder.

API status: Jev is in early access (waitlist). The transport layer raises
until an official endpoint is configured from TypeSafe's published docs
(docs.typesafe.ai) — nothing here is guessed. MockJevModel is fully
functional for demos/tests and follows the documented output contract:
typed action + calibrated confidence, no free text.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from .perception import MarketSession, PerceptionSnapshot


@dataclass(frozen=True)
class JevDecision:
    """Type-safe decision output — Jev's documented output contract.

    action: "buy" | "sell" | "hold"
    confidence: calibrated probability in [0, 1] — the model's own estimate
    """
    action: str
    confidence: float

    def __post_init__(self):
        if self.action not in ("buy", "sell", "hold"):
            raise ValueError(f"invalid Jev action: {self.action!r}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence out of range: {self.confidence}")


class JevTransportError(RuntimeError):
    """Raised when the live Jev API transport is not yet configured."""


class JevModel:
    """Live Jev adapter — decision format + VeriAgent mapping are final.

    The HTTP transport activates once early access lands; the endpoint MUST
    come from TypeSafe's official docs (docs.typesafe.ai), never guessed.
    """

    MODEL_ID = "jev-systemone"

    def __init__(self, api_key: str | None = None, endpoint: str | None = None):
        self.api_key = api_key or os.environ.get("TYPESAFE_AI_API_KEY")
        self.endpoint = endpoint or os.environ.get("TYPESAFE_AI_ENDPOINT")

    @property
    def ready(self) -> bool:
        return bool(self.api_key and self.endpoint)

    def decide(self, snap: PerceptionSnapshot) -> JevDecision:
        """Ask Jev for a typed decision on a market snapshot."""
        if not self.ready:
            raise JevTransportError(
                "Jev live transport not configured — awaiting TypeSafe early "
                "access; set TYPESAFE_AI_API_KEY and TYPESAFE_AI_ENDPOINT "
                "from official docs (docs.typesafe.ai). Use MockJevModel for "
                "demos/tests."
            )
        payload = self._build_payload(snap)
        raw = self._call_api(payload)
        return self._parse_decision(raw)

    def _build_payload(self, snap: PerceptionSnapshot) -> dict:
        """Structured question for Jev — market state in, decision out."""
        return {
            "task": "trading_decision",
            "asset": snap.asset,
            "underlying": getattr(snap, "underlying", "") or snap.asset,
            "mid_price": round(snap.mid_price, 8),
            "bid": round(snap.bid, 8),
            "ask": round(snap.ask, 8),
            "spread_bps": round(snap.spread_bps, 4),
            "liquidity_usd": round(snap.liquidity_usd, 2),
            "venue": snap.venue,
            "chain": snap.chain,
            "session": getattr(snap, "session", MarketSession.OPEN).value,
        }

    def _call_api(self, payload: dict) -> dict:
        """Transport hook — wired to the official endpoint when access lands."""
        raise JevTransportError(
            "Jev HTTP transport activates after early access; endpoint must "
            "come from docs.typesafe.ai (nothing is guessed here)."
        )

    def _parse_decision(self, raw: dict) -> JevDecision:
        return JevDecision(action=str(raw["action"]), confidence=float(raw["confidence"]))


class MockJevModel:
    """Deterministic Jev stand-in following the documented output contract:
    typed action + calibrated confidence, no free text.

    Signal: spread-mean-reversion like the demo strategy, with confidence
    derived from how decisive the market state is (tight spread + deep
    liquidity -> high confidence).
    """

    MODEL_ID = "jev-systemone-mock"

    def decide(self, snap: PerceptionSnapshot) -> JevDecision:
        # deterministic pseudo-signal from market state
        tight = snap.spread_bps < 12.0
        deep = snap.liquidity_usd > 1_000_000
        h = hashlib.sha256(
            f"{snap.asset}|{snap.mid_price:.8f}|{snap.session.value}".encode()
        ).hexdigest()
        roll = int(h[:4], 16) / 0xFFFF

        if snap.session == MarketSession.HALTED:
            # Jev would see no valid market; decision layer rejects anyway
            return JevDecision(action="hold", confidence=0.95)
        if tight and deep:
            action = "buy" if roll > 0.4 else "sell"
            confidence = 0.75 + roll * 0.2   # 0.75-0.95
        elif not tight:
            action = "hold"
            confidence = 0.60 + roll * 0.2
        else:
            action = "buy" if roll > 0.5 else "sell"
            confidence = 0.45 + roll * 0.25  # thin book -> low confidence
        # after-hours: confidence discounted (thin liquidity, wider spreads)
        if snap.session == MarketSession.CLOSED:
            confidence = max(confidence - 0.2, 0.05)
        return JevDecision(action=action, confidence=round(confidence, 4))


def jev_decision_to_risk_score(decision: JevDecision) -> int:
    """Map Jev confidence to VeriAgent's 0-10000 risk score.

    Inverted: high confidence -> low risk. The calibration is preserved in
    the decision's reason text so auditors see the model's own uncertainty.
    """
    return int(round((1.0 - decision.confidence) * 10_000))
