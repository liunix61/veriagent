# VeriAgent Technical Framework

> Created: 2026-09-13 | Related: 01-solution-overview / 02-system-architecture / 04-core-flows

---

## 1. Repository Structure

```
veriagent/
├── contracts/                  # Foundry project
│   ├── src/
│   │   ├── AgentIdentityRegistry.sol
│   │   ├── VeriAgentVault.sol
│   │   ├── DecisionRecorder.sol
│   │   ├── PaymentRouter.sol
│   │   └── interfaces/
│   ├── test/                   # Foundry unit + fuzz tests
│   └── script/Deploy.s.sol
├── engine/                     # Python agent engine (from HOODflow)
│   ├── agent_loop.py           # main loop: perceive→decide→record→execute
│   ├── perceive.py             # robinhood-evm-mcp client (reused)
│   ├── decide.py               # LLM decision + JSON-schema validation
│   ├── record.py               # credential construction & on-chain record
│   ├── execute.py              # session-key trade execution
│   ├── x402_client.py          # x402 paid data purchase
│   ├── risk_manager.py         # off-chain risk (reused from HOODflow)
│   └── config.yaml
├── frontend/                   # Nuxt4
│   ├── pages/ (vault/ agent/ explorer/)
│   └── lib/contracts.ts        # viem ABI wrappers
└── docs/                       # this directory (bilingual)
```

## 2. Tech Stack Detail

| Component | Choice | Notes |
|-----------|--------|-------|
| Contract language | Solidity | ^0.8.24 (custom errors, checked math) |
| Contract framework | Foundry | forge test / fuzz / gas snapshot |
| Contract security | OpenZeppelin | Ownable/ReentrancyGuard/Pausable, used minimally |
| L2 interaction | viem (TS) / web3.py (Python) | frontend / engine respectively |
| Agent framework | plain Python loop (not Strands — avoids AWS-event overlap) | modular, HOODflow-style |
| MCP | robinhood-evm-mcp | 16 tools: prices/trading/liquidity/cross-chain |
| LLM | pluggable: Claude / GPT / Llama (LangChain optional) | prompts versioned, hash on-chain |
| x402 | lightweight self-hosted facilitator, spec-aligned | USDC on Arbitrum/Base |
| Storage | IPFS (full decision JSON) | hash on-chain, full text retrievable |
| Frontend | Nuxt4 + viem + Tailwind | single page, three views |
| CI | GitHub Actions | forge test + pytest + build |

## 3. Contract Interfaces (key signatures)

```solidity
// AgentIdentityRegistry.sol
function registerAgent(bytes32 metadataHash, string calldata ensName) external returns (uint256 agentId);
function rotateSessionKey(uint256 agentId, address newKey) external;
function getAgent(uint256 agentId) external view returns (AgentRecord memory);

// VeriAgentVault.sol
function initialize(uint256 agentId, VaultPolicy calldata policy) external;
function deposit(address asset, uint256 amount) external;
function executeTrade(Trade calldata t) external;   // onlySessionKey
function checkPolicy(Trade calldata t) public view returns (bool ok, bytes32 reason);
function updatePolicy(VaultPolicy calldata p) external; // onlyOwner + timelock
function emergencyPause() external;                  // onlyOwner

// DecisionRecorder.sol
function record(uint256 agentId, address vault, bytes32 actionHash,
                bytes32 reasonHash, bytes32 dataSourceHash, bytes32 modelHash)
        external returns (uint256 decisionId);
function bindTx(uint256 decisionId, bytes32 txHash) external;
function verifyTrade(bytes32 txHash) external view returns (DecisionRecord memory);

// PaymentRouter.sol
function settle(bytes32 x402Payload, bytes calldata signature) external returns (bool);
```

## 4. Policy Engine Rules (vault core)

Checked in order; any failure rejects the trade (with a reason so the agent can self-correct):

1. **Whitelist**: `trade.asset ∈ policy.assetWhitelist`
2. **Position cap**: `postTradeValue(asset) / totalValue ≤ maxPositionPct`
3. **Daily-loss breaker**: `dailyRealizedLoss + unrealizedDrawdown ≤ dailyLossLimitBps`
4. **Cooldown**: `block.timestamp - lastTradeAt ≥ tradeCooldown`
5. **Frequency**: `tradesToday < maxTradesPerDay`
6. **Pause**: `!paused`

## 5. Agent Decision Schema (LLM output constraints)

```json
{
  "action": "BUY | SELL | HOLD",
  "asset": "0x...",            // must be whitelisted
  "amountPct": 5,              // % of total assets, ≤ maxPositionPct
  "reason": "decision rationale, ≤3 sentences",
  "dataSources": ["cmc:NVDA", "mcp:depth:NVDA/USDC"],
  "confidence": 0.72
}
```

- Pydantic validation; invalid output retried (max 2) → HOLD fallback
- `reason` + `dataSources` + prompt version → keccak → DecisionRecorder

## 6. x402 Integration

```
engine → GET https://data.provider/api/v1/sig?symbol=NVDA
      ← 402 Payment Required { x402Payload }
engine → POST /pay { signedPayload }   // PaymentRouter or facilitator
      ← 200 { data, paymentProof }
data + paymentProof → folded into dataSourceHash
```

- W2 ships a local mock facilitator first, interfaces strictly x402-spec-aligned
- Priority target: CMC Agent Hub (the b402 call pattern validated in the Binance ecosystem)

## 7. Test Strategy

| Layer | Tool | Coverage goal |
|-------|------|---------------|
| Contract unit | forge test | 100% function coverage + every policy rejection path |
| Contract fuzz | forge fuzz | policy boundary values (bps/time/amount) |
| Contract attacks | forge + hand-written PoCs | reentrancy / permission bypass / session-key abuse |
| Engine | pytest | decision schema / retry / risk fallback |
| E2E | anvil + scripts | deposit→decide→credential→trade→verify |

## 8. Gas Budget (critical path)

| Operation | Est. gas | Notes |
|-----------|---------|-------|
| record() | ~80k | 4×bytes32 + event |
| executeTrade() | ~120k | policy checks + transfer |
| deposit() | ~70k | ERC20 transferFrom |
| bindTx() | ~45k | single storage write |

On L2 the full loop costs <$0.05 — viable for high-frequency small decisions.
