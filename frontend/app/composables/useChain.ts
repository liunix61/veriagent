/** Chain access: viem public client + minimal ABIs. Falls back to demo
 * data when RPC or contract addresses are not configured. */

import { createPublicClient, http, type PublicClient } from "viem";

export const recorderAbi = [
  {
    type: "event",
    name: "DecisionRecorded",
    inputs: [
      { name: "decisionId", type: "uint256", indexed: true },
      { name: "agentId", type: "uint256", indexed: true },
      { name: "vault", type: "address", indexed: true },
      { name: "actionHash", type: "bytes32", indexed: false },
      { name: "reasonHash", type: "bytes32", indexed: false },
      { name: "dataSourceHash", type: "bytes32", indexed: false },
      { name: "modelHash", type: "bytes32", indexed: false },
      { name: "timestamp", type: "uint64", indexed: false },
    ],
  },
  {
    type: "event",
    name: "DecisionBound",
    inputs: [
      { name: "decisionId", type: "uint256", indexed: true },
      { name: "txHash", type: "bytes32", indexed: true },
    ],
  },
  {
    type: "function",
    name: "verifyTrade",
    stateMutability: "view",
    inputs: [{ name: "txHash", type: "bytes32" }],
    outputs: [
      {
        name: "",
        type: "tuple",
        components: [
          { name: "agentId", type: "uint256" },
          { name: "vault", type: "address" },
          { name: "actionHash", type: "bytes32" },
          { name: "reasonHash", type: "bytes32" },
          { name: "dataSourceHash", type: "bytes32" },
          { name: "modelHash", type: "bytes32" },
          { name: "timestamp", type: "uint64" },
          { name: "txHash", type: "bytes32" },
        ],
      },
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
