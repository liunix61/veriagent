<template>
  <div class="panel">
    <h2>Agent 市场 / Agent Market
      <span style="float: right" class="pill" :class="mode === 'chain' ? 'ok' : 'warn'">
        {{ mode === "chain" ? "ON-CHAIN" : "DEMO" }}
      </span>
    </h2>
    <p style="color: var(--dim); font-size: 12px; margin-top: 0">
      注册 Agent = ERC-8004 身份（owner/ENS/策略哈希）+ 链上信誉分。信誉分由已结算交易累积，
      被 Vault 拒绝则由 slasher 扣分 —— 用户按可验证历史选 Agent，不看广告。
    </p>
    <table>
      <thead>
        <tr>
          <th>id</th><th>ENS</th><th>owner</th><th>reputation</th>
          <th>strategy hash</th><th>status</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="a in agents" :key="a.agentId">
          <td>#{{ a.agentId }}</td>
          <td>{{ a.ensName || "—" }}</td>
          <td>{{ a.owner }}</td>
          <td>
            <span class="pill" :class="a.reputation >= 0 ? 'ok' : 'bad'">
              {{ a.reputation >= 0 ? "+" : "" }}{{ a.reputation }}
            </span>
          </td>
          <td><span class="hash">{{ a.metadataHash }}</span></td>
          <td>
            <span class="pill" :class="a.active ? 'ok' : 'warn'">
              {{ a.active ? "active" : "paused" }}
            </span>
          </td>
        </tr>
        <tr v-if="!agents.length">
          <td colspan="6" style="color: var(--dim)">no agents registered</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
const { getClient, cfg, connected } = useChain();

const mode = ref<"chain" | "demo">("demo");

interface AgentRow {
  agentId: string; ensName: string; owner: string;
  reputation: number; metadataHash: string; active: boolean;
}

const agents = ref<AgentRow[]>([]);

const short = (s: unknown) => String(s).slice(0, 10) + "…";

const DEMO_AGENTS: AgentRow[] = [
  { agentId: "1", ensName: "alpha-vault-agent.eth", owner: "0x7099…79C8",
    reputation: 128, metadataHash: "0xa1b2…c3d4", active: true },
  { agentId: "2", ensName: "arb-scanner.eth", owner: "0x3C44…93BC",
    reputation: 64, metadataHash: "0xe5f6…7788", active: true },
  { agentId: "3", ensName: "", owner: "0x90F7…6b0c",
    reputation: -8, metadataHash: "0x99aa…bbcc", active: false },
];

onMounted(async () => {
  const registry = (cfg.registryAddress as string) || "";
  if (!connected.value || !registry.startsWith("0x")) {
    agents.value = DEMO_AGENTS;
    return;
  }
  try {
    const c = getClient();
    const count = await c.readContract({
      address: registry as `0x${string}`,
      abi: registryAbi, functionName: "agentCount",
    });
    const rows: AgentRow[] = [];
    for (let i = 1; i <= Number(count); i++) {
      const r: any = await c.readContract({
        address: registry as `0x${string}`,
        abi: registryAbi, functionName: "getAgent", args: [BigInt(i)],
      });
      rows.push({
        agentId: String(i),
        ensName: r.ensName,
        owner: short(r.owner),
        reputation: Number(r.reputation),
        metadataHash: short(r.metadataHash),
        active: r.active,
      });
    }
    agents.value = rows;
    mode.value = "chain";
  } catch {
    agents.value = DEMO_AGENTS;
  }
});
</script>
