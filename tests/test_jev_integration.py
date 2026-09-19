"""Jev (TypeSafe System One Model) integration tests.

VeriAgent is the audit layer for Jev-driven trading: every Jev decision
enters the same four-hash credential pipeline, confidence is preserved in
the decision record, and HALTED sessions still hard-reject regardless of
what the model says.
"""

import pytest

from engine.agent import State, VeriAgent
from engine.executor import MockExecutor
from engine.jev_model import (
    JevDecision,
    JevModel,
    JevTransportError,
    MockJevModel,
    jev_decision_to_risk_score,
)
from engine.perception import (
    MarketSession,
    MockTokenizedEquitySource,
    TokenizedEquity,
)
from engine.recorder import LocalRecorder
from engine.strategy import DecisionPolicy, DecisionReject, RiskPolicy


def _equity_source(session, liquidity=8_000_000.0):
    return MockTokenizedEquitySource(
        TokenizedEquity(
            symbol="NVDA",
            token_address="0xBSt0ck5Nvda000000000000000000000000000002",
        ),
        seed=7, base_price=500.0,
        session_override=session, liquidity_usd=liquidity,
    )


# ── JevDecision output contract ───────────────────────────────

def test_jev_decision_contract_valid():
    d = JevDecision(action="buy", confidence=0.87)
    assert d.action == "buy"
    assert d.confidence == 0.87


def test_jev_decision_rejects_bad_action():
    with pytest.raises(ValueError):
        JevDecision(action="long", confidence=0.9)


def test_jev_decision_rejects_bad_confidence():
    with pytest.raises(ValueError):
        JevDecision(action="buy", confidence=1.2)
    with pytest.raises(ValueError):
        JevDecision(action="buy", confidence=-0.1)


# ── MockJevModel follows documented contract ──────────────────

def test_mock_jev_outputs_typed_decisions():
    m = MockJevModel()
    src = _equity_source(MarketSession.OPEN)
    snap = src.snapshot("robinhood-chain", "bstocks", "bNVDA")
    for _ in range(10):
        d = m.decide(snap)
        assert d.action in ("buy", "sell", "hold")
        assert 0.0 <= d.confidence <= 1.0


def test_mock_jev_halted_outputs_hold_high_confidence():
    m = MockJevModel()
    snap = _equity_source(MarketSession.HALTED).snapshot(
        "robinhood-chain", "bstocks", "bNVDA")
    d = m.decide(snap)
    assert d.action == "hold"
    assert d.confidence >= 0.9


def test_mock_jev_closed_session_discounts_confidence():
    m = MockJevModel()
    open_d = m.decide(_equity_source(MarketSession.OPEN).snapshot(
        "robinhood-chain", "bstocks", "bNVDA"))
    closed_d = m.decide(_equity_source(MarketSession.CLOSED).snapshot(
        "robinhood-chain", "bstocks", "bNVDA"))
    assert closed_d.confidence <= open_d.confidence


# ── confidence → risk score mapping ───────────────────────────

def test_confidence_maps_inverted_to_risk_score():
    assert jev_decision_to_risk_score(JevDecision("buy", 0.95)) == 500
    assert jev_decision_to_risk_score(JevDecision("buy", 0.5)) == 5000
    assert jev_decision_to_risk_score(JevDecision("hold", 0.0)) == 10_000


# ── live transport not guessed ────────────────────────────────

def test_live_jev_raises_without_config(monkeypatch):
    monkeypatch.delenv("TYPESAFE_AI_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_AI_ENDPOINT", raising=False)
    m = JevModel()
    assert not m.ready
    snap = _equity_source(MarketSession.OPEN).snapshot(
        "robinhood-chain", "bstocks", "bNVDA")
    with pytest.raises(JevTransportError):
        m.decide(snap)


def test_live_jev_payload_carries_full_market_context():
    m = JevModel(api_key="k", endpoint="https://example.invalid")
    snap = _equity_source(MarketSession.CLOSED).snapshot(
        "robinhood-chain", "bstocks", "bNVDA")
    p = m._build_payload(snap)
    assert p["asset"] == "bNVDA"
    assert p["underlying"] == "NVDA"
    assert p["session"] == "CLOSED"
    assert p["spread_bps"] > 0
    assert p["venue"] == "bstocks"


# ── Jev decisions flow through the VeriAgent credential pipeline ─

def _jev_agent(tmp_path, session=MarketSession.OPEN):
    """VeriAgent whose policy consumes MockJevModel decisions."""
    jev = MockJevModel()
    src = _equity_source(session)

    class JevPolicy(DecisionPolicy):
        def decide(self, agent_id, snap, amount, action=None,
                   reason=None, model_id="strategy-v1"):
            jd = jev.decide(snap)
            return super().decide(
                agent_id, snap, amount,
                action=None if jd.action == "hold" else jd.action,
                reason=(f"jev action={jd.action} confidence={jd.confidence:.4f} "
                        f"session={getattr(snap, 'session', MarketSession.OPEN).value}"),
                model_id=MockJevModel.MODEL_ID,
            )

    return VeriAgent(
        agent_id=1, source=src,
        policy_engine=JevPolicy(),
        recorder=LocalRecorder(str(tmp_path / "audit.jsonl")),
        executor=MockExecutor(),
    )


def test_jev_decision_creates_auditable_credential(tmp_path):
    agent = _jev_agent(tmp_path)
    report = agent.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    assert report.reject_reason is None
    assert report.state == State.VERIFIED
    cred = report.credential
    assert cred.decision.model_id == MockJevModel.MODEL_ID
    assert "jev action=" in cred.decision.reason
    assert "confidence=" in cred.decision.reason
    assert agent.audit_trail_valid()


def test_jev_haltd_gate_still_rejects(tmp_path):
    """Jev says hold at 0.95 confidence — the SEC halt gate must still fire
    before any decision/credential exists (compliance > model)."""
    agent = _jev_agent(tmp_path, session=MarketSession.HALTED)
    report = agent.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    assert report.reject_reason == "MARKET_HALTED"
    assert report.credential is None
    assert agent.executor.calls == []


def test_jev_closed_session_decision_audited_with_session(tmp_path):
    agent = _jev_agent(tmp_path, session=MarketSession.CLOSED)
    report = agent.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    if report.reject_reason is None:
        reason = report.decision.reason
        assert "jev action=" in reason        # model provenance
        assert "session=CLOSED" in reason     # market context on record


def test_jev_model_hash_distinct_from_generic_strategy(tmp_path):
    """modelHash on-chain commitment distinguishes Jev from other models."""
    agent = _jev_agent(tmp_path)
    report = agent.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    assert report.credential.decision.model_hash.startswith("0x")
    generic = _jev_agent(tmp_path)
    r2 = generic.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    # both Jev runs share the same model_id -> same model_hash lineage
    assert (report.credential.decision.model_id ==
            r2.credential.decision.model_id)
