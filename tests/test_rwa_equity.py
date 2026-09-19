"""RWA tokenized-equity tests (bStocks on Robinhood Chain).

Covers the SEC Innovation Exemption (2026-09-17) compliance surface:
  - primary-market HALTED -> hard trade reject (concurrent-halt condition)
  - CLOSED -> tradable but risk-scored (thin-liquidity premium)
  - dividend passthrough acknowledged as auditable credential (No Synthetics)
"""

import datetime
import pytest

from engine.agent import State, VeriAgent, DividendReceipt
from engine.executor import MockExecutor
from engine.models import DividendEvent
from engine.perception import (
    EquitySessionCalendar,
    MarketSession,
    MockTokenizedEquitySource,
    TokenizedEquity,
)
from engine.recorder import LocalRecorder
from engine.strategy import DecisionPolicy, DecisionReject, RiskPolicy


def _agent(tmp_path, source=None):
    return VeriAgent(
        agent_id=1,
        source=source or MockTokenizedEquitySource(
            TokenizedEquity(
                symbol="AAPL",
                token_address="0xBSt0ck5Aap1e0000000000000000000000000001",
                dividend_per_share=0.25,
            ),
            seed=7,
            base_price=195.0,
        ),
        policy_engine=DecisionPolicy(),
        recorder=LocalRecorder(str(tmp_path / "audit.jsonl")),
        executor=MockExecutor(),
    )


def _equity_source(session, **kw):
    return MockTokenizedEquitySource(
        TokenizedEquity(
            symbol="NVDA",
            token_address="0xBSt0ck5Nvda000000000000000000000000000002",
            dividend_per_share=0.10,
        ),
        seed=7,
        base_price=500.0,
        session_override=session,
        **kw,
    )


# ── EquitySessionCalendar ─────────────────────────────────────

def test_calendar_open_during_us_regular_hours():
    cal = EquitySessionCalendar()
    ts = datetime.datetime(2026, 9, 24, 15, 0, tzinfo=datetime.timezone.utc).timestamp()
    assert cal.session_at(ts) == MarketSession.OPEN  # Thursday 15:00 UTC


def test_calendar_closed_out_of_hours():
    cal = EquitySessionCalendar()
    ts = datetime.datetime(2026, 9, 24, 2, 0, tzinfo=datetime.timezone.utc).timestamp()
    assert cal.session_at(ts) == MarketSession.CLOSED  # 02:00 UTC = NY night


def test_calendar_closed_on_weekend():
    cal = EquitySessionCalendar()
    ts = datetime.datetime(2026, 9, 26, 12, 0, tzinfo=datetime.timezone.utc).timestamp()
    assert cal.session_at(ts) == MarketSession.CLOSED  # Saturday


def test_calendar_halted_overrides_everything():
    cal = EquitySessionCalendar()
    ts = datetime.datetime(2026, 9, 24, 15, 0, tzinfo=datetime.timezone.utc).timestamp()
    cal.mark_halt(until_ts=ts + 3600)
    assert cal.session_at(ts) == MarketSession.HALTED
    # halt expires -> back to calendar logic
    assert cal.session_at(ts + 7200) != MarketSession.HALTED


def test_calendar_holiday_closed():
    cal = EquitySessionCalendar(holidays={"2026-12-25"})
    ts = datetime.datetime(2026, 12, 25, 15, 0, tzinfo=datetime.timezone.utc).timestamp()
    assert cal.session_at(ts) == MarketSession.CLOSED


# ── tokenized-equity perception ───────────────────────────────

def test_equity_source_carries_metadata():
    src = _equity_source(MarketSession.OPEN)
    snap = src.snapshot("robinhood-chain", "bstocks", "bNVDA")
    assert snap.underlying == "NVDA"
    assert snap.session == MarketSession.OPEN
    assert snap.dividend_per_share == 0.10
    assert snap.venue == "bstocks"


def test_session_changes_context_hash():
    src_open = _equity_source(MarketSession.OPEN)
    src_halted = _equity_source(MarketSession.HALTED)
    h1 = src_open.snapshot("robinhood-chain", "bstocks", "bNVDA").context_hash
    h2 = src_halted.snapshot("robinhood-chain", "bstocks", "bNVDA").context_hash
    assert h1 != h2  # audit trail proves WHICH session the agent saw


def test_closed_session_widens_spread_thins_liquidity():
    src = _equity_source(MarketSession.CLOSED)
    snap = src.snapshot("robinhood-chain", "bstocks", "bNVDA")
    assert snap.spread_bps > 6.0          # 3x spread multiplier after hours
    assert snap.liquidity_usd < 3_000_000  # 30% of regular liquidity


# ── session gate in decision policy (SEC concurrent-halt rule) ─

