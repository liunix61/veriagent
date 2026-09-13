"""Credential recorder: turns Decisions into Credentials and anchors them.

Two modes:
- LocalRecorder   : append-only JSONL audit trail (demo/tests, no network)
- OnChainRecorder : anchors to DecisionRecorder.sol via RPC (W2 integration)

The credential MUST exist (local at minimum, on-chain before tx inclusion in
production) before the executor is allowed to run — enforced by agent.py.
"""

from __future__ import annotations

import json
import os
from .models import Credential, Decision


class LocalRecorder:
    """Append-only JSONL audit trail. Tamper-evident: each line carries the
    previous line's hash, forming a hash chain."""

    def __init__(self, path: str):
        self.path = path
        self._prev = "0x" + "00" * 32
        self._count = 0
        if os.path.exists(path):
            with open(path) as f:
                lines = [l for l in f.read().splitlines() if l.strip()]
            self._count = len(lines)
            if lines:
                self._prev = json.loads(lines[-1])["line_hash"]

    @property
    def count(self) -> int:
        return self._count

    def record(self, decision: Decision) -> Credential:
        from .models import _hash, _canonical, HASH_ALGO

        cred = Credential(
            credential_id=f"cred-{self._count + 1:06d}",
            decision=decision,
            decision_hash=decision.decision_hash,
        )
        entry = cred.to_audit_dict()
        entry["seq"] = self._count + 1
        entry["prev"] = self._prev
        entry["line_hash"] = "0x" + _hash(_canonical(entry).encode()).hex()
        self._prev = entry["line_hash"]

        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a") as f:
            f.write(_canonical(entry) + "\n")
        self._count += 1
        cred.algo = HASH_ALGO
        return cred

    def verify_chain(self) -> bool:
        """Re-walk the hash chain; True iff nothing was altered/removed."""
        from .models import _hash, _canonical

        if not os.path.exists(self.path):
            return True
        prev = "0x" + "00" * 32
        with open(self.path) as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                line_hash = entry.pop("line_hash")  # computed before it was added
                if entry["prev"] != prev:
                    return False
                expected = "0x" + _hash(_canonical(entry).encode()).hex()
                if line_hash != expected:
                    return False
                prev = line_hash
        return True


class OnChainRecorder:
    """Anchors credential hashes to DecisionRecorder.sol.

    Interface-complete; RPC wiring lands with the Sepolia deployment
    (needs RPC_URL + contract address + session key). Record() returns a
    Credential whose recorded_tx/block_number are filled from the receipt.
    """

    def __init__(self, rpc_url: str, contract_address: str, private_key: str):
        self.rpc_url = rpc_url
        self.contract_address = contract_address
        if not private_key:
            raise ValueError("session key required for on-chain recording")
        # web3 import deferred: engine must run without it in mock mode
        raise NotImplementedError(
            "OnChainRecorder activates after Sepolia deploy (W2 step 3)"
        )
