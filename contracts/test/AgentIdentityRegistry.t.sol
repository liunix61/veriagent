// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {AgentIdentityRegistry} from "../src/AgentIdentityRegistry.sol";

contract AgentIdentityRegistryTest is Test {
    AgentIdentityRegistry internal reg;

    address internal dev = address(this);
    address internal key1 = address(0x1111);
    address internal key2 = address(0x2222);
    address internal other = address(0xBAD);

    bytes32 internal constant META = keccak256("strategy-v1");

    event AgentRegistered(uint256 indexed agentId, address indexed owner, bytes32 metadataHash, string ensName);
    event SessionKeyRotated(uint256 indexed agentId, address indexed oldKey, address indexed newKey);

    function setUp() public {
        reg = new AgentIdentityRegistry();
    }

    // ── registerAgent ─────────────────────────────

    function test_register_success() public {
        uint256 id = reg.registerAgent(META, "veri-001.eth", key1);
        assertEq(id, 1);
        assertEq(reg.agentCount(), 1);

        AgentIdentityRegistry.AgentRecord memory a = reg.getAgent(id);
        assertEq(a.owner, dev);
        assertEq(a.ensName, "veri-001.eth");
        assertEq(a.metadataHash, META);
        assertEq(a.reputation, 0);
        assertTrue(a.active);
        assertEq(reg.agentSessionKey(id), key1);
    }

    function test_register_emitsEvent() public {
        vm.expectEmit(true, true, false, true);
        emit AgentRegistered(1, dev, META, "veri-001.eth");
        reg.registerAgent(META, "veri-001.eth", key1);
    }

    function test_register_revertsZeroMetadata() public {
        vm.expectRevert(AgentIdentityRegistry.ZeroMetadataHash.selector);
        reg.registerAgent(bytes32(0), "x", key1);
    }

    function test_register_revertsBoundKeyReuse() public {
        reg.registerAgent(META, "a", key1);
        vm.expectRevert(AgentIdentityRegistry.KeyAlreadyBound.selector);
        reg.registerAgent(META, "b", key1);
    }

    function test_register_noSessionKeyAllowed() public {
        uint256 id = reg.registerAgent(META, "a", address(0));
        assertEq(reg.agentSessionKey(id), address(0));
    }

    // ── session key ───────────────────────────────

    function test_agentOfSessionKey_lookup() public {
        uint256 id = reg.registerAgent(META, "a", key1);
        (uint256 found, bool active) = reg.agentOfSessionKey(key1);
        assertEq(found, id);
        assertTrue(active);
        (uint256 none, ) = reg.agentOfSessionKey(key2);
        assertEq(none, 0);
    }

    function test_rotateSessionKey_success() public {
        uint256 id = reg.registerAgent(META, "a", key1);
        reg.rotateSessionKey(id, key2);
        assertEq(reg.agentSessionKey(id), key2);

        // old key freed
        (uint256 oldLookup, ) = reg.agentOfSessionKey(key1);
        assertEq(oldLookup, 0);
        // new key bound
        (uint256 newLookup, bool active) = reg.agentOfSessionKey(key2);
        assertEq(newLookup, id);
        assertTrue(active);
    }

    function test_rotateSessionKey_emitsEvent() public {
        uint256 id = reg.registerAgent(META, "a", key1);
        vm.expectEmit(true, true, true, false);
        emit SessionKeyRotated(id, key1, key2);
        reg.rotateSessionKey(id, key2);
    }

    function test_rotateSessionKey_revertsNonOwner() public {
        uint256 id = reg.registerAgent(META, "a", key1);
        vm.prank(other);
        vm.expectRevert(AgentIdentityRegistry.NotAgentOwner.selector);
        reg.rotateSessionKey(id, key2);
    }

    function test_rotateSessionKey_revertsBoundKeyReuse() public {
        reg.registerAgent(META, "a", key1);
        uint256 id2 = reg.registerAgent(META, "b", key2);
        vm.expectRevert(AgentIdentityRegistry.KeyAlreadyBound.selector);
        reg.rotateSessionKey(id2, key1);
    }

    function test_stolenKeyProtection_rotateInvalidatesOldKey() public {
        // simulates key leak: owner rotates, leaked key can no longer be resolved
        uint256 id = reg.registerAgent(META, "a", key1);
        reg.rotateSessionKey(id, key2);
        (uint256 leaked, ) = reg.agentOfSessionKey(key1);
        assertEq(leaked, 0);
    }

    // ── active status ─────────────────────────────

    function test_setActive_togglesLookup() public {
        uint256 id = reg.registerAgent(META, "a", key1);
        reg.setActive(id, false);
        (uint256 found, bool active) = reg.agentOfSessionKey(key1);
        assertEq(found, id);
        assertFalse(active);
        assertFalse(reg.getAgent(id).active);
    }

    function test_setActive_revertsNonOwner() public {
        uint256 id = reg.registerAgent(META, "a", key1);
        vm.prank(other);
        vm.expectRevert(AgentIdentityRegistry.NotAgentOwner.selector);
        reg.setActive(id, false);
    }

    // ── reputation ────────────────────────────────

    function test_reputation_slasherFlow() public {
        uint256 id = reg.registerAgent(META, "a", key1);
        address vault = address(0xFEE);
        reg.setReputationSlasher(vault, true);

        vm.prank(vault);
        reg.adjustReputation(id, 1);   // clean trade
        vm.prank(vault);
        reg.adjustReputation(id, -5);  // violation
        assertEq(reg.getAgent(id).reputation, -4);
    }

    function test_reputation_revertsUnauthorized() public {
        uint256 id = reg.registerAgent(META, "a", key1);
        vm.prank(other);
        vm.expectRevert(AgentIdentityRegistry.NotSlasher.selector);
        reg.adjustReputation(id, 1);
    }

    function test_reputation_revertsUnknownAgent() public {
        reg.setReputationSlasher(address(this), true);
        vm.expectRevert(AgentIdentityRegistry.UnknownAgent.selector);
        reg.adjustReputation(99, 1);
    }

    function test_setReputationSlasher_onlyOwner() public {
        vm.prank(other);
        vm.expectRevert(AgentIdentityRegistry.NotSlasher.selector);
        reg.setReputationSlasher(other, true);
    }

    // ── views ─────────────────────────────────────

    function test_getAgent_revertsUnknown() public {
        vm.expectRevert(AgentIdentityRegistry.UnknownAgent.selector);
        reg.getAgent(1);
    }

    function test_agentsOf_history() public {
        reg.registerAgent(META, "a", key1);
        reg.registerAgent(META, "b", key2);
        vm.prank(other);
        reg.registerAgent(META, "c", address(0));

        uint256[] memory mine = reg.agentsOf(dev);
        uint256[] memory theirs = reg.agentsOf(other);
        assertEq(mine.length, 2);
        assertEq(theirs.length, 1);
    }
}
