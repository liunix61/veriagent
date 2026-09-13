// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {DecisionRecorder} from "../src/DecisionRecorder.sol";

/// @notice End-to-end cross-language parity against the REAL contract:
/// the four commitment hashes computed by engine/models.py from a fixed
/// Decision fixture are submitted to a deployed DecisionRecorder, and the
/// stored record + events must carry them unchanged. Same fixture asserted
/// in tests/test_abi_parity.py — drift on either side fails one suite.
contract HashParityTest is Test {
    DecisionRecorder internal recorder;
    address internal vault = address(this); // test acts as the vault

    // engine fixture: Decision(agent_id=7, buy WETH, reason="buy WETH
    // spread=6.0bps liq=5000000", model="strategy-v1", ...)
    uint256 constant AGENT_ID = 7;
    bytes32 constant ACTION_HASH =
        0xdd53723a2398aff850ba558da48929e40623ab8ce90c68fa2413a47b03fce1e1;
    bytes32 constant REASON_HASH =
        0x3c4dc0f96c0af44265dff0ac0569ddcf1dbd52d703f9dacd26f8621024f18bc3;
    bytes32 constant DATA_SOURCE_HASH =
        0xe47fff08fcc1b5db46324acadc7c4a6db33098ac1f5e42afdc49e639a0bb883a;
    bytes32 constant MODEL_HASH =
        0x36e92fb341dbfc84b52048934241929a7d96631588ac49ab9b1dbcc20ae56027;

    function setUp() public {
        recorder = new DecisionRecorder();
        recorder.setVaultAuthorization(vault, true);
    }

    function test_record_storesEngineHashesUnchanged() public {
        uint256 id = recorder.record(
            AGENT_ID, ACTION_HASH, REASON_HASH, DATA_SOURCE_HASH, MODEL_HASH
        );
        DecisionRecorder.DecisionRecord memory r = recorder.getDecision(id);

        assertEq(r.agentId, AGENT_ID);
        assertEq(r.vault, vault);
        assertEq(r.actionHash, ACTION_HASH, "actionHash drifted from engine");
        assertEq(r.reasonHash, REASON_HASH, "reasonHash drifted from engine");
        assertEq(r.dataSourceHash, DATA_SOURCE_HASH, "dataSourceHash drifted");
        assertEq(r.modelHash, MODEL_HASH, "modelHash drifted");
        assertGt(r.timestamp, 0);
        assertEq(r.txHash, bytes32(0)); // unbound until execution
    }

    function test_record_then_bind_then_verify_fullLoop() public {
        uint256 id = recorder.record(
            AGENT_ID, ACTION_HASH, REASON_HASH, DATA_SOURCE_HASH, MODEL_HASH
        );
        bytes32 execTx = keccak256("fake-execution-tx");
        recorder.bindTx(id, execTx);

        DecisionRecorder.DecisionRecord memory r = recorder.verifyTrade(execTx);
        assertEq(r.agentId, AGENT_ID);
        assertEq(r.reasonHash, REASON_HASH);
        assertEq(r.txHash, execTx);
    }

    function test_record_emitsDecisionRecordedWithEngineHashes() public {
        vm.expectEmit(true, true, true, true);
        emit DecisionRecorder.DecisionRecorded(
            1, AGENT_ID, vault,
            ACTION_HASH, REASON_HASH, DATA_SOURCE_HASH, MODEL_HASH,
            uint64(block.timestamp)
        );
        recorder.record(
            AGENT_ID, ACTION_HASH, REASON_HASH, DATA_SOURCE_HASH, MODEL_HASH
        );
    }
}
