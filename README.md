# VeriAgent — 可验证链上 Agent 资管原语

> Arbitrum Open House Singapore Buildathon 2026 · Robinhood Chain

**一句话**：AI Agent 自主交易你的资金之前，先在链上留下不可抵赖的决策凭证；交易与凭证的顺序可被任何人独立验证。

## 为什么需要它

Judge 视角的直白问题：Agent 跑路了说是策略失误，策略方跑路了说是 Agent 失控——谁来证明交易执行前存在过一个合理决策？

VeriAgent 的答案：**凭证先于交易**（evidence before money）。

1. Agent 决策 → `DecisionRecorder.record()` 上链（含决策全部要素哈希）
2. 确认后才允许交易 → `bindTx()` 把交易哈希绑回凭证
3. 任何人 `verifyTrade(decisionHash, txHash)` 一步验证顺序与完整性

## 架构

```
引擎 (Python)                          链上 (Solidity)
┌─────────────────────┐               ┌──────────────────────┐
│ perception → strategy│   record()   │ DecisionRecorder     │
│        ↓             │ ───────────▶│  (两阶段凭证)         │
│   LocalRecorder      │   bindTx()  │ AgentIdentityRegistry│
│  (哈希链审计)         │ ───────────▶│  (ERC-8004 风格)      │
│        ↓             │              │ VeriAgentVault       │
│     executor         │              │  (policy 引擎 6 规则) │
└─────────────────────┘               │ PaymentRouter (x402) │
        ↕ 哈希逐字节一致                └──────────────────────┘
engine/abi_encode.py  ⇄  abi.encode()        Nuxt4 Console (Audit Explorer)
```

**链上/链下同一承诺哈希**：`engine/abi_encode.py` 与 Solidity `abi.encode` 产出逐字节一致的编码，同一测试向量在 pytest 与 forge 两端断言（`HashParity.t.sol` / `test_abi_parity.py`）。审计对账无需信任引擎运营方。

## 快速开始

```bash
# 合约测试 (77 tests)
cd contracts && forge test

# 引擎测试 (16 tests) + 一键 demo
cd .. && python3 -m pytest tests/ -q
python3 main.py --loops 5        # 输出可验证审计轨迹

# 前端控制台
cd frontend && npm install && npm run dev
```

## 安全模型

- **Session key 轮换**：被盗 key 即时失效，历史交易仍可验证
- **Policy 引擎**（链上强制）：白名单 / 仓位上限 / 日亏损熔断 / 冷却期 / 频率限制 / 暂停
- **24h timelock**：policy 变更走 pending 槽位，到期才生效
- **引擎侧状态机**：`RECORDED` 之前任何执行调用抛 `OrderViolation`
- **审计哈希链**：JSONL 链式哈希，篡改一字节即验证失败（有测试证明）

## 测试与真 bug

103 个测试（77 forge + 16 pytest + 10 其它）。开发中抓出并修复的真合约 bug：
timelock 假生效（直接覆写）、日快照 sentinel 缺失、首笔冷却误杀、
position cap 分母错误（漏计本次买入）、EIP-712 签名可锻性风险。

## 文档

`docs/` 中英双语四件套：总体方案 / 系统架构 / 技术框架 / 核心流程。

## License

MIT
