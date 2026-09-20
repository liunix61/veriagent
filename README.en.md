# VeriAgent — Verifiable On-Chain Primitives for Agent Asset Management

> Arbitrum Open House Singapore Buildathon 2026 · Robinhood Chain

**In one line**: before an AI agent trades your funds, it must leave an
undeniable decision credential on-chain; the order of credential-vs-trade is
independently verifiable by anyone.

## The problem, stated plainly

The agent blames the strategy; the strategy blames the agent. Who can prove a
reasonable decision existed *before* the trade?

VeriAgent's answer: **evidence before money**.

1. Agent decides → `DecisionRecorder.record()` (full decision commitment on-chain)
2. Only then may it trade → `bindTx()` links the execution tx back to the credential
3. Anyone calls `verifyTrade(decisionHash, txHash)` — one call verifies order + integrity

## Architecture

```
Engine (Python)                          On-chain (Solidity)
┌─────────────────────┐               ┌──────────────────────┐
│ perception → strategy│   record()   │ DecisionRecorder     │
│        ↓             │ ───────────▶│  (two-phase credential)│
│   LocalRecorder      │   bindTx()  │ AgentIdentityRegistry│
│  (hash-chained audit)│ ───────────▶│  (ERC-8004 style)     │
│        ↓             │              │ VeriAgentVault        │
│     executor         │              │  (6-rule policy engine)│
└─────────────────────┘               │ PaymentRouter (x402) │
        ↕ byte-identical hashes        └──────────────────────┘
engine/abi_encode.py  ⇄  abi.encode()        Nuxt4 Console (Audit Explorer)
```

**On-chain/off-chain hash parity**: `engine/abi_encode.py` produces encodings
byte-identical to Solidity `abi.encode`. One fixed test vector is asserted in
BOTH pytest and forge test (`HashParity.t.sol` / `test_abi_parity.py`) — audit
reconciliation requires zero trust in the engine operator.

## Quickstart

```bash
# contract tests (84)
cd contracts && forge test

# engine tests (59) + one-command demo
cd .. && python3 -m pytest tests/ -q
python3 main.py --loops 5        # verifiable audit trail output

# console
cd frontend && npm install && npm run dev
```

## Security model

- **Session-key rotation**: a stolen key dies instantly; history stays verifiable
- **On-chain policy engine**: whitelist / position cap / daily-loss circuit
  breaker / cooldown / rate limit / pause
- **24h timelock**: policy changes sit in a pending slot until activated
- **Engine state machine**: any execution before `RECORDED` raises `OrderViolation`
- **Hash-chained audit log**: one altered byte fails verification (tested)

## RWA compliance + AI decision-model audit layer

- **SEC TSV alignment** (Innovation Exemption 2026-09-17): `MarketSession.HALTED`
  hard-rejects trades (concurrent-halt condition); `CLOSED` trades carry a
  +3000bps risk premium recorded on-chain; dividends audited twice — engine
  `dividend_ack` credential + on-chain `notifyDividend` event (No Synthetics)
- **Dual-track AI decision-model auditing**: Jev (TypeSafe System One) and
  NanoJev (open 0.6B replica, liunix61/NanoJev) run the same four-hash
  credential pipeline — `model_id`/`modelHash` distinguish the model lineage
  on-chain; compliance gates fire BEFORE the model (HALTED rejects regardless
  of model confidence)
- **bStocks console**: frontend BStocksPanel shows per-holding session pills,
  rights passthrough flags, and the dividend audit trail (Robinhood Chain
  narrative made visible)

## Tests & real bugs caught

143 tests (84 forge + 59 pytest). Real contract bugs found and fixed
during development: fake timelock (direct overwrite), missing day-snapshot
sentinel, first-trade cooldown kill, position-cap denominator error, EIP-712
signature malleability exposure.

## Docs

`docs/` — bilingual (ZH/EN) four-piece set: master plan / architecture /
tech stack / core flows.

## License

MIT
