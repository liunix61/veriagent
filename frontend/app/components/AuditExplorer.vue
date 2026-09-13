<template>
  <div class="panel">
    <h2>审计浏览器 / Audit Explorer
      <span style="float: right" class="pill" :class="mode === 'chain' ? 'ok' : 'warn'">
        {{ mode === "chain" ? "ON-CHAIN" : "DEMO" }}
      </span>
    </h2>
    <p style="color: var(--dim); font-size: 12px; margin-top: 0">
      每笔交易先有凭证后有成交 — recordedAt ≤ boundAt 是硬性可验证顺序，不是口头承诺。
    </p>
    <table>
      <thead>
        <tr>
          <th>credential</th><th>decision</th><th>amount</th>
          <th>recorded → bound</th><th>order</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.credentialId">
          <td class="hash">{{ row.credentialId }}</td>
          <td>{{ row.action }} {{ row.asset }} <span style="color: var(--dim)">@{{ row.venue }}</span></td>
          <td>{{ row.amount }}</td>
          <td style="font-size: 11px">
            <span class="hash">{{ row.recordedAt }}</span>
            <template v-if="row.boundTx"> → <span class="hash">{{ row.boundTx }}</span></template>
            <template v-else> → <span style="color: var(--dim)">pending</span></template>
          </td>
          <td>
            <span v-if="row.boundTx" class="pill" :class="row.orderOk ? 'ok' : 'bad'">
              {{ row.orderOk ? "✓ valid" : "✗ VIOLATION" }}
            </span>
            <span v-else class="pill warn">recorded</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="5" style="color: var(--dim)">no credentials</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
const { getClient, cfg, connected } = useChain();

const mode = ref<"chain" | "demo">("demo");

interface Row {
  credentialId: string; action: string; asset: string; venue: string;
  amount: string; recordedAt: string; boundTx: string | null; orderOk: boolean;
}

const rows = ref<Row[]>([]);

const DEMO_ROWS: Row[] = [
  { credentialId: "0xc870…f34", action: "buy", asset: "WETH", venue: "uniswap-v3",
    amount: "0.01", recordedAt: "blk 1201", boundTx: "0x9ea3…7cb7", orderOk: true },
  { credentialId: "0xfbd9…a40", action: "buy", asset: "WETH", venue: "uniswap-v3",
    amount: "0.01", recordedAt: "blk 1203", boundTx: "0xda3f…f14a", orderOk: true },
  { credentialId: "0x4be4…b196", action: "sell", asset: "ARB", venue: "uniswap-v3",
    amount: "12.5", recordedAt: "blk 1207", boundTx: "0x5596…b881", orderOk: true },
];

onMounted(async () => {
  const recorder = (cfg.recorderAddress as string) || "";
  if (!connected.value || !recorder.startsWith("0x")) {
    rows.value = DEMO_ROWS;
    return;
  }
  try {
    const c = getClient();
    const logs = await c.getContractEvents({
      address: recorder as `0x${string}`,
      abi: recorderAbi, eventName: "DecisionRecorded",
      fromBlock: 0n, toBlock: "latest",
    });
    const bindings = await c.getContractEvents({
      address: recorder as `0x${string}`,
      abi: recorderAbi, eventName: "TradeBound",
      fromBlock: 0n, toBlock: "latest",
    });
    const bound = new Map(bindings.map((b: any) => [b.args.credentialId, b]));
    rows.value = logs.map((l: any) => {
      const b: any = bound.get(l.args.credentialId);
      return {
        credentialId: String(l.args.credentialId).slice(0, 10) + "…",
        action: l.args.action, asset: l.args.asset, venue: l.args.venue,
        amount: String(l.args.amount),
        recordedAt: `blk ${l.blockNumber}`,
        boundTx: b ? String(b.args.txHash).slice(0, 10) + "…" : null,
        // order validity: binding must be at/after the recording block
        orderOk: b ? b.blockNumber >= l.blockNumber : false,
      };
    });
    mode.value = "chain";
  } catch {
    rows.value = DEMO_ROWS;
  }
});
</script>