def test_halted_market_rejects_trade(tmp_path):
    agent = _agent(tmp_path, source=_equity_source(MarketSession.HALTED))
    report = agent.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    assert report.reject_reason == "MARKET_HALTED"
    assert report.credential is None       # nothing recorded, nothing executed
    assert agent.executor.calls == []


def test_halted_gate_can_be_disabled(tmp_path):
    policy = DecisionPolicy(RiskPolicy(enforce_session=False))
    src = _equity_source(MarketSession.HALTED)
    agent = VeriAgent(
        agent_id=1, source=src, policy_engine=policy,
        recorder=LocalRecorder(str(tmp_path / "audit.jsonl")),
        executor=MockExecutor(),
    )
    report = agent.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    assert report.reject_reason is None  # override path (emergency operator mode)


def test_closed_market_trades_with_risk_premium(tmp_path):
    agent = _agent(tmp_path, source=_equity_source(MarketSession.CLOSED))
    report = agent.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    assert report.reject_reason is None
    assert report.state == State.VERIFIED
    d = report.decision
    assert d.risk_score >= 3000             # thin-liquidity premium applied
    assert "session=CLOSED" in d.reason     # audit trail records the session


def test_open_market_normal_flow(tmp_path):
    agent = _agent(tmp_path, source=_equity_source(MarketSession.OPEN))
    report = agent.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    assert report.state == State.VERIFIED
    assert "session=OPEN" in report.decision.reason
    assert "session=CLOSED" not in report.decision.reason


def test_closed_market_risk_exceeds_open(tmp_path):
    """CLOSED session must carry strictly more risk than OPEN (premium)."""
    open_src = _equity_source(MarketSession.OPEN)
    closed_src = _equity_source(MarketSession.CLOSED)
    a_open = _agent(tmp_path / "o", source=open_src)
    a_closed = _agent(tmp_path / "c", source=closed_src)
    r_open = a_open.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    r_closed = a_closed.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    assert r_closed.decision.risk_score >= r_open.decision.risk_score + 3000


def test_reject_on_liquidity_still_works_with_session(tmp_path):
    src = _equity_source(MarketSession.OPEN, liquidity_usd=50_000.0)
    agent = _agent(tmp_path, source=src)
    report = agent.run_once("robinhood-chain", "bstocks", "bNVDA", 10**16)
    assert report.reject_reason == "INSUFFICIENT_LIQUIDITY"


# ── dividend passthrough (SEC No Synthetics) ──────────────────

def _dividend_event():
    return DividendEvent(
        asset="bAAPL",
        token_address="0xBSt0ck5Aap1e0000000000000000000000000001",
        underlying="AAPL",
        per_share=0.25,
        total_amount=125.50,
        ex_date="2026-09-18",
        pay_date="2026-09-24",
        source_tx="0xd1v1d3nd",
    )


def test_dividend_ack_creates_credential(tmp_path):
    agent = _agent(tmp_path)
    receipt = agent.run_dividend(_dividend_event())
    assert receipt.recorded
    assert isinstance(receipt, DividendReceipt)
    cred = receipt.credential
    assert cred.decision.action == "dividend_ack"
    assert cred.decision.asset == "bAAPL"
    # four-hash audit chain is intact
    assert agent.audit_trail_valid()


def test_dividend_never_reaches_executor(tmp_path):
    agent = _agent(tmp_path)
    agent.run_dividend(_dividend_event())
    assert agent.executor.calls == []  # dividends are proven, not traded


def test_dividend_reason_carries_event_details(tmp_path):
    agent = _agent(tmp_path)
    receipt = agent.run_dividend(_dividend_event())
    reason = receipt.credential.decision.reason
    assert "AAPL" in reason
    assert "dps=0.2500" in reason
    assert "total=125.50" in reason
    assert "ex=2026-09-18" in reason


def test_two_dividends_distinct_credentials(tmp_path):
    agent = _agent(tmp_path)
    r1 = agent.run_dividend(_dividend_event())
    ev2 = DividendEvent(
        asset="bNVDA",
        token_address="0xBSt0ck5Nvda000000000000000000000000000002",
        underlying="NVDA", per_share=0.10, total_amount=42.0,
        ex_date="2026-09-20", pay_date="2026-09-26",
    )
    r2 = agent.run_dividend(ev2)
    assert r1.credential.decision_hash != r2.credential.decision_hash
    assert agent.recorder.count == 2
    assert agent.audit_trail_valid()


def test_dividend_then_trade_share_same_audit_chain(tmp_path):
    agent = _agent(tmp_path)
    agent.run_dividend(_dividend_event())
    report = agent.run_once("robinhood-chain", "bstocks", "bAAPL", 10**16)
    assert report.state == State.VERIFIED
    assert agent.recorder.count == 2   # dividend ack + trade in one hash chain
    assert agent.audit_trail_valid()
