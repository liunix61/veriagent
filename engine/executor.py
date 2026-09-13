"""Trade execution layer.

MockExecutor for demo/tests; Web3Executor (venue adapter calls) activates
after Sepolia deploy. The executor never sees a Decision directly — it gets
a Credential so it can carry the proof, mirroring Vault.proceedToTrade.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

from .models import Credential, TradeResult


class Executor(Protocol):
    def execute(self, credential: Credential) -> TradeResult: ...


class MockExecutor:
    """Deterministic simulated fills — no network, no funds."""

    def __init__( self, fail_rate: float = 0.0):
        self.fail_rate = fail_rate
        self.calls: list[str] = []

    def execute(self, credential: Credential) -> TradeResult:
        d = credential.decision
        self.calls.append(credential.credential_id)
        h = hashlib.sha256(credential.decision_hash.encode()).hexdigest()
        roll = int(h[:8], 16) / 0xFFFFFFFF
        if roll < self.fail_rate:
            return TradeResult(tx_hash="0x" + h[:64], status="failed",
                               error="SIMULATED_SLIPPAGE")
        return TradeResult(
            tx_hash="0x" + h[:64],
            status="success",
            actual_price=100.0 * (1 + (roll - 0.5) * 0.001),
            filled_amount=d.amount,
            gas_used=90_000,
        )


class Web3Executor:
    """Real venue adapter — activates post-deploy."""

    def __init__(self, rpc_url: str, vault_address: str, session_key: str):
        if not vault_address:
            raise ValueError("vault address required")
        raise NotImplementedError(
            "Web3Executor activates after Sepolia deploy (W2 step 3)"
        )
