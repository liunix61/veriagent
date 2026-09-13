# VeriAgent Core Flows

> Created: 2026-09-13 | Related: 01-solution-overview / 02-system-architecture / 03-technical-framework

---

## Flow 1: Agent Registration & Identity

```
Developer             AgentIdentityRegistry           Off-chain
   │                        │                             │
   │ 1. strategy/model doc ─→│                             │──→ IPFS (full metadata)
   │ 2. registerAgent(hash) │                             │
   │←────── agentId ────────│                             │
   │ 3. bind session key    │                             │
   │    (rotateSessionKey)  │                             │
```

- One agentId = one verifiable "strategy datasheet" (metadataHash → model/prompt/strategy version)
- Optional ENS binding (`veri-001.eth`) for human-readable identity
- Reputation starts at 0: clean audited trades +1, violations -5

## Flow 2: User Creates a Vault

```
User                  VeriAgentVault                 Agent
 │ 1. createVault(agentId, policy)  │                  │
 │    (whitelist/position cap/loss/ │                  │
 │     cooldown)                    │                  │
 │ 2. deposit(USDC) ───────────────→│                  │
 │ 3. authorize session key ────────│←─ bound ─────────│
```

- Policy enters a **24h timelock** before activation — protects against mistakes and social engineering
- `emergencyPause()` available anytime; the agent is disabled instantly
- Vaults fully isolated: one agent may serve several vaults, permissions never shared

## Flow 3: Core Trade Loop (most important)

```
Agent engine                Off-chain                 Contracts
────────────                ─────────                 ─────────
T0 Perceive: mcp market data + x402 paid data
T1 Decide: LLM → decision JSON (schema-validated)
        ↓ retries ≤2 → HOLD fallback
T2 Off-chain risk: risk_manager checks
        ↓ pass
T3 Record: record(actionHash, reasonHash,
        dataSourceHash, modelHash)
        ──────────────────────────→ DecisionRecorder.record()
        ←────── decisionId ────────
T4 Execute: session-key signed tx
        ──────────────────────────→ Vault.executeTrade(trade)
                                     │ checkPolicy() (6 rules)
                                     │  ├─ pass → transfer + event
                                     │  └─ fail → revert(reason)
T5 Back-fill: bindTx(decisionId, txHash)
        ──────────────────────────→ DecisionRecorder.bindTx()
T6 Sleep tradeCooldown → back to T0
```

**Key design**: credential precedes trade (T3 < T4) — no "act first, justify later"; policy is re-checked at contract level even if off-chain risk fails.

## Flow 4: x402 Paid Data Purchase

```
Agent ──GET /api/signal──→ data service
     ←──402 + x402Payload──
Agent ──sign + settle(USDC)──→ PaymentRouter/facilitator
     ←──200 + data + proof──
data + proof → folded into dataSourceHash → Flow 3, T3
```

- Every paid data call leaves an on-chain trace — auditors can ask "what data did you look at, and what did it cost?"
- Loops without paid needs skip this step (mcp market data is free)

## Flow 5: Third-Party Audit Verification (Audit Explorer)

```
Verifier enters txHash
   → Explorer calls verifyTrade(txHash)
   → returns DecisionRecord {agentId, actionHash, reasonHash, ...}
   → fetch full decision JSON from IPFS
   → recompute keccak(JSON) == reasonHash ? ✅ untampered
   → check txHash ↔ decisionId ↔ agentId ↔ vault consistency
   → show agent identity / reputation / violation history
```

**Selling point**: verification requires trusting nobody on the VeriAgent team — pure on-chain + IPFS self-proof.

## Flow 6: Violations & Circuit Breakers

| Scenario | Detected by | Response |
|----------|-------------|----------|
| Trade outside whitelist | Vault.checkPolicy | revert; trade never happens |
| Daily loss limit reached | Vault.checkPolicy | all trades revert that day + event alert |
| Illegal LLM output | engine schema check | retry → HOLD, never on-chain |
| Emergency | user | emergencyPause freezes everything |
| Malicious session key | owner rotation + limits | old key instantly invalid |

## Flow 7: Hackathon Demo Script (3-min video)

```
00:00  Hook: "Would you let an AI agent manage your money?"
00:20  Create vault: set constraints (NVDA/TSLA whitelist, ≤10% position, ≤2% daily loss)
00:50  Agent runs autonomously: perceive→decide→record→execute, one full loop
01:30  Explorer verification: enter txHash → reasons, data sources, agent identity all shown
02:00  Attack demo: forged out-of-policy trade → contract reverts
02:30  Robinhood Chain deployment footage + track summary
```

## Exception Matrix

| Exception | Handling |
|-----------|----------|
| LLM timeout / invalid output | 2 retries → HOLD → "no-decision" event |
| x402 service down | degrade to free mcp data; dataSourceHash flags degradation |
| record succeeded, execute failed | credential kept as "decided, not executed" — honest and visible |
| RPC outage | engine backs off exponentially; cooldown naturally rate-limits |
