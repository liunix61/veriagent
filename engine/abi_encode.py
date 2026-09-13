"""EVM encoding parity for DecisionRecorder.record() calls.

The real contract signature (authoritative):
    record(uint256 agentId, bytes32 actionHash, bytes32 reasonHash,
           bytes32 dataSourceHash, bytes32 modelHash) -> uint256 decisionId

All arguments are static (one uint256 + four bytes32), so the ABI encoding
is a plain 32-byte-word concatenation. This module produces the exact
calldata bytes an on-chain recorder would submit, and the four hashes are
computed from the SAME off-chain JSON the IPFS bundle would carry — so
re-computing from the published bundle reproduces the on-chain commitment
(verified end-to-end in HashParity.t.sol against a real deployed recorder).
"""

from __future__ import annotations

from eth_hash.auto import keccak

WORD = 32


def _word_int(v: int) -> bytes:
    if v < 0 or v >= 2 ** 256:
        raise ValueError("uint256 out of range")
    return v.to_bytes(WORD, "big")


def _word_b32(h: str) -> bytes:
    b = bytes.fromhex(h.lower().removeprefix("0x"))
    if len(b) != 32:
        raise ValueError(f"bytes32 required, got {len(b)} bytes: {h}")
    return b


RECORD_SELECTOR_INPUT = b""  # record() has no 4-byte selector in plain abi.encode


def encode_record_args(
    agent_id: int,
    action_hash: str,
    reason_hash: str,
    data_source_hash: str,
    model_hash: str,
) -> bytes:
    """Byte-identical to Solidity abi.encode of record()'s five arguments."""
    return (
        _word_int(agent_id)
        + _word_b32(action_hash)
        + _word_b32(reason_hash)
        + _word_b32(data_source_hash)
        + _word_b32(model_hash)
    )


def record_calldata(*args, **kwargs) -> bytes:
    """Full calldata: 4-byte selector + abi.encode(args).

    selector = first 4 bytes of keccak256(
        "record(uint256,bytes32,bytes32,bytes32,bytes32)")
    """
    sig = keccak(b"record(uint256,bytes32,bytes32,bytes32,bytes32)")[:4]
    return sig + encode_record_args(*args, **kwargs)
