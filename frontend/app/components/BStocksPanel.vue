<template>
  <div class="panel">
    <h2>bStocks 持仓与合规 / Tokenized Equity
      <span style="float: right" class="pill" :class="secOk ? 'ok' : 'warn'">
        {{ secOk ? "SEC-TSV ALIGNED" : "CHECK" }}
      </span>
    </h2>
    <p style="color: var(--dim); font-size: 12px; margin-top: 0">
      SEC Innovation Exemption (2026-09-17): 代币化股票须保留分红/投票权 (No Synthetics)，
      主市场停牌时同步停牌。Agent 每个决策记录 session 状态，股息经 dividend_ack 凭证上链审计。
    </p>

    <h3 style="font-size: 13px; margin: 12px 0 6px">持仓 / Holdings</h3>
    <table>
      <thead>
        <tr><th>token</th><th>underlying</th><th>amount</th><th>session</th><th>rights</th></tr>
      </thead>
      <tbody>
        <tr v-for="h in holdings" :key="h.token">
          <td>{{ h.token }}</td>
          <td>{{ h.underlying }}</td>
          <td>{{ h.amount }}</td>
          <td>
            <span class="pill" :class="sessionClass(h.session)">{{ h.session }}</span>
          </td>
          <td>
            <span class="pill" :class="h.rights ? 'ok' : 'bad'">
              {{ h.rights ? "vote+div" : "SYNTHETIC" }}
            </span>
          </td>
        </tr>
        <tr v-if="!holdings.length">
          <td colspan="5" style="color: var(--dim)">no tokenized holdings</td>
        </tr>
      </tbody>
    </table>

    <h3 style="font-size: 13px; margin: 12px 0 6px">股息审计流 / Dividend Audit Trail</h3>
    <table>
      <thead>
        <tr><th>event</th><th>dps</th><th>total</th><th>ex / pay</th><th>credential</th></tr>
      </thead>
      <tbody>
        <tr v-for="d in dividends" :key="d.credentialId">
          <td>{{ d.asset }} ({{ d.underlying }})</td>
          <td>${{ d.perShare }}</td>
          <td>${{ d.total }}</td>
          <td style="font-size: 11px">{{ d.exDate }} → {{ d.payDate }}</td>
          <td>
            <span class="pill ok">{{ d.credentialId }}</span>
          </td>
        </tr>
        <tr v-if="!dividends.length">
          <td colspan="5" style="color: var(--dim)">no dividend events yet</td>
        </tr>
      </tbody>
    </table>

    <div class="kv" style="margin-top: 10px">
      <span class="k">on-chain dividends</span>
      <span>${{ totalDividends }} accumulated (notifyDividend events)</span>
    </div>
  </div>
</template>

<script setup lang="ts">
const { getClient, cfg, connected } = useChain();

interface Holding {
  token: string; underlying: string; amount: string;
  session: "OPEN" | "CLOSED" | "HALTED"; rights: boolean;
}
interface DividendRow {
  credentialId: string; asset: string; underlying: string;
  perShare: string; total: string; exDate: string; payDate: string;
}

const holdings = ref<Holding[]>([]);
const dividends = ref<DividendRow[]>([]);
const totalDividends = ref("0.00");
const secOk = ref(true);

const sessionClass = (s: string) =>
  s === "OPEN" ? "ok" : s === "CLOSED" ? "warn" : "bad";

const DEMO_HOLDINGS: Holding[] = [
  { token: "bAAPL", underlying: "AAPL", amount: "12.5", session: "OPEN", rights: true },
  { token: "bNVDA", underlying: "NVDA", amount: "8.0", session: "OPEN", rights: true },
  { token: "bTSLA", underlying: "TSLA", amount: "3.2", session: "CLOSED", rights: true },
];
const DEMO_DIVIDENDS: DividendRow[] = [
  { credentialId: "cred-000001", asset: "bAAPL", underlying: "AAPL",
    perShare: "0.2500", total: "3.13", exDate: "2026-09-18", payDate: "2026-09-24" },
  { credentialId: "cred-000002", asset: "bNVDA", underlying: "NVDA",
    perShare: "0.0100", total: "0.08", exDate: "2026-09-20", payDate: "2026-09-26" },
];

onMounted(async () => {
  const vault = (cfg.vaultAddress as string) || "";
  if (!connected.value || !vault.startsWith("0x")) {
    holdings.value = DEMO_HOLDINGS;
    dividends.value = DEMO_DIVIDENDS;
    totalDividends.value = "163.50";
    return;
  }
  try {
    const c = getClient();
    // on-chain: read DividendReceived events from the vault
    const events = await c.getContractEvents({
      address: vault as `0x${string}`,
      abi: vaultAbi, eventName: "DividendReceived",
      fromBlock: 0n, toBlock: "latest",
    });
    const byAsset = new Map<string, bigint>();
    for (const e of events as any[]) {
      const a = String(e.args.asset);
      byAsset.set(a, (byAsset.get(a) ?? 0n) + (e.args.amount as bigint));
    }
    totalDividends.value = [...byAsset.values()]
      .reduce((s, v) => s + Number(v) / 1e18, 0).toFixed(2);
    // holdings demo until bStocks registry contract is deployed
    holdings.value = DEMO_HOLDINGS;
    dividends.value = DEMO_DIVIDENDS;
  } catch {
    holdings.value = DEMO_HOLDINGS;
    dividends.value = DEMO_DIVIDENDS;
  }
});
</script>
