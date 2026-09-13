<template>
  <div class="shell">
    <header>
      <div class="brand">
        <span class="logo">◈</span> VeriAgent
        <span class="tag">verifiable agent vault</span>
      </div>
      <nav>
        <NuxtLink to="/">Console</NuxtLink>
      </nav>
      <div class="net" :class="{ ok: connected }">
        {{ connected ? chainLabel : "offline · demo data" }}
      </div>
    </header>
    <main>
      <NuxtPage />
    </main>
    <footer>
      decision → credential → execution — evidence before money ·
      <a href="https://github.com/liunix61/veriagent" target="_blank">github</a>
    </footer>
  </div>
</template>

<script setup lang="ts">
const { connected, chainLabel } = useChain();
</script>

<style>
:root {
  --bg: #0b0e14; --panel: #12161f; --line: #232a38;
  --fg: #d7dde8; --dim: #7a8699; --acc: #4fd1c5; --warn: #f6ad55; --bad: #fc8181;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.5 ui-monospace, "JetBrains Mono", Menlo, monospace; }
a { color: var(--acc); text-decoration: none; }
.shell { max-width: 1100px; margin: 0 auto; padding: 0 20px; }
header { display: flex; align-items: center; gap: 24px; padding: 18px 0;
  border-bottom: 1px solid var(--line); }
.brand { font-size: 18px; font-weight: 700; }
.logo { color: var(--acc); }
.tag { color: var(--dim); font-size: 12px; font-weight: 400; margin-left: 8px; }
nav { display: flex; gap: 16px; margin-left: auto; }
.net { font-size: 12px; color: var(--dim); }
.net.ok { color: var(--acc); }
main { padding: 24px 0; }
footer { color: var(--dim); font-size: 12px; padding: 20px 0;
  border-top: 1px solid var(--line); }
.grid { display: grid; grid-template-columns: 340px 1fr; gap: 16px; }
@media (max-width: 860px) { .grid { grid-template-columns: 1fr; } }
.panel { background: var(--panel); border: 1px solid var(--line);
  border-radius: 10px; padding: 16px; }
.panel h2 { margin: 0 0 12px; font-size: 13px; color: var(--dim);
  text-transform: uppercase; letter-spacing: 1px; }
.kv { display: flex; justify-content: space-between; padding: 4px 0;
  border-bottom: 1px dashed var(--line); font-size: 13px; }
.kv:last-child { border-bottom: none; }
.kv .k { color: var(--dim); }
.mono { font-family: inherit; }
.pill { display: inline-block; padding: 1px 8px; border-radius: 99px;
  font-size: 11px; border: 1px solid var(--line); }
.pill.ok { color: var(--acc); border-color: var(--acc); }
.pill.warn { color: var(--warn); border-color: var(--warn); }
.pill.bad { color: var(--bad); border-color: var(--bad); }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { text-align: left; color: var(--dim); font-weight: 500;
  padding: 6px 8px; border-bottom: 1px solid var(--line); }
td { padding: 6px 8px; border-bottom: 1px solid var(--line); }
.hash { color: var(--acc); }
</style>
