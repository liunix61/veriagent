<template>
  <div class="panel">
    <h2>Vault 状态 / Vault State</h2>
    <div class="kv"><span class="k">agent</span><span>{{ pos.agent }}</span></div>
    <div class="kv"><span class="k">state</span>
      <span class="pill" :class="pos.state === 0 ? 'ok' : 'bad'">
        {{ ["ACTIVE", "REVOKED"][pos.state] ?? "?" }}
      </span>
    </div>
    <div class="kv"><span class="k">asset type</span>
      <span>{{ ["ERC20", "ERC721"][pos.assetType] ?? "?" }}</span></div>
    <div class="kv"><span class="k">total value</span><span>${{ pos.totalValue }}</span></div>
    <div class="kv"><span class="k">policy</span>
      <span class="pill" :class="policy.paused ? 'warn' : 'ok'">
        {{ policy.paused ? "PAUSED" : "ENFORCING" }}
      </span>
    </div>
    <div class="kv"><span class="k">max position</span><span>${{ policy.maxPosition }}</span></div>
    <div class="kv"><span class="k">daily loss limit</span><span>${{ policy.maxDailyLoss }}</span></div>
    <div class="kv"><span class="k">cooldown</span><span>{{ policy.cooldown }}s</span></div>
    <div class="kv"><span class="k">min interval</span><span>{{ policy.minInterval }}s</span></div>
  </div>
</template>

<script setup lang="ts">
const { getClient, cfg, connected } = useChain();

const pos = reactive({ agent: "0x0000…0000", state: 0, assetType: 0, totalValue: "0" });
const policy = reactive({
  maxPosition: "—", maxDailyLoss: "—", cooldown: "—", minInterval: "—", paused: false,
});

const DEMO = {
  pos: { agent: "0x7099…79C8", state: 0, assetType: 0, totalValue: "25,000" },
  policy: { maxPosition: "10,000", maxDailyLoss: "2,000", cooldown: "60", minInterval: "30", paused: false },
};

onMounted(async () => {
  if (!connected.value || !(cfg.vaultAddress as string)?.startsWith("0x")) {
    Object.assign(pos, DEMO.pos); Object.assign(policy, DEMO.policy);
    return;
  }
  try {
    const c = getClient();
    const [agent, state, assetType] = await c.readContract({
      address: cfg.vaultAddress as `0x${string}`,
      abi: vaultAbi, functionName: "positionAgent",
    });
    pos.agent = agent.slice(0, 6) + "…" + agent.slice(-4);
    pos.state = state; pos.assetType = assetType;
  } catch {
    Object.assign(pos, DEMO.pos); Object.assign(policy, DEMO.policy);
  }
});
</script>
