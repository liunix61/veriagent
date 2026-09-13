"""VeriAgent core loop with the ordering invariant enforced by a state machine.

States: IDLE → PERCEIVED → DECIDED → RECORDED → EXECUTED → VERIFIED
Any attempt to skip RECORDED raises OrderViolation. This is the engine-side
mirror of DecisionRecorder's two-phase record→bindTx; the chain is the
authority in production, this state machine is the guarantee in the engine.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum

from .models import Decision, Credential, TradeResult
from .perception import MarketDataSource, PerceptionSnapshot
from .strategy import DecisionPolicy, DecisionReject
from .recorder import LocalRecorder
from .executor import Executor


class State(str, Enum):
    IDLE = "IDLE"
    PERCEIVED = "PERCEIVED"
    DECIDED = "DECIDED"
    RECORDED = "RECORDED"
    EXECUTED = "EXECUTED"
    VERIFIED = "VERIFIED"


class OrderViolation(Exception):
    """A trade was attempted before its credential existed."""


@dataclass
class LoopReport:
    state: State
    decision: Decision | None = None
    credential: Credential | None = None
    result: TradeResult | None = None
    reject_reason: str | None = None
    tx_bound: bool = False


@dataclass
class VeriAgent:
    agent_id: int
    source: MarketDataSource
    policy_engine: DecisionPolicy
    recorder: LocalRecorder
    executor: Executor
    _state: State = State.IDLE
    _cred: Credential | None = None
    _decision: Decision | None = None
    history: list[LoopReport] = field(default_factory=list)

    # ── invariant enforcement ─────────────────────

    def _assert_order(self, allowed: set[State]) -> None:
        if self._state not in allowed:
            raise OrderViolation(
                f"illegal transition from {self._state.value} "
                f"(expected one of {sorted(s.value for s in allowed)})"
            )

    def execute_trade(self) -> TradeResult:
        """Public hook demonstrating the invariant: without a recorded
        credential the executor is unreachable."""
        if self._state != State.RECORDED or self._cred is None:
            raise OrderViolation(
                "trade attempted before credential recorded — "
                "this is the exact failure mode the project exists to prevent"
            )
        return self._run_execution(self._cred)

    def _run_execution(self, cred: Credential) -> TradeResult:
        result = self.executor.execute(cred)
        self._bind_tx(cred, result)
        self._state = State.EXECUTED
        return result

    def _bind_tx(self, cred: Credential, result: TradeResult) -> None:
        """Bind execution tx back to the credential (mirrors bindTx)."""
        cred.bound_tx = result.tx_hash
        binding_path = self.recorder.path + ".bindings.jsonl"
        with open(binding_path, "a") as f:
            f.write(json.dumps({
                "credential_id": cred.credential_id,
                "decision_hash": cred.decision_hash,
                "tx_hash": result.tx_hash,
                "status": result.status,
                "ts": time.time(),
            }, sort_keys=True) + "\n")

    # ── one full loop ─────────────────────────────

    def run_once(self, chain: str, venue: str, asset: str,
                 amount: int) -> LoopReport:
        report = LoopReport(state=State.IDLE)
        try:
            # 1. perceive
            snap: PerceptionSnapshot = self.source.snapshot(chain, venue, asset)
            self._state = State.PERCEIVED
            report.state = self._state

            # 2. decide
            decision = self.policy_engine.decide(self.agent_id, snap, amount)
            self._decision = decision
            self._state = State.DECIDED
            report.decision = decision

            # 3. record — MUST succeed before any execution path opens
            cred = self.recorder.record(decision)
            self._cred = cred
            self._state = State.RECORDED
            report.credential = cred

            # 4. execute (only reachable via RECORDED)
            result = self._run_execution(cred)
            report.result = result

            # 5. verify binding
            report.tx_bound = (
                self._cred.bound_tx == result.tx_hash
                and result.tx_hash is not None
            )
            self._state = State.VERIFIED if report.tx_bound else State.EXECUTED
            report.state = self._state

        except DecisionReject as e:
            report.reject_reason = e.reason
        finally:
            self.history.append(report)
            self._state = State.IDLE
            self._cred = None
            self._decision = None
        return report

    def audit_trail_valid(self) -> bool:
        return self.recorder.verify_chain()
