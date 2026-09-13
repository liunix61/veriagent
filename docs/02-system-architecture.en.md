# VeriAgent System Architecture

> Created: 2026-09-13 | Related: 01-solution-overview / 03-technical-framework / 04-core-flows

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Nuxt4)                          │
│   Vault console          Agent market        Audit Explorer      │
└────────┬───────────────────┬──────────────────┬─────────────────┘
         │ viem (JSON-RPC)   │                  │
┌────────▼───────────────────▼──────────────────▼─────────────────┐
│                     Contracts (Solidity)                          │
│  ┌────────────────┐ ┌─────────────────┐ ┌──────────────────┐   │
│  │ AgentIdentity  │ │  VeriAgentVault │ │ DecisionRecorder │   │
│  │  Registry      │ │  (policy vault) │ │  (credentials)   │   │
│  │ (ERC-8004-like)│ │                 │ │                  │   │
│  └────────────────┘ └─────────────────┘ └──────────────────┘   │
│  ┌────────────────┐                                            │
│  │ PaymentRouter  │  x402 on-chain settlement (USDC)           │
│  └────────────────┘                                            │
└────────┬───────────────────────────────────────────────────────┘
         │ Deployed on: Arbitrum Sepolia (baseline) / Robinhood Chain (main)
┌────────▼───────────────────────────────────────────────────────┐
│              Agent Engine (Python, from HOODflow)                │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
│  │Perceive  │→│ Decide    │→│ Record    │→│ Execute      │  │
│  │(MCP      │  │(LLM +    │  │(hash +    │  │(session-key  │  │
│  │ client)  │  │ schema)  │  │ on-chain) │  │ trade)       │  │
│  └────┬─────┘  └──────────┘  └───────────┘  └──────────────┘  │
│       │         off-chain risk_manager.py fallback             │
└───────┼────────────────────────────────────────────────────────┘
        │ MCP protocol                │ HTTP 402 (x402)
┌───────▼─────────────┐   ┌──────────▼─────────────────────────┐
│ robinhood-evm-mcp   │   │ x402 paid data services             │
│ (16 tools: prices/  │   │ (CMC data / research agents /       │
│  trading/liquidity) │   │  oracles)                           │
└─────────────────────┘   └────────────────────────────────────┘
```

## 2. Contract Layer Design

### 2.1 AgentIdentityRegistry (identity & reputation)

```
AgentRecord {
    agentId (uint256, auto-increment)
    owner (address)           // controller; can rotate session key
    ensName (string)          // e.g. "veri-001.eth" (optional)
    metadataHash (bytes32)    // IPFS hash of strategy/model version
    registeredAt (uint64)
    reputation (int256)       // +1 clean audits, -5 violations
    active (bool)
}
```

- ERC-8004-style on-chain identity + reputation registry
- `registerAgent()` / `rotateSessionKey()` / `slashReputation()`

### 2.2 VeriAgentVault (policy vault, core contract)

```
VaultPolicy {
    assetWhitelist (address[])  // tradable tokens (bStocks)
    maxPositionPct (uint16)     // per-asset cap in bps (1000 = 10%)
    dailyLossLimitBps (uint16)  // daily-loss circuit breaker
    tradeCooldown (uint32)      // min seconds between trades
    maxTradesPerDay (uint16)
}

Key functions:
- deposit()/withdraw()          // user funds (owner only)
- executeTrade(agentId, trade)  // only the vault's bound session key
- checkPolicy(trade) → bool     // all constraints checked on-chain
- updatePolicy(policy)          // owner only + timelock
- emergencyPause()              // user instant freeze
```

**Security design**:
- The agent never has custody — only an "execute" entry point filtered by policy
- Policy changes are owner-only with a 24h timelock
- Daily loss is computed from oracle price snapshots the agent cannot manipulate

### 2.3 DecisionRecorder (decision credentials, innovation core)

```
DecisionRecord {
    decisionId (uint256)
    agentId (uint256)
    vaultAddr (address)
    actionHash (bytes32)      // keccak(action JSON: side/amount/asset)
    reasonHash (bytes32)      // keccak(LLM reason summary)
    dataSourceHash (bytes32)  // keccak(data sources + x402 proofs)
    modelHash (bytes32)       // keccak(model/prompt version)
    timestamp (uint64)
    txHash (bytes32)          // execution tx hash (back-filled)
}
```

- Two-phase: `record()` at decision time → `bindTx()` after execution
- `verifyTrade(txHash) → DecisionRecord` for Explorer and third parties
- Full JSON lives off-chain (IPFS/Arweave); only hashes on-chain — cheap yet verifiable

### 2.4 PaymentRouter (x402 settlement)

- Agent calls a paid data service → service returns HTTP 402 + payload
- Agent signs → PaymentRouter settles in USDC → service releases data
- The payment proof is hashed into DecisionRecord.dataSourceHash — paid data becomes audit evidence

## 3. Agent Engine Design (reusing HOODflow)

```
Perceive                 Decide                Record               Execute
─────────                ──────                ──────               ───────
robinhood-evm-mcp        LLM inference         keccak(JSON)         viem/web3.py
16 tools:                input: market +       DecisionRecorder     session-key
- live prices            positions + policy    .record()            signed trade
- liquidity depth        output: structured         ↓               Vault
- OHLCV                  decision JSON         after success:       .executeTrade()
x402 extras                     ↓                    ↓                    ↓
(CMC/research)           risk_manager.py       back-fill txHash    off-chain risk
                         hard checks                                 re-check
```

- **Perceive**: HOODflow MCP client reused as-is; x402 data augments inputs
- **Decide**: LLM output must pass JSON-schema validation (action/amount/asset/reason/sources)
- **Record**: credential goes on-chain before execution — decisions precede actions
- **Execute**: session key valid only for its vault; policy filters again at contract level

## 4. Data Flow & Trust Boundaries

| Boundary | Assumption | Guarantee |
|----------|-----------|-----------|
| Agent ↔ Vault | Agent untrusted | policy contract + session-key limits |
| Agent ↔ Data sources | Sources untrusted | cross-checks + dataSourceHash trail |
| User ↔ Vault | User fully in control | owner-only management + emergencyPause |
| Third party ↔ Audit | Trust nobody | on-chain self-verification |

## 5. Deployment Topology

| Network | Content | Purpose |
|---------|---------|---------|
| Arbitrum Sepolia | All 4 contracts + demo | baseline requirement |
| Robinhood Chain testnet | All 4 contracts + bStocks strategy | reserved slot + main demo |
| Arbitrum One | read-only DecisionRecorder mirror (optional) | bonus |
