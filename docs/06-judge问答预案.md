# Judge 问答预案 / Judge Q&A Prep

## Q1: 凭证先上链，交易不就慢了？套利窗口早没了。

**A**: 分两层。
1. L2 上确认极快（Arbitrum block ~250ms，Robinhood Chain 同级）；record → 确认 → bindTx 的延迟对中低频资管策略（我们的目标场景）完全可接受。
2. 高频场景是**批量凭证**：链下聚合决策流定期锚定 Merkle root（V2），单笔延迟归零，安全性靠事后可挑战。
3. 反问：如果快到不能留证据，那正是散户最该警惕的策略。

## Q2: 引擎可以先交易再补记录，链上根本拦不住。

**A**: 对，链是死的，交易和 record 是两笔独立交易，无法原子化证明"物理先后"。
我们的诚实声明 + 缓解：
- `verifyTrade` 检查的是 **recordedAt ≤ boundAt**（绑定时校验凭证已存在且未过期）
- 补记录 = 凭证的 `expiresAt` 必须在 trade timestamp 之前 → 事后补的凭证过不了期检查
- Vault 的 `proceedToTrade` 原子化了"record 确认 + 权限校验"，跳过 record 拿不到执行授权
- 引擎状态机 + 审计哈希链提供链下可追责证据（对簿公堂用）

## Q3: 为什么不直接用 ERC-8004 / 已有 Agent 标准？

**A**: 用了。AgentIdentityRegistry 是 ERC-8004 风格（identity/reputation/validation 三件套）。
我们做的是标准**没覆盖**的部分：交易-决策的可验证绑定。标准回答"这个 Agent 是谁"，我们回答"它为什么这么做、事前还是事后"。

## Q4: USDC 从哪来？Robinhood Chain 有原生 USDC 吗？

**A**: Robinhood Chain 是 EVM + Arbitrum Orbit 链，USDC 通过官方 bridge 或原生发行接入；
Vault 的 IERC20 地址是构造参数，部署时注入，不硬编码。测试期用 mock。

## Q5: session key 泄露，攻击者能在 revoke 前转走多少钱？

**A**: 双重上限：
1. 单笔 ≤ perTxMax（默认 $0.50）
2. 总额 ≤ budget（默认 $5/月）
3. 只能打白名单商户 —— 攻击者自己的地址收不到钱
4. revoke 秒级生效
**最坏损失 = min(budget, 白名单内可消耗额)**，且全部流向可追踪的白名单地址。

## Q6: 两个项目是不是一个项目拆两个凑数？

**A**: 共享设计哲学（凭证先行），解决不同问题：
- VeriAgent = **资管**（决策可信）→ Robinhood Chain
- VeriPay = **支付**（额度可信）→ Arbitrum One
合约无依赖、可独立审计、独立部署。x402 PaymentRouter 是 VeriAgent 的收款组件，
在 VeriPay 中独立演化为限额账户体系。

## Q7: 审计哈希链为什么不直接全上链？

**A**: 成本。每循环一次 record 已经上链（核心证据）；审计链是引擎侧的完整性补充
（谁在什么时候跑了什么），链上凭证是权威，本地链是廉价冗余。有争议时以链上为准。

## Q8: 演示是 mock 的，凭什么相信上线能跑？

**A**: 三层验证，逐层接近真实：
1. 102+ 单元测试（含攻击路径：重放/篡改/签名可锻/被盗 key/超支）
2. 链上/链下哈希奇偶测试 —— 编码层面和 EVM 逐字节一致
3. Deploy 脚本已在本地 anvil 全流程跑通；Sepolia 部署后 E2E 补上
mock 只替代了"价格源"，不替代任何安全逻辑。
