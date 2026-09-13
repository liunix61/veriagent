// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {DecisionRecorder} from "../src/DecisionRecorder.sol";
import {AgentIdentityRegistry} from "../src/AgentIdentityRegistry.sol";
import {VeriAgentVault} from "../src/VeriAgentVault.sol";
import {PaymentRouter} from "../src/PaymentRouter.sol";

/// @notice Deploys the full VeriAgent contract set.
/// Usage:
///   forge script script/Deploy.s.sol --rpc-url $RPC_URL --broadcast --private-key $PK
/// Env:
///   USDC_ADDRESS  — native USDC on target chain
///   EXECUTOR_ADDRESS — ITradeExecutor venue adapter (deployed separately)
///   ORACLE_ADDRESS — IPriceOracle (mock or Chainlink adapter)
contract Deploy is Script {
    function run() external {
        uint256 pk = vm.envUint("DEPLOYER_PK");
        address usdc = vm.envAddress("USDC_ADDRESS");
        address executor = vm.envAddress("EXECUTOR_ADDRESS");
        address oracle = vm.envAddress("ORACLE_ADDRESS");

        vm.startBroadcast(pk);

        DecisionRecorder recorder = new DecisionRecorder();
        AgentIdentityRegistry registry = new AgentIdentityRegistry();
        PaymentRouter router = new PaymentRouter(usdc);

        // vault template deployed per-user by a factory in W2; one demo vault here
        VeriAgentVault vault = new VeriAgentVault(
            address(registry), address(recorder), executor, oracle
        );

        vm.stopBroadcast();

        console.log("DecisionRecorder:", address(recorder));
        console.log("AgentIdentityRegistry:", address(registry));
        console.log("PaymentRouter:", address(router));
        console.log("VeriAgentVault (demo):", address(vault));
    }
}
