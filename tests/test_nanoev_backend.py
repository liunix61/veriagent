"""NanoJev backend tests — open-source Jev replica as an alternative decision
provider behind the same VeriAgent audit pipeline.

NanoJev (TianyuCodings, forked at liunix61/NanoJev) self-hosts a 0.6B
decision model; the adapter maps its candidate distributions onto the same
JevDecision contract that Jev (TypeSafe) uses — model_id distinguishes the
lineage on-chain.
"""

import json
import pytest

from engine.jev_model import (
    JevDecision,
    JevTransportError,
    MockJevModel,
    NanoJevModel,
    jev_decision_to_risk_score,
)
from engine.perception import (
    MarketSession,
    MockTokenizedEquitySource,
    TokenizedEquity,
)
from engine.agent import State, VeriAgent
from engine.executor import MockExecutor
from engine.recorder import LocalRecorder
from engine.strategy import DecisionPolicy


def _snap(session=MarketSession.OPEN):
    src = MockTokenizedEquitySource(
        TokenizedEquity(symbol="NVDA",
                        token_address="0xNvda000000000000000000000000000000000002"),
        seed=7, base_price=500.0, session_override=session,
    )
    return src.snapshot("robinhood-chain", "bstocks", "bNVDA")


# ── request payload follows serve_decisions.py contract ───────

def test_payload_shape_matches_serving_contract():
    m = NanoJevModel(endpoint="http://127.0.0.1:8765")
    p = m.build_payload(_snap(MarketSession.CLOSED))
    assert "states" in p
    assert len(p["states"]) <= m.MAX_STATES
    st = p["states"][0]
    q = st["questions"]["trading_decision"]
    assert q["type"] == "choice"
    crits = q["criteria"]
    assert len(crits) == 3
    assert crits[0].startswith("buy")
    assert crits[1].startswith("sell")
    assert crits[2].startswith("hold")
    # state context carries full market + session
    assert "CLOSED" in st["state"]
    assert "bNVDA" in st["state"]


def test_payload_paths_within_demo_limit():
    m = NanoJevModel()
    p = m.build_payload(_snap())
    total = sum(
        len(q["criteria"])
        for s in p["states"] for q in s["questions"].values()
    )
    assert total <= m.MAX_PATHS


# ── response parsing: distribution -> JevDecision ─────────────

def test_parse_response_argmax_with_named_keys():
    m = NanoJevModel()
    raw = {"questions": {"trading_decision": {
        "distribution": {"buy": 0.71, "sell": 0.19, "hold": 0.10}}}}
    d = m.parse_response(raw)
    assert d.action == "buy"
    assert d.confidence == 0.71


def test_parse_response_tolerates_described_keys():
    m = NanoJevModel()
    raw = {"questions": {"trading_decision": {"probabilities": {
        "buy: increase position at the touch": 0.22,
        "sell: decrease position at the touch": 0.63,
        "hold: no order this block": 0.15}}}}
    d = m.parse_response(raw)
    assert d.action == "sell"
    assert d.confidence == 0.63


def test_parse_response_single_fallback_key():
    m = NanoJevModel()
    raw = {"answers": {"only_q": {"distribution": {"hold": 0.9, "buy": 0.1}}}}
    d = m.parse_response(raw)
    assert d.action == "hold"
    assert d.confidence == 0.9


def test_parse_response_missing_distribution_raises():
    m = NanoJevModel()
    with pytest.raises(JevTransportError):
        m.parse_response({"questions": {"trading_decision": {}}})
    with pytest.raises(JevTransportError):
        m.parse_response({})


# ── transport error names the fix ─────────────────────────────

def test_decide_unreachable_server_names_the_fix():
    m = NanoJevModel(endpoint="http://127.0.0.1:1", timeout_sec=0.3)
    with pytest.raises(JevTransportError) as ei:
        m.decide(_snap())
    assert "serve_decisions.py" in str(ei.value)  # actionable recovery cmd


# ── same pipeline, different model lineage ────────────────────

class _FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_nanoev_decision_through_veriagent_pipeline(monkeypatch, tmp_path):
    """NanoJev decision -> four-hash credential, lineage on record."""
    import urllib.request
    m = NanoJevModel(endpoint="http://nanoev.test")
    payload_out = {"questions": {"trading_decision": {
        "distribution": {"buy": 0.82, "sell": 0.12, "hold": 0.06}}}}

    def fake_urlopen(req, timeout=None):
        # verify the wire payload on the way through
        body = json.loads(req.data.decode())
        assert body["states"][0]["questions"]["trading_decision"]["type"] == "choice"
        return _FakeResp(payload_out)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    jd = m.decide(_snap())
    assert jd == JevDecision(action="buy", confidence=0.82)

    # full VeriAgent loop driven by NanoJev decisions
    class NanoPolicy(DecisionPolicy):
        def decide(self, agent_id, snap, amount, action=None,
                   reason=None, model_id="strategy-v1"):
            d = m.decide(snap)
            return super().decide(
                agent_id, snap, amount,
                action=None if d.action == "hold" else d.action,
                reason=(f"nanojev action={d.action} confidence={d.confidence:.4f} "
                        f"session={getattr(snap, 'session', MarketSession.OPEN).value}"),
                model_id=NanoJevModel.MODEL_ID,
            )

    agent = VeriAgent(
        agent_id=1, source=MockTokenizedEquitySource(
            TokenizedEquity(symbol="NVDA", token_address="0xNvda00...02"),
            seed=7, base_price=500.0, session_override=MarketSession.OPEN),
        policy_engine=NanoPolicy(),
        recorder=LocalRecorder(str(tmp_path / "audit.jsonl")),
        executor=MockExecutor(),
    )
    report = agent.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    assert report.reject_reason is None
    assert report.state == State.VERIFIED
    cred = report.credential
    assert cred.decision.model_id == NanoJevModel.MODEL_ID
    assert "nanojev action=buy" in cred.decision.reason
    assert "confidence=0.8200" in cred.decision.reason
    assert agent.audit_trail_valid()


def test_nanoev_and_mock_lineages_have_distinct_model_ids():
    assert NanoJevModel.MODEL_ID != MockJevModel.MODEL_ID
    assert NanoJevModel.MODEL_ID != "jev-systemone"
    # risk-score mapping is shared across all Jev-contract models
    assert jev_decision_to_risk_score(JevDecision("buy", 0.82)) == 1800
