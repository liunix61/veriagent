# docs/07 — Funding Rate Strategy Integration (VeriAgent)

> v1.0 | 2026-09-20 | VeriAgent × Funding Rate Arbitrage
> Prerequisites: docs/01-04 core suite; this is a strategy-layer extension — "evidence before money" unchanged
> Status: Design doc (Phase 0) — pending user review before Phase 1 coding

## 1. Goal & Positioning

Integrate funding rate arbitrage as a **new decision source in VeriAgent's strategy layer**:
strategy output still flows through the full credential pipeline —
`Decision → record() on-chain → bindTx() → verifyTrade()` — arbitrage decisions receive the
same non-repudiable audit guarantees as any other trade decision.

**One line**: the moment the Agent says "I want to run a funding arb", the rationale, rate
evidence, and leg configuration are already anchored on-chain — no one can later claim
"the funding rate wasn't like that at the time".

## 2. Strategy Model (Operations → Decision Mapping)

| Play | Legs | Decision semantics |
|------|------|---------------------|
| Positive-rate arb | spot buy + perp short (equal notional) | open_arb / close_arb |
| Negative-rate reverse arb | perp long + margin spot short | open_arb_short_side |
| Cross-venue rate/spread | short leg at venue A + long leg at venue B | open_arb_cross_venue |

Core property: **delta-neutral two-leg structure** — income from funding cashflow, not direction.

## 3. Decision Object Extension (models.py, backward-compatible)

### 3.1 Extended fields (enter action_payload → automatically covered by actionHash)

```python
{
  "strategy": "funding_arb",
  "legs": [
    {"venue": "binance", "instrument": "spot", "asset": "BTC", "side": "buy",
     "amount": 100000000, "hedge_role": "spot"},
    {"venue": "binance", "instrument": "perp", "asset": "BTC", "side": "sell",
     "amount": 100000000, "hedge_role": "perp"}
  ],
  "funding_snapshot": {
    "venue": "binance", "asset": "BTCUSDT", "funding_rate_bps": 3.2,
    "next_settle_ts": 1758374400, "mark_price": 63250.5,
    "index_price": 63248.2, "open_interest_usd": 4200000000
  },
  "expected_income_bps": 128,
  "hedge_ratio": 1.00,
  "period_hours": 8
}
```

### 3.2 Zero contract changes (architectural advantage)

`DecisionRecorder.record()` stores only five hashes on-chain — the action_payload structure is
an **off-chain convention**; new fields flow automatically into
`actionHash = keccak(canonical JSON)`. Contracts are unaware of the new payload shape.
The existing abi_encode.py ↔ Solidity `abi.encode` byte-exact parity assertions keep holding.

### 3.3 reason format (reasonHash anchor)

```
"funding_arb binance:BTCUSDT rate=3.2bps/8h settle=2026-09-20T16:00Z
 expected_net=128bps(4p) fees=32bps legs=spot_buy+perp_short ratio=1.00
 session=OPEN"
```

### 3.4 model_id lineage

| Strategy version | model_id |
|------------------|----------|
| Rule-based | `funding-arb-v1` (Phase 1) |
| Jev integration | `jev-funding-v1` (future) |
| NanoJev integration | `nanojev-funding-0.6b` (Phase 4 narrative) |

Dual-track audit extends: **the same credential pipeline audits funding decisions of
different model lineages**.

## 4. Perception Layer Extension (perception.py)

```python
@dataclass(frozen=True)
class FundingRateSnapshot:
    venue: str
    asset: str
    funding_rate_bps: float    # current predicted rate (bps per period)
    funding_rate_avg_8h: float # 7-day mean (guards against single-point spikes)
    next_settle_ts: int
    mark_price: float
    index_price: float
    open_interest_usd: float
    volume_24h_usd: float
    ts: int
```

- `PerceptionSnapshot` gains optional field `funding: FundingRateSnapshot | None = None`
- `context_hash` covers the rate snapshot → `dataSourceHash` anchors rate evidence on-chain
- Data sources (Phase 2): Binance `/fapi/v1/premiumIndex`, OKX `/api/v5/public/funding-rate`,
  Bybit `/v5/market/tickers` — public REST endpoints, no API key needed for rates
- **Data-latency honesty**: credentials anchor the snapshot *predicted* rate; actual settled
  rates may differ — each settlement period's *realized* rate goes into the local JSONL audit
  chain for post-hoc reconciliation

## 5. Strategy Module Design (engine/funding_arb.py, new file)

```python
@dataclass
class FundingArbConfig:
    min_funding_rate_bps: float = 3.0
    min_avg_rate_bps: float = 1.5
    min_notional_usd: float = 500.0
    max_notional_usd: float = 50_000.0
    hedge_ratio_min: float = 0.95
    hedge_ratio_max: float = 1.05
    min_venue_oi_usd: float = 50_000_000.0
    fee_rate_bps: float = 8.0
    slippage_budget_bps: float = 10.0
    min_expected_net_bps: float = 30.0
    periods_to_hold: int = 4
    max_funding_notional_usd: float = 50_000.0

class FundingArbPolicy:
    """Mirrors DecisionPolicy: rate snapshot → Decision or DecisionReject."""

    def decide(self, agent_id, snap, amount_usd) -> Decision:
        # 1. session gate inherited (HALTED hard-reject for tokenized-equity perps)
        # 2. rate thresholds: rate >= min AND avg >= min_avg
        # 3. venue depth: OI >= min_venue_oi_usd
        # 4. net yield: gross = rate_bps × periods; cost = fees + slippage budget
        #    net < min_expected_net_bps → reject "FUNDING_EDGE_TOO_THIN"
        # 5. hedge ratio bounds → "HEDGE_RATIO_OUT_OF_BOUNDS"
        # 6. notional cap → "FUNDING_NOTIONAL_EXCEEDED"
        ...
```

