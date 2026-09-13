"""VeriAgent engine tests — the invariant is the star of the show."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.models import Decision
from engine.perception import MockMarketDataSource, PerceptionSnapshot
from engine.strategy import DecisionPolicy, RiskPolicy, DecisionReject
from engine.recorder import LocalRecorder
from engine.executor import MockExecutor
from engine.agent import VeriAgent, State, OrderViolation


def _decision(nonce: int = 1) -> Decision:
    return Decision(
        agent_id=1, chain="arbitrum-sepolia", action="buy",
        venue="uniswap-v3", asset="WETH", amount=10**16,
        max_slippage_bps=50, risk_score=1200,
        context_hash="0x" + "ab" * 32, nonce=nonce,
        expires_at=2_000_000_000,
        reason="test reason", model_id="test-model",
    )


def _agent(tmp_path, policy=None, fail_rate=0.0):
    return VeriAgent(
        agent_id=1,
        source=MockMarketDataSource(seed=7),
        policy_engine=DecisionPolicy(policy),
        recorder=LocalRecorder(str(tmp_path / "audit.jsonl")),
        executor=MockExecutor(fail_rate=fail_rate),
    )


# ── models ─────────────────────────────────────────

def test_decision_hash_deterministic():
    assert _decision().decision_hash == _decision().decision_hash


def test_decision_hash_changes_with_any_field():
    a, b = _decision(), _decision(nonce=2)
    assert a.decision_hash != b.decision_hash


# ── perception ─────────────────────────────────────

def test_mock_snapshot_deterministic():
    s1 = MockMarketDataSource(seed=3).snapshot("arb", "uni", "WETH")
    s2 = MockMarketDataSource(seed=3).snapshot("arb", "uni", "WETH")
    assert s1.context_hash == s2.context_hash
    assert s1.bid < s1.mid_price < s1.ask
    assert s1.spread_bps > 0


# ── strategy gates ─────────────────────────────────

def test_policy_rejects_thin_liquidity():
    pol = DecisionPolicy(RiskPolicy(min_liquidity_usd=10_000_000))
    snap = MockMarketDataSource().snapshot("arb", "uni", "WETH")
    with pytest.raises(DecisionReject, match="INSUFFICIENT_LIQUIDITY"):
        pol.decide(1, snap, 100)


def test_policy_rejects_wide_spread():
    pol = DecisionPolicy(RiskPolicy(max_spread_bps=0.001))
    snap = MockMarketDataSource().snapshot("arb", "uni", "WETH")
    with pytest.raises(DecisionReject, match="SPREAD_TOO_WIDE"):
        pol.decide(1, snap, 100)


def test_policy_nonce_monotonic():
    pol = DecisionPolicy()
    snap = MockMarketDataSource().snapshot("arb", "uni", "WETH")
    d1 = pol.decide(1, snap, 100)
    d2 = pol.decide(1, snap, 100)
    assert d2.nonce == d1.nonce + 1


# ── THE invariant ──────────────────────────────────

def test_execute_before_record_raises(tmp_path):
    agent = _agent(tmp_path)
    with pytest.raises(OrderViolation, match="before credential recorded"):
        agent.execute_trade()


def test_full_loop_records_before_executes(tmp_path):
    agent = _agent(tmp_path)
    report = agent.run_once("arbitrum-sepolia", "uniswap-v3", "WETH", 10**16)
    assert report.state == State.VERIFIED
    assert report.credential is not None
    assert report.result.status == "success"
    # credential file was written before the binding file exists...
    audit = tmp_path / "audit.jsonl"
    bindings = tmp_path / "audit.jsonl.bindings.jsonl"
    assert audit.exists() and bindings.exists()
    # ...and the executor only ever saw recorded credentials
    assert agent.executor.calls == [report.credential.credential_id]


def test_loop_rejection_leaves_no_credential(tmp_path):
    agent = _agent(tmp_path, policy=RiskPolicy(min_liquidity_usd=10_000_000))
    report = agent.run_once("arbitrum-sepolia", "uniswap-v3", "WETH", 10**16)
    assert report.reject_reason == "INSUFFICIENT_LIQUIDITY"
    assert not (tmp_path / "audit.jsonl").exists()
    assert agent.executor.calls == []


# ── audit trail ────────────────────────────────────

def test_audit_trail_hash_chain_valid(tmp_path):
    agent = _agent(tmp_path)
    for _ in range(3):
        agent.run_once("arbitrum-sepolia", "uniswap-v3", "WETH", 10**16)
    assert agent.audit_trail_valid()


def test_audit_trail_detects_tampering(tmp_path):
    agent = _agent(tmp_path)
    agent.run_once("arbitrum-sepolia", "uniswap-v3", "WETH", 10**16)
    agent.run_once("arbitrum-sepolia", "uniswap-v3", "WETH", 10**16)
    # tamper with line 1
    path = tmp_path / "audit.jsonl"
    lines = path.read_text().splitlines()
    entry = json.loads(lines[0])
    entry["decision"]["amount"] = 999_999_999
    lines[0] = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n")
    assert not agent.audit_trail_valid()


def test_binding_links_tx_to_credential(tmp_path):
    agent = _agent(tmp_path)
    report = agent.run_once("arbitrum-sepolia", "uniswap-v3", "WETH", 10**16)
    binding = json.loads(
        (tmp_path / "audit.jsonl.bindings.jsonl").read_text().strip()
    )
    assert binding["credential_id"] == report.credential.credential_id
    assert binding["decision_hash"] == report.credential.decision_hash
    assert binding["tx_hash"] == report.result.tx_hash
    assert report.tx_bound


# ── failure-mode demo: mock executor failure still binds ──

def test_failed_execution_still_binds_evidence(tmp_path):
    agent = _agent(tmp_path, fail_rate=1.0)
    report = agent.run_once("arbitrum-sepolia", "uniswap-v3", "WETH", 10**16)
    assert report.result.status == "failed"
    binding = json.loads(
        (tmp_path / "audit.jsonl.bindings.jsonl").read_text().strip()
    )
    assert binding["status"] == "failed"  # failures are also evidence
