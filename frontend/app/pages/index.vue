<template>
  <div>
    <div class="grid">
      <div>
        <VaultPanel />
        <div style="height: 16px" />
        <ContractPanel />
        <div style="height: 16px" />
        <BStocksPanel />
      </div>
      <AuditExplorer />
    </div>
  </div>
</template>

<script setup lang="ts">
// Console: vault state + contract map + bStocks compliance on the left,
// audit explorer on the right
</script>
