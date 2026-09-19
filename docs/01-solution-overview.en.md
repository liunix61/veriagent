# VeriAgent Solution Overview

> Arbitrum Open House Singapore Buildathon entry
> Built on the HOODflow engine base (/home/liunix/workspace/hoodflow)
> Created: 2026-09-13 | Event: Sep 14 – Oct 4, 2026

---

## 1. One-line Positioning

**VeriAgent = verifiable on-chain AI agent asset-management primitives**: every trading decision an AI agent makes becomes an on-chain auditable credential, and the agent autonomously manages tokenized assets (bStocks/RWA) inside a smart-contract-enforced vault.

## 2. The Real Problem

**Problem**: institutions and users don't trust AI agents with money — decisions are black boxes, permissions are uncontrollable, and there is no accountability when things go wrong.

Three pain points:
1. **Black-box trading**: why the agent bought/sold cannot be proven or audited after the fact
2. **Permission runaway**: an agent holding API keys or private keys has full mandate with no hard constraints
3. **No accountability**: agent services have no identity, no reputation, no on-chain track record

**VeriAgent's answer**:
- Every trade = on-chain decision record (reason hash + data-source hash) → **auditable**
- The agent only holds a session key; strategy rules are hard-enforced by the vault contract (whitelist / position caps / daily-loss circuit breaker) → **constrained**
- Every agent has ERC-8004-style identity + ENS name + on-chain reputation → **accountable**

## 3. Target Tracks & Winning Strategy

| Target | Path |
|--------|------|
| **Promising Products track** ($15K, explicitly AI agents + new financial primitives) | Primary: decision credentials + vault are genuinely new primitives |
| **Overall top 3** ($40/20/10K) | Native deployment on Robinhood Chain (1/3 reserved slot) + contract quality |
| **Grants** ($30K discretionary) | Complete product narrative + roadmap |
| **Founder House spot** | Top-3 Buildathon teams advance automatically |

Mapping to the 4 judging criteria:
1. Contract quality → full Foundry test suite + policy engine
2. PMF → riding the tokenized-stock/RWA wave (Robinhood Chain's core narrative)
3. Innovation → "decision credential" primitive doesn't exist elsewhere
4. Real problem → trust deficit in agent asset management

## 3.1 RWA Compliance Alignment: SEC Innovation Exemption (2026-09-17)

On 2026-09-17 the SEC issued a five-year Innovation Exemption creating the **TSV
(Tokenized Securities Venue)** category: real stocks tokenized 1:1 may trade on
permissioned AMM/liquidity pools without national-securities-exchange registration.
How each core condition maps to VeriAgent:

| SEC TSV condition | VeriAgent implementation |
|---|---|
| **No Synthetics**: tokens must carry dividend+voting rights identical to traditional shares | `TokenizedEquity.onchain_rights=True` flag; dividend passthrough audited twice — engine `run_dividend` -> `dividend_ack` credential + on-chain `notifyDividend`/`DividendReceived` event |
| **Concurrent halt**: tokenized trading stops when the primary market halts | `MarketSession.HALTED` hard gate -> `DecisionReject("MARKET_HALTED")` — no credential generated, executor unreachable |
| **After-hours liquidity management**: 24/7 venues see thin liquidity | `MarketSession.CLOSED` -> +3000bps risk premium + widened spread tolerance; decision reason records `session=CLOSED` on-chain |
| **Issuer rights + transparency**: trade data published within 10 minutes | Four commitment hashes per decision (action/reason/dataSource/model) + JSONL hash chain; `context_hash` embeds the session state |
| **Trading caps** (Tier 1: 75 symbols / 0.25% ADV) | Vault policy engine: `maxPositionPctBps` + `maxTradesPerDay` + `dailyLossLimitBps` |

bStocks on Robinhood Chain (an Arbitrum Orbit chain) are the flagship product of this
track — VeriAgent's engine and contracts are designed against the TSV compliance surface.

## 4. Product Shape

```
User deposits USDC/bStocks → picks a strategy agent → vault custody under policy constraints
                                                            │
Agent loop: perceive market → LLM decision → record credential on-chain → execute via session key
                                                            │
Any third party can verify via Explorer: full decision evidence for every trade
```

Three user-facing components:
1. **Vault**: user funds, strategy constraints guaranteed by contract
2. **Agent market**: registered agents with reputation scores and audit history
3. **Audit Explorer**: decision-credential search/verification UI

## 5. Tech Stack (summary; see 03-technical-framework)

| Layer | Choice |
|-------|--------|
| Contracts | Solidity + Foundry (Vault / IdentityRegistry / DecisionRecorder / PaymentRouter) |
| Chains | Arbitrum Sepolia (baseline) → Robinhood Chain (main theater, via robinhood-evm-mcp) |
| Agent engine | Python, reusing HOODflow engine (MCP client / market maker / arbitrage / risk) |
| LLM | Pluggable (Claude/GPT/Llama), structured JSON decisions |
| Data/payments | x402 micropayments for market data & analysis services |
| Frontend | Nuxt4 (vault management + Audit Explorer) |

## 6. HOODflow Assets Reused

| HOODflow asset | VeriAgent use |
|----------------|---------------|
| `engine/arbitrage_bot.py` | Core strategy loop |
| `engine/market_maker.py` | Market-making strategy (later) |
| `engine/risk_manager.py` | Off-chain risk checks (second line of defense) |
| robinhood-evm-mcp's 16 tools | Market data / trading / liquidity depth |
| `contracts/*.sol` | Strategy reference implementations |
| Python MCP-client pattern | Call existing tools, never rebuild the server |

## 7. Three-Week Milestones (Sep 14 – Oct 4)

| Week | Deliverables |
|------|--------------|
| W1 (9/14–9/20) | Contracts: IdentityRegistry + DecisionRecorder + Vault (policy engine) + Foundry tests; deploy to Arbitrum Sepolia |
| W2 (9/21–9/27) | Agent engine upgrade: HOODflow → "decide → credential → execute" loop; x402 integration; deploy to Robinhood Chain testnet |
| W3 (9/28–10/4) | Explorer frontend + end-to-end demo + video + submission (repo/docs/pitch) |

**Demo script (submission video)**:
1. User creates a vault with constraints (NVDA/TSLA whitelist, ≤10% per position, ≤2% daily loss)
2. Agent runs one autonomous trade loop; decision credential appears on-chain
3. Explorer verifies trade ↔ credential ↔ agent identity end to end
4. Forced policy violation → vault contract rejects (constraints proven)

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Robinhood Chain mainnet unusable for the event | Its testnet suffices; rules only require an Arbitrum-chain deployment |
| x402 integration cost | W2 ships a mock facilitator first with spec-aligned interfaces |
| Unstable LLM decisions | JSON-schema validation + off-chain risk fallback (HOLD) |
| Time pressure | Contracts first (highest judging weight), minimal frontend |
