<template>
  <div class="panel">
    <h2>合约地图 / Contracts</h2>
    <div class="kv"><span class="k">DecisionRecorder</span>
      <span class="hash">{{ short(cfg.recorderAddress) }}</span></div>
    <div class="kv"><span class="k">IdentityRegistry</span>
      <span class="hash">{{ short(cfg.registryAddress) }}</span></div>
    <div class="kv"><span class="k">VeriAgentVault</span>
      <span class="hash">{{ short(cfg.vaultAddress) }}</span></div>
    <div class="kv"><span class="k">rpc</span><span>{{ cfg.rpcUrl }}</span></div>
    <p style="color: var(--dim); font-size: 11px; margin-bottom: 0">
      配置 NUXT_PUBLIC_* 环境变量接入真实链；未配置时展示演示数据。
    </p>
  </div>
</template>

<script setup lang="ts">
const { cfg } = useChain();
const short = (a: unknown) =>
  typeof a === "string" && a.startsWith("0x")
    ? a.slice(0, 8) + "…" + a.slice(-6) : "—";
</script>
