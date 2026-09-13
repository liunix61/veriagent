"""EVM abi.encode parity for Decision payloads.

Solidity DecisionRecorder computes:
    keccak256(abi.encode(agentId, chain, action, venue, asset, amount,
                         maxSlippageBps, riskScore, contextHash, nonce, expiresAt))

This module produces the byte-identical encoding in Python so an off-chain
credential hashes to the same on-chain commitment. Parity is proven by a
fixed test vector asserted in BOTH pytest and forge test (DecisionRecorder.t.sol).
"""

from __future__ import annotations

from eth_hash.auto import keccak

WORD = 32


def _pad32(b: bytes, left: bool) -> bytes:
    if len(b) > WORD:
        raise ValueError("value longer than 32 bytes")
    pad = b"\x00" * (WORD - len(b))
    return pad + b if left else b + pad


def _uint256(v: int) -> bytes:
    if v < 0 or v >= 2 ** 256:
        raise ValueError("uint256 out of range")
    return v.to_bytes(WORD, "big")


def _address(addr: str) -> bytes:
    a = addr.lower().removeprefix("0x")
    if len(a) != 40:
        raise ValueError("bad address")
    return _pad32(bytes.fromhex(a), left=True)


def _bytes32(b: bytes) -> bytes:
    return _pad32(b, left=False)


def _dynamic(data: bytes) -> tuple[bytes, bytes]:
    """Return (placeholder, tail) for a dynamic bytes/string value."""
    tail = _uint256(len(data)) + _pad32(data, left=False) if len(data) % WORD == 0 \
        else _uint256(len(data)) + data + b"\x00" * (WORD - len(data) % WORD)
    return b"", tail


def encode_decision_payload(
    agent_id: str,
    chain: str,
    action: str,
    venue: str,
    asset: str,
    amount: int,
    max_slippage_bps: int,
    risk_score: int,
    context_hash: str,
    nonce: int,
    expires_at: int,
) -> bytes:
    """Byte-identical to Solidity abi.encode of DecisionPayload fields."""
    dynamics = [chain.encode(), action.encode(), venue.encode(), asset.encode()]
    n_static = 7  # agentId, amount, maxSlippageBps, riskScore, contextHash, nonce, expiresAt
    n_slots = n_static + len(dynamics)
    head_size = n_slots * WORD

    heads: list[bytes] = []
    tails: list[bytes] = []
    offset = head_size

    # order matters: agentId, chain, action, venue, asset, amount, ...
    heads.append(_address(agent_id))
    for d in dynamics:
        heads.append(_uint256(offset))
        padded = d + b"\x00" * ((WORD - len(d) % WORD) % WORD)
        tail = _uint256(len(d)) + padded
        tails.append(tail)
        offset += len(tail)

    heads.append(_uint256(amount))
    heads.append(_uint256(max_slippage_bps))
    heads.append(_uint256(risk_score))
    ch = context_hash.lower().removeprefix("0x")
    heads.append(_bytes32(bytes.fromhex(ch)))
    heads.append(_uint256(nonce))
    heads.append(_uint256(expires_at))

    assert len(heads) == n_slots
    return b"".join(heads) + b"".join(tails)


def decision_payload_hash(**kwargs) -> str:
    return "0x" + keccak(encode_decision_payload(**kwargs)).hex()
