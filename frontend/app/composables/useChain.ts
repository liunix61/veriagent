/** Chain access: viem public client + minimal ABIs. Falls back to demo
 * data when RPC or contract addresses are not configured. */

import { createPublicClient, http, type PublicClient } from "viem";

export const recorderAbi = [
  {
    type: "event",
    name: "DecisionRecorded",
    inputs: [
      { name: "credentialId", type: "bytes32", indexed: true },
      { name: "agent", type: "address", indexed: true },
      { name: "decisionHash", type: "bytes32", indexed: false },
      { name: "chain", type: "string", indexed: false },
      { name: "action", type: "string", indexed: false },
      { name: "venue", type: "string", indexed: false },
      { name: "asset", type: "string", indexed: false },
      { name: "amount", type: "uint256", indexed: false },
      { name: "maxSlippageBps", type: "uint256", indexed: false },
      { name: "riskScore", type: "uint256", indexed: false },
      { name: "contextHash", type: "bytes32", indexed: false },
      { name: "nonce", type: "uint256", indexed: false },
      { name: "expiresAt", type: "uint256", indexed: false },
      { name: "recordedAt", type: "uint256", indexed: false },
    ],
  },
  {
    type: "event",
    name: "TradeBound",
    inputs: [
      { name: "credentialId", type: "bytes32", indexed: true },
      { name: "txHash", type: "bytes32", indexed: true },
      { name: "boundAt", type: "uint256", indexed: false },
    ],
  },
  {
    type: "function",
    name: "verifyTrade",
    stateMutability: "view",
    inputs: [
      { name: "decisionHash", type: "bytes32" },
      { name: "txHash", type: "bytes32" },
    ],
    outputs: [
      { name: "", type: "bool" },
      { name: "", type: "string" },
    ],
  },
] as const;

export const vaultAbi = [
  {
    type: "function",
    name: "positionAgent",
    stateMutability: "view",
    inputs: [],
    outputs: [
      { name: "", type: "address" },
      { name: "", type: "uint8" },
      { name: "", type: "uint8" },
      { name: "", type: "uint256" },
    ],
  },
  {
    type: "function",
    name: "getPolicy",
    stateMutability: "view",
    inputs: [],
    outputs: [
      { name: "", type: "address[]" },
      { name: "", type: "uint256[]" },
      { name: "", type: "uint256" },
      { name: "", type: "uint256" },
      { name: "", type: "uint256" },
      { name: "", type: "uint256" },
      { name: "", type: "bool" },
    ],
  },
  {
    type: "function",
    name: "totalValue",
    stateMutability: "view",
    inputs: [],
    outputs: [{ name: "", type: "uint256" }],
  },
] as const;

let client: PublicClient | null = null;

export function useChain() {
  const cfg = useRuntimeConfig().public;
  const connected = ref(false);
  const chainLabel = ref("");

  function getClient(): PublicClient {
    if (!client) {
      client = createPublicClient({
        transport: http(cfg.rpcUrl as string),
      });
    }
    return client;
  }

  async function probe() {
    try {
      const c = getClient();
      const id = await c.getChainId();
      chainLabel.value = `chain ${id}`;
      connected.value = true;
    } catch {
      connected.value = false;
    }
  }

  onMounted(probe);

  return { getClient, connected, chainLabel, cfg };
}
