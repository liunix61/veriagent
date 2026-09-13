"""abi.encode parity — the same vector asserted in HashParity.t.sol."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.abi_encode import decision_payload_hash

VECTOR = dict(
    agent_id="0x0000000000000000000000000000000000001001",
    chain="arbitrum-sepolia",
    action="buy",
    venue="uniswap-v3",
    asset="WETH",
    amount=10 ** 16,
    max_slippage_bps=50,
    risk_score=1200,
    context_hash="0x" + "ab" * 32,
    nonce=1,
    expires_at=2_000_000_000,
)

EXPECTED = "0xe3b5c92cc8264fc527cdd99dff2271777fc9588852785422845227234a910f46"


def test_vector_matches_solidity():
    assert decision_payload_hash(**VECTOR) == EXPECTED


def test_vector_deterministic():
    assert decision_payload_hash(**VECTOR) == decision_payload_hash(**VECTOR)


def test_vector_sensitive_to_amount():
    v = dict(VECTOR, amount=10 ** 16 + 1)
    assert decision_payload_hash(**v) != EXPECTED
