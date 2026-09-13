#!/usr/bin/env python3
"""VeriAgent demo: one command runs the full verifiable loop.

    python3 main.py --loops 5 --chain arbitrum-sepolia

Output shows, per loop: decision → credential (hash) → tx binding, then
verifies the tamper-evident audit trail. Exit code 0 iff audit valid.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.perception import MockMarketDataSource
from engine.strategy import DecisionPolicy, RiskPolicy
from engine.recorder import LocalRecorder
from engine.executor import MockExecutor
from engine.agent import VeriAgent, State
from engine.models import HASH_ALGO


def main() -> int:
    ap = argparse.ArgumentParser(description="VeriAgent verifiable-loop demo")
    ap.add_argument("--loops", type=int, default=5)
    ap.add_argument("--chain", default="arbitrum-sepolia")
    ap.add_argument("--venue", default="uniswap-v3")
    ap.add_argument("--asset", default="WETH")
    ap.add_argument("--amount", type=int, default=10 ** 16, help="base units")
    ap.add_argument("--audit", default="audit/demo.jsonl")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    agent = VeriAgent(
        agent_id="demo-agent-1",
        source=MockMarketDataSource(seed=args.seed),
        policy_engine=DecisionPolicy(RiskPolicy()),
        recorder=LocalRecorder(args.audit),
        executor=MockExecutor(),
    )

    print(f"VeriAgent demo — {args.loops} loops on {args.chain}/{args.venue}")
    print(f"hash algo: {HASH_ALGO}  | audit trail: {args.audit}\n")

    for i in range(1, args.loops + 1):
        report = agent.run_once(args.chain, args.venue, args.asset, args.amount)
        if report.reject_reason:
            print(f"[{i}] REJECTED  {report.reject_reason}")
            continue
        d, c, r = report.decision, report.credential, report.result
        assert d is not None and c is not None and r is not None  # non-rejected loop invariant
        print(f"[{i}] {report.state.value:9s} nonce={d.nonce} {d.action} {d.amount} {d.asset}")
        print(f"     cred={c.credential_id} hash={c.decision_hash[:18]}…")
        print(f"     tx={r.tx_hash[:18]}… status={r.status} bound={report.tx_bound}")

    valid = agent.audit_trail_valid()
    creds = agent.recorder.count
    print(f"\naudit trail: {creds} credentials, hash-chain valid = {valid}")
    print("verifiable end-to-end: decision existed BEFORE trade, tampering detectable")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
