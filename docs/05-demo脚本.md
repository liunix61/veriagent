# Demo 脚本（3 分钟）/ Demo Script (3 min)

> 中英双语，录屏时中文口播 + 英文字幕；或直接英文版投稿。

## 0:00–0:20 — Hook（痛点）

**中文**：AI Agent 帮你交易，出事了谁证明它"当时决策是合理的"？
Agent 说是策略的锅，策略说是 Agent 失控。我们把答案写进链上：**先有凭证，后有钱**。

**EN**: Your AI agent trades your funds. When things go wrong, who proves the
decision was reasonable *before* the trade? We put the answer on-chain:
**evidence before money**.

## 0:20–1:00 — 机制（合约）

屏幕：`DecisionRecorder.sol` 代码 + 状态图

1. `record()` — 决策要素完整哈希上链（时机/方向/数量/滑点上限/风险分）
2. 确认后才 `bindTx()` — 交易哈希绑回凭证
3. `verifyTrade(decisionHash, txHash)` — 任何人一步验证顺序

强调：**引擎侧 Python 状态机同样强制这个顺序** —— RECORDED 之前调执行直接抛异常。
链上/链下承诺哈希逐字节一致（abi.encode 奇偶测试双端断言）。

## 1:00–1:40 — Demo（终端实拍）

```bash
python3 main.py --loops 5
```
输出 5 个循环：VERIFIED / cred / tx / bound=True
```
audit trail: 5 credentials, hash-chain valid = True
```
篡改演示：改审计文件一个字节 → `verify_chain()` 立即 False。

## 1:40–2:20 — 前端 + Policy

屏幕：Nuxt4 控制台
- Audit Explorer：每行显示 `recorded → bound` + ✓ valid 顺序标记
- Vault 面板：6 规则 policy（白名单/仓位/日亏损熔断/冷却/频率/暂停）+ 24h timelock

## 2:20–3:00 — 收尾 + 赛道

- 102+ 测试全绿，抓出 7 个真合约 bug（timelock 假生效、签名可锻性…）
- 双项目：VeriAgent @ Robinhood Chain（资管原语）+ VeriPay @ Arbitrum One（x402 限额支付）
- V2：FollowerVault 跟单钱包 —— Promising Products "Requesting funding" 的答案
- 结束语：**Trust the math, not the operator.**

## 录制清单

- [ ] 终端：`python3 main.py --loops 5`（先清 audit/ 目录）
- [ ] 终端：篡改演示（sed 改一个字节 → verify False）
- [ ] 浏览器：Nuxt4 控制台（demo 模式即可，右上角 DEMO 徽章诚实标注）
- [ ] 代码：DecisionRecorder.sol record/bindTx/verifyTrade 三函数滚动
- [ ] forge test 全绿截图
