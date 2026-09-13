// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {DecisionRecorder} from "../src/DecisionRecorder.sol";

contract DecisionRecorderTest is Test {
    DecisionRecorder internal recorder;

    address internal owner = address(this);
    address internal vault = address(0xBEEF);
    address internal stranger = address(0xBAD);

    bytes32 internal constant ACTION = keccak256("action");
    bytes32 internal constant REASON = keccak256("reason");
    bytes32 internal constant SOURCES = keccak256("sources");
    bytes32 internal constant MODEL = keccak256("model");

    event DecisionRecorded(
        uint256 indexed decisionId,
        uint256 indexed agentId,
        address indexed vault,
        bytes32 actionHash,
        bytes32 reasonHash,
        bytes32 dataSourceHash,
        bytes32 modelHash,
        uint64 timestamp
    );
    event DecisionBound(uint256 indexed decisionId, bytes32 indexed txHash);

    function setUp() public {
        recorder = new DecisionRecorder();
        recorder.setVaultAuthorization(vault, true);
    }

    // ── record() ──────────────────────────────────

    function test_record_success() public {
        vm.prank(vault);
        uint256 id = recorder.record(1, ACTION, REASON, SOURCES, MODEL);
        assertEq(id, 1);
        assertEq(recorder.decisionCount(), 1);

        DecisionRecorder.DecisionRecord memory r = recorder.getDecision(id);
        assertEq(r.agentId, 1);
        assertEq(r.vault, vault);
        assertEq(r.actionHash, ACTION);
        assertEq(r.reasonHash, REASON);
        assertEq(r.dataSourceHash, SOURCES);
        assertEq(r.modelHash, MODEL);
        assertEq(r.txHash, bytes32(0));
    }

    function test_record_emitsEvent() public {
        vm.prank(vault);
        vm.expectEmit(true, true, true, false);
        emit DecisionRecorded(1, 1, vault, ACTION, REASON, SOURCES, MODEL, uint64(block.timestamp));
        recorder.record(1, ACTION, REASON, SOURCES, MODEL);
    }

    function test_record_revertsUnauthorizedVault() public {
        vm.prank(stranger);
        vm.expectRevert(DecisionRecorder.NotAuthorizedVault.selector);
        recorder.record(1, ACTION, REASON, SOURCES, MODEL);
    }

    function test_record_revertsZeroActionHash() public {
        vm.prank(vault);
        vm.expectRevert(DecisionRecorder.ZeroHash.selector);
        recorder.record(1, bytes32(0), REASON, SOURCES, MODEL);
    }

    function test_record_revertsZeroReasonHash() public {
        vm.prank(vault);
        vm.expectRevert(DecisionRecorder.ZeroHash.selector);
        recorder.record(1, ACTION, bytes32(0), SOURCES, MODEL);
    }

    function test_record_idsIncrement() public {
        vm.startPrank(vault);
        assertEq(recorder.record(1, ACTION, REASON, SOURCES, MODEL), 1);
        assertEq(recorder.record(1, ACTION, REASON, SOURCES, MODEL), 2);
        assertEq(recorder.record(2, ACTION, REASON, SOURCES, MODEL), 3);
        vm.stopPrank();
        assertEq(recorder.decisionCount(), 3);
    }

    // ── bindTx() ──────────────────────────────────

    function test_bindTx_success() public {
        vm.prank(vault);
        uint256 id = recorder.record(1, ACTION, REASON, SOURCES, MODEL);

        bytes32 txH = keccak256("tx1");
        vm.prank(stranger); // anyone can bind once tx is known
        recorder.bindTx(id, txH);

        DecisionRecorder.DecisionRecord memory r = recorder.getDecision(id);
        assertEq(r.txHash, txH);
        assertEq(recorder.txToDecision(txH), id);
    }

    function test_bindTx_emitsEvent() public {
        vm.prank(vault);
        uint256 id = recorder.record(1, ACTION, REASON, SOURCES, MODEL);
        bytes32 txH = keccak256("tx1");
        vm.expectEmit(true, true, false, false);
        emit DecisionBound(id, txH);
        recorder.bindTx(id, txH);
    }

    function test_bindTx_revertsUnknownDecision() public {
        vm.expectRevert(DecisionRecorder.UnknownDecision.selector);
        recorder.bindTx(99, keccak256("tx"));
    }

    function test_bindTx_revertsDoubleBind() public {
        vm.prank(vault);
        uint256 id = recorder.record(1, ACTION, REASON, SOURCES, MODEL);
        recorder.bindTx(id, keccak256("tx1"));
        vm.expectRevert(DecisionRecorder.AlreadyBound.selector);
        recorder.bindTx(id, keccak256("tx2"));
    }

    function test_bindTx_revertsZeroTxHash() public {
        vm.prank(vault);
        uint256 id = recorder.record(1, ACTION, REASON, SOURCES, MODEL);
        vm.expectRevert(DecisionRecorder.ZeroHash.selector);
        recorder.bindTx(id, bytes32(0));
    }

    function test_bindTx_revertsTxHashReuse() public {
        vm.startPrank(vault);
        uint256 id1 = recorder.record(1, ACTION, REASON, SOURCES, MODEL);
        uint256 id2 = recorder.record(1, ACTION, REASON, SOURCES, MODEL);
        vm.stopPrank();
        bytes32 txH = keccak256("tx1");
        recorder.bindTx(id1, txH);
        vm.expectRevert(DecisionRecorder.TxAlreadyBound.selector);
        recorder.bindTx(id2, txH);
    }

    // ── verifyTrade() ─────────────────────────────

    function test_verifyTrade_fullCycle() public {
        vm.prank(vault);
        uint256 id = recorder.record(7, ACTION, REASON, SOURCES, MODEL);
        bytes32 txH = keccak256("realTx");
        recorder.bindTx(id, txH);

        DecisionRecorder.DecisionRecord memory r = recorder.verifyTrade(txH);
        assertEq(r.agentId, 7);
        assertEq(r.vault, vault);
        assertEq(r.reasonHash, REASON);
        assertEq(r.timestamp, uint64(block.timestamp));
    }

    function test_verifyTrade_revertsUnboundTx() public {
        vm.expectRevert(DecisionRecorder.UnknownDecision.selector);
        recorder.verifyTrade(keccak256("never"));
    }

    function test_getDecision_revertsUnknown() public {
        vm.expectRevert(DecisionRecorder.UnknownDecision.selector);
        recorder.getDecision(42);
    }

    // ── history ───────────────────────────────────

    function test_decisionsOf_history() public {
        vm.startPrank(vault);
        recorder.record(1, ACTION, REASON, SOURCES, MODEL);
        recorder.record(2, ACTION, REASON, SOURCES, MODEL);
        recorder.record(1, ACTION, REASON, SOURCES, MODEL);
        vm.stopPrank();

        uint256[] memory a1 = recorder.decisionsOf(1);
        uint256[] memory a2 = recorder.decisionsOf(2);
        assertEq(a1.length, 2);
        assertEq(a1[0], 1);
        assertEq(a1[1], 3);
        assertEq(a2.length, 1);
        assertEq(a2[0], 2);
    }

    // ── admin ─────────────────────────────────────

    function test_setVaultAuthorization_onlyOwner() public {
        vm.prank(stranger);
        vm.expectRevert(DecisionRecorder.NotOwner.selector);
        recorder.setVaultAuthorization(stranger, true);
    }

    function test_deauthorization_blocksRecording() public {
        recorder.setVaultAuthorization(vault, false);
        vm.prank(vault);
        vm.expectRevert(DecisionRecorder.NotAuthorizedVault.selector);
        recorder.record(1, ACTION, REASON, SOURCES, MODEL);
    }

    function test_transferOwnership() public {
        recorder.transferOwnership(stranger);
        vm.expectRevert(DecisionRecorder.NotOwner.selector);
        recorder.setVaultAuthorization(vault, true);
        vm.prank(stranger);
        recorder.setVaultAuthorization(vault, true); // new owner works
    }

    // ── invariant: credential precedes execution ───

    function test_invariant_unrecordedTxCannotBeVerified() public {
        // a trade executed without a prior record() can never gain a credential
        vm.prank(vault);
        uint256 id = recorder.record(1, ACTION, REASON, SOURCES, MODEL);
        bytes32 forgedTx = keccak256("forged");
        // binding a tx to this decision does not let another tx verify
        recorder.bindTx(id, keccak256("realTx"));
        vm.expectRevert(DecisionRecorder.UnknownDecision.selector);
        recorder.verifyTrade(forgedTx);
    }
}