**Rejection codes** (auditable via reasonHash):
`MARKET_HALTED / FUNDING_EDGE_TOO_THIN / HEDGE_RATIO_OUT_OF_BOUNDS / FUNDING_NOTIONAL_EXCEEDED / INSUFFICIENT_VENUE_DEPTH / FUNDING_RATE_TOO_THIN`

## 6. On-chain Policy Semantics (VeriAgentVault.sol 6 rules)

| Existing rule | Funding-arb semantics | Handling |
|---------------|----------------------|----------|
| Whitelist | venue whitelist must include CEX names | Phase 1 engine-side enforce; off-chain mode documented |
| Position cap | both legs' notionals count toward exposure (conservative) | documented + test assertion |
| Daily loss circuit-breaker | leg losses (slippage/rate reversal) count toward daily loss | inherited |
| Cooldown / rate-limit | two legs = one credential = one decision event | documented: one decision, one credential |
| Pause | engine consumes pause signals (off-chain CEX activity cannot be force-closed on-chain) | honestly flagged (§10) |

**Optional Phase 3 contract extensions** (non-blocking):
`funding_leg_pair_required` / `max_funding_notional` / `hedge_ratio_bounds` (9500-10500 bps on-chain).

**Execution-mode positioning**: CEX funding arb is off-chain activity — the credential pipeline
anchors **decisions and rate evidence on-chain**; `bindTx()` extends to bind arbitrary execution
proof hashes (CEX fill-report hashes); `verifyTrade` semantics unchanged.

## 7. Audit Chain Enhancement (recorder.py JSONL)

```
decision time:  decision (4 hashes + legs + rate snapshot)
execution:      leg_fill_reports (two-leg fill hashes + actual prices + slippage)
holding period: funding_settlements [{period_ts, rate_bps, income_usd, proof}]
close:          close_decision + close_fills + realized_pnl_summary
```

Chained-hash guarantee: tampering with any settlement record breaks the JSONL chain.
**Income verification loop**: external auditors reconcile claimed funding income against
on-chain-anchored rate snapshots + public exchange settlement data.

## 8. Test Plan (pytest + forge)

**pytest (Phase 1 engine-side)**:
- Hash stability: existing four-hash test vectors **zero breakage** (backward-compat assertions)
- Funding payload canonical-hash determinism
- Threshold rejection matrix: one case per rejection code
- Net-yield numeric assertions
- HALTED gate inheritance for tokenized-equity funding decisions
- Audit-chain funding lifecycle: decision → execution → multi-period settlements → close,
  JSONL chain integrity + tamper detection

**forge (mechanism compatibility)**:
- DecisionRecorder compatibility with funding payload hashes
- HashParity extension: funding payload byte-exact abi_encode ↔ abi.encode assertion
- If Phase 3 contract extensions proceed: leg-pair/hedge-ratio rule unit tests

## 9. Phased Implementation

| Phase | Content | Deliverable |
|-------|---------|-------------|
| **0 (this round)** | Design doc (bilingual) | docs/07 |
| **1** | engine/funding_arb.py + models/perception extensions + pytest + main.py demo mode | full funding decision pipeline on mock rate data |
| **2** | Live rate data sources (Binance/OKX/Bybit public REST) + multi-venue rate ranking | demo on real rate data |
| **3** | Optional contract policy extensions + FundingPanel frontend (rate ranking / position state / settlement income curves) | on-chain rules + visualization |
| **4** | NanoJev funding-decision fine-tuning narrative (JSONL audit history → training-data asset loop) | dual-track audit extended to arb strategy model layer |

**Buildathon narrative gain**: veriagent's "verifiable decisions" story + funding arb as a
real yield-bearing financial primitive — aligned with Arbitrum Promising Products
(AI agents + financial primitives) and Robinhood Chain track's "agents manage money with proof".

## 10. Risks & Honest Gaps

| Risk/Gap | Description | Mitigation |
|----------|-------------|------------|
| CEX custody risk | audit doesn't remove exchange counterparty risk | per-venue exposure caps; audit chain records venue distribution |
| Rate data latency | anchored snapshot ≠ settled rate | settlement records in audit chain for reconciliation |
| CEX execution authenticity | bindTx proof depends on exchange API receipts | fill-report hashing + API signature verification; trust assumption documented |
| Limited on-chain enforcement | off-chain CEX arb cannot be force-closed by on-chain policy | engine consumes signals; positioned as "decision audit" not "execution custody" |
| Single-leg risk | one leg fails/delays → delta exposure | credential records leg config; hedge drift monitored + recorded in audit chain |
| Fee erosion | taker fees + slippage can eat thin funding edges | 30bps net-yield entry filter; maker-first preference (configurable) |
| Strategy capacity | crowded arb drives rates to zero quickly | 7-day mean threshold + rate-trend fields in credentials (entry timing auditable) |

## 11. Boundary with Existing System

- **Unchanged**: four-hash credential mechanism / DecisionRecorder / AgentIdentityRegistry / verifyTrade
- **Extended**: action_payload field conventions / perception data classes / strategy class / audit record types
- **Optional**: VeriAgentVault policy rules (Phase 3)
- **Explicitly out of scope**: HFT market-making / directional leverage — VeriAgent's narrative is
  "verifiable decision audit layer", not a strategy factory; strategy sources are pluggable
  (Jev / NanoJev / rule-based funding), the credential pipeline never changes

---

*Phase 0 complete → pending user review → Phase 1 coding.*
*Chinese version: docs/07-资金费率策略集成方案.md*
