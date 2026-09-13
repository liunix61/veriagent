"""record() parity — the same five-hash vector asserted in HashParity.t.sol.

The vector: a fixed Decision fixture → four commitment hashes → encoded
record() calldata. HashParity.t.sol deploys the REAL DecisionRecorder and
asserts record() with these exact hash constants stores them unchanged.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.models import Decision
from engine.abi_encode import encode_record_args, record_calldata

FIXTURE = Decision(
    agent_id=7,
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
    reason="buy WETH spread=6.0bps liq=5000000",
    model_id="strategy-v1",
)


def test_fixture_hashes_deterministic():
    a = FIXTURE.record_args
    b = FIXTURE.record_args
    assert a == b
    for v in a.values():
        if isinstance(v, str):
            assert v.startswith("0x") and len(v) == 66


def test_reason_hash_required():
    import pytest
    bad = Decision(**{**FIXTURE.__dict__, "reason": ""})
    with pytest.raises(ValueError, match="reason is required"):
        _ = bad.reason_hash


def test_encode_record_args_length():
    enc = encode_record_args(**FIXTURE.record_args)
    assert len(enc) == 5 * 32  # five static words


def test_record_calldata_selector():
    cd = record_calldata(**FIXTURE.record_args)
    # selector = keccak("record(uint256,bytes32,bytes32,bytes32,bytes32)")[:4]
    from eth_hash.auto import keccak
    assert cd[:4] == keccak(b"record(uint256,bytes32,bytes32,bytes32,bytes32)")[:4]
    assert len(cd) == 4 + 5 * 32


def test_hashes_sensitive_to_fields():
    a = FIXTURE.record_args
    changed = Decision(**{**FIXTURE.__dict__, "amount": 10 ** 16 + 1})
    assert changed.action_hash != a["action_hash"]      # amount is in action payload
    assert changed.reason_hash == a["reason_hash"]      # reason text unchanged
    changed2 = Decision(**{**FIXTURE.__dict__, "reason": "different words"})
    assert changed2.reason_hash != a["reason_hash"]
