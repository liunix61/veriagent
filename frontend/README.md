# VeriAgent Frontend

Nuxt 4 console for the VeriAgent contract set: vault state, policy view,
and the **Audit Explorer** — on-chain evidence that every trade had a
credential *before* it executed (`recordedAt ≤ boundAt`).

## Run

```bash
npm install
NUXT_PUBLIC_RPC_URL=https://sepolia-rollup.arbitrum.io/rpc \
NUXT_PUBLIC_RECORDER=0x... NUXT_PUBLIC_REGISTRY=0x... NUXT_PUBLIC_VAULT=0x... \
npm run dev
```

Without env vars the console renders demo data (marked `DEMO` in the UI) —
it never fabricates a `ON-CHAIN` badge.

## Stack

Nuxt 4 · Vue 3 · viem (public client, contract events). No wallet needed for
the read-only console; signing stays in the engine (session keys), matching
the security model: the browser never touches agent keys.
