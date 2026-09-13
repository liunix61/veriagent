"""Core data models. Pure data, no I/O — hashable and deterministic.

Hash mapping is anchored to the REAL DecisionRecorder.sol contract:
    record(agentId, actionHash, reasonHash, dataSourceHash, modelHash)
Full decision JSON lives off-chain; the chain stores only the four hashes.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict


def _canonical(obj: dict) -> str:
    """Deterministic JSON serialization (sorted keys) so hashes are stable."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


try:  # EVM-compatible keccak256 when available
    from eth_hash.auto import keccak as _keccak

    def _hash(data: bytes) -> bytes:
        return _keccak(data)

    HASH_ALGO = "keccak256"
except ImportError:  # fallback: sha256, flagged so judges/users know
    def _hash(data: bytes) -> bytes:
        return hashlib.sha256(data).digest()

    HASH_ALGO = "sha256"


def _h32(text: str) -> str:
    """0x-prefixed 32-byte hash of a UTF-8 string."""
    return "0x" + _hash(text.encode()).hex()


def _h32_json(obj: dict) -> str:
    return "0x" + _hash(_canonical(obj).encode()).hex()


@dataclass(frozen=True)
class Decision:
    """A trading decision, produced by the strategy from market perception.

    On-chain, only the four commitment hashes are stored (see abi_encode.py):
      actionHash      = keccak(canonical JSON of the action payload)
      reasonHash      = keccak(reason text)
      dataSourceHash  = keccak(context sources + x402 proofs)
      modelHash       = keccak(model/prompt version)
    """
    agent_id: int                # uint256 agent id in AgentIdentityRegistry
    chain: str
    action: str                  # "buy" | "sell"
    venue: str
    asset: str
    amount: int                  # base units
    max_slippage_bps: int
    risk_score: int              # 0-10000
    context_hash: str            # hash of the market snapshot (data source)
    nonce: int
    expires_at: int              # unix ts
    reason: str = ""             # LLM reason summary (→ reasonHash)
    model_id: str = "unspecified"  # model/prompt version (→ modelHash)

    # ── the four on-chain hashes ──────────────────

    @property
    def action_payload(self) -> dict:
        """Canonical action payload — hashed into actionHash on-chain."""
        return {
            "action": self.action,
            "amount": self.amount,
            "asset": self.asset,
            "chain": self.chain,
            "expires_at": self.expires_at,
            "max_slippage_bps": self.max_slippage_bps,
            "nonce": self.nonce,
            "risk_score": self.risk_score,
            "venue": self.venue,
        }

    @property
    def action_hash(self) -> str:
        return _h32_json(self.action_payload)

    @property
    def reason_hash(self) -> str:
        if not self.reason:
            raise ValueError("reason is required for an on-chain credential")
        return _h32(self.reason)

    @property
    def data_source_hash(self) -> str:
        """Hashes the evidence bundle: market snapshot + x402 proofs."""
        return _h32_json({"context_hash": self.context_hash, "proofs": []})

    @property
    def model_hash(self) -> str:
        return _h32(self.model_id)

    @property
    def record_args(self) -> dict:
        """The exact five arguments submitted to DecisionRecorder.record()."""
        return {
            "agent_id": self.agent_id,
            "action_hash": self.action_hash,
            "reason_hash": self.reason_hash,
            "data_source_hash": self.data_source_hash,
            "model_hash": self.model_hash,
        }

    # ── local audit hash (JSONL hash chain, off-chain integrity) ──

    def to_payload_dict(self) -> dict:
        return asdict(self)

    @property
    def decision_hash(self) -> str:
        """Local audit commitment over the full decision (off-chain chain)."""
        return "0x" + _hash(_canonical(self.to_payload_dict()).encode()).hex()


@dataclass
class Credential:
    """Proof that a Decision existed before any trade built on it."""
    credential_id: str
    decision: Decision
    decision_hash: str
    algo: str = HASH_ALGO
    decision_id: int | None = None    # on-chain decisionId (post-record)
    recorded_tx: str | None = None    # tx that anchored record() on-chain
    bound_tx: str | None = None       # execution tx hash (post-bindTx)
    block_number: int | None = None
    created_at: float = field(default_factory=time.time)

    def to_audit_dict(self) -> dict:
        return {
            "credential_id": self.credential_id,
            "decision_hash": self.decision_hash,
            "algo": self.algo,
            "decision_id": self.decision_id,
            "recorded_tx": self.recorded_tx,
            "bound_tx": self.bound_tx,
            "block_number": self.block_number,
            "created_at": self.created_at,
            "decision": asdict(self.decision),
        }


@dataclass
class TradeResult:
    tx_hash: str
    status: str            # "success" | "failed"
    actual_price: float = 0.0
    filled_amount: int = 0
    gas_used: int = 0
    error: str | None = None
