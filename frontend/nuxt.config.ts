export default defineNuxtConfig({
  compatibilityDate: "2026-01-01",
  devtools: { enabled: false },
  ssr: false, // chain reads are client-side
  runtimeConfig: {
    public: {
      rpcUrl: process.env.NUXT_PUBLIC_RPC_URL || "http://127.0.0.1:8545",
      recorderAddress: process.env.NUXT_PUBLIC_RECORDER || "",
      registryAddress: process.env.NUXT_PUBLIC_REGISTRY || "",
      vaultAddress: process.env.NUXT_PUBLIC_VAULT || "",
    },
  },
  app: {
    head: { title: "VeriAgent — Verifiable Agent Vault" },
  },
});
