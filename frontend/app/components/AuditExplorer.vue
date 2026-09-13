<template>
  <div class="panel">
    <h2>审计浏览器 / Audit Explorer
      <span style="float: right" class="pill" :class="mode === 'chain' ? 'ok' : 'warn'">
        {{ mode === "chain" ? "ON-CHAIN" : "DEMO" }}
      </span>
    </h2>
    <p style="color: var(--dim); font-size: 12px; margin-top: 0">
      每笔交易先有凭证后有成交 — record 区块 ≤ bind 区块是硬性可验证顺序，不是口头承诺。
      合约只存四哈希（action/reason/dataSource/model），全文在链下 bundle，重算哈希即可对账。
    </p>
    <table>
      <thead>
        <tr>
          <th>id</th><th>agent</th><th>four hashes</th>
          <th>record → bind</th><th>order</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.decisionId">
          <td>#{{ row.decisionId }}</td>
          <td>{{ row.agentId }}</td>
          <td style="font-size: 11px">
            <span class="hash">act {{ row.actionHash }}</span><br />
            <span class="hash">rea {{ row.reasonHash }}</span><br />
            <span class="hash">src {{ row.dataSourceHash }}</span><br />
            <span class="hash">mod {{ row.modelHash }}</span>
          </td>
          <td style="font-size: 11px">
            <span class="hash">blk {{ row.recordBlock }}</span>
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
  decisionId: string; agentId: string;
  actionHash: string; reasonHash: string; dataSourceHash: string; modelHash: string;
  recordBlock: string; boundTx: string | null; orderOk: boolean;
}

const rows = ref<Row[]>([]);

const h = (s: unknown) => String(s).slice(0, 10) + "…";

const DEMO_ROWS: Row[] = [
  { decisionId: "1", agentId: "7",
    actionHash: h("0xdd53723a2398aff8"), reasonHash: h("0x3c4dc0f96c0af442"),
    dataSourceHash: h("0xe47fff08fcc1b5db"), modelHash: h("0x36e92fb341dbfc84"),
    recordBlock: "1201", boundTx: "0x9ea3…7cb7", orderOk: true },
  { decisionId: "2", agentId: "7",
    actionHash: h("0x11aa22bb33cc44dd"), reasonHash: h("0x55ee66ff77889900"),
    dataSourceHash: h("0xabcdef1234567890"), modelHash: h("0x36e92fb341dbfc84"),
    recordBlock: "1203", boundTx: "0xda3f…f14a", orderOk: true },
];

onMounted(async () => {
  const recorder = (cfg.recorderAddress as string) || "";
  if (!connected.value || !recorder.startsWith("0x")) {
    rows.value = DEMO_ROWS;
    return;
  }
  try {
    const c = getClient();
    const recorded = await c.getContractEvents({
      address: recorder as `0x${string}`,
      abi: recorderAbi, eventName: "DecisionRecorded",
      fromBlock: 0n, toBlock: "latest",
    });
    const bound = await c.getContractEvents({
      address: recorder as `0x${string}`,
      abi: recorderAbi, eventName: "DecisionBound",
      fromBlock: 0n, toBlock: "latest",
    });
    const boundById = new Map(bound.map((b: any) => [String(b.args.decisionId), b]));
    rows.value = recorded.map((l: any) => {
      const b: any = boundById.get(String(l.args.decisionId));
      return {
        decisionId: String(l.args.decisionId),
        agentId: String(l.args.agentId),
        actionHash: h(l.args.actionHash),
        reasonHash: h(l.args.reasonHash),
        dataSourceHash: h(l.args.dataSourceHash),
        modelHash: h(l.args.modelHash),
        recordBlock: String(l.blockNumber),
        boundTx: b ? h(b.args.txHash) : null,
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
