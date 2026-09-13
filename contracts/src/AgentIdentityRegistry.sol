// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title AgentIdentityRegistry - ERC-8004-style agent identity & reputation
/// @notice One agentId = one verifiable strategy datasheet (metadataHash → IPFS).
///         Reputation: +1 clean audited trade, -5 violations (slashing via owner).
contract AgentIdentityRegistry {
    struct AgentRecord {
        address owner;          // controller; rotates session keys
        string ensName;         // optional human-readable identity
        bytes32 metadataHash;   // IPFS hash of strategy/model version
        uint64 registeredAt;
        int256 reputation;
        bool active;
    }

    uint256 public nextAgentId = 1;
    mapping(uint256 => AgentRecord) private agents;
    /// @notice active session key → agentId (0 = not bound)
    mapping(address => uint256) public sessionKeyToAgent;
    /// @notice agentId → current session key
    mapping(uint256 => address) public agentSessionKey;
    /// @notice owner → their agentIds
    mapping(address => uint256[]) private ownerAgents;

    event AgentRegistered(uint256 indexed agentId, address indexed owner, bytes32 metadataHash, string ensName);
    event SessionKeyRotated(uint256 indexed agentId, address indexed oldKey, address indexed newKey);
    event AgentStatusChanged(uint256 indexed agentId, bool active);
    event ReputationChanged(uint256 indexed agentId, int256 delta, int256 newReputation);
    event ReputationSlasherSet(address indexed slasher, bool enabled);

    error NotAgentOwner();
    error UnknownAgent();
    error AgentInactive();
    error ZeroMetadataHash();
    error KeyAlreadyBound();
    error NotSlasher();

    /// @notice designated contract allowed to adjust reputation (e.g. vault registry)
    mapping(address => bool) public reputationSlasher;
    address public owner;

    modifier onlyAgentOwner(uint256 agentId) {
        AgentRecord storage a = agents[agentId];
        if (a.registeredAt == 0) revert UnknownAgent();
        if (a.owner != msg.sender) revert NotAgentOwner();
        _;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotSlasher();
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function setReputationSlasher(address slasher, bool enabled) external onlyOwner {
        reputationSlasher[slasher] = enabled;
        emit ReputationSlasherSet(slasher, enabled);
    }

    // ──────────────────────────────────────────────
    // Registration
    // ──────────────────────────────────────────────

    function registerAgent(bytes32 metadataHash, string calldata ensName, address sessionKey)
        external
        returns (uint256 agentId)
    {
        if (metadataHash == bytes32(0)) revert ZeroMetadataHash();
        if (sessionKey != address(0) && sessionKeyToAgent[sessionKey] != 0) revert KeyAlreadyBound();

        agentId = nextAgentId++;
        agents[agentId] = AgentRecord({
            owner: msg.sender,
            ensName: ensName,
            metadataHash: metadataHash,
            registeredAt: uint64(block.timestamp),
            reputation: 0,
            active: true
        });
        ownerAgents[msg.sender].push(agentId);
        if (sessionKey != address(0)) {
            sessionKeyToAgent[sessionKey] = agentId;
            agentSessionKey[agentId] = sessionKey;
        }
        emit AgentRegistered(agentId, msg.sender, metadataHash, ensName);
    }

    function rotateSessionKey(uint256 agentId, address newKey) external onlyAgentOwner(agentId) {
        if (newKey != address(0) && sessionKeyToAgent[newKey] != 0) revert KeyAlreadyBound();
        address oldKey = agentSessionKey[agentId];
        if (oldKey != address(0)) {
            delete sessionKeyToAgent[oldKey];
        }
        if (newKey != address(0)) {
            sessionKeyToAgent[newKey] = agentId;
        }
        agentSessionKey[agentId] = newKey;
        emit SessionKeyRotated(agentId, oldKey, newKey);
    }

    function setActive(uint256 agentId, bool active) external onlyAgentOwner(agentId) {
        agents[agentId].active = active;
        emit AgentStatusChanged(agentId, active);
    }

    // ──────────────────────────────────────────────
    // Reputation
    // ──────────────────────────────────────────────

    function adjustReputation(uint256 agentId, int256 delta) external {
        if (!reputationSlasher[msg.sender]) revert NotSlasher();
        AgentRecord storage a = agents[agentId];
        if (a.registeredAt == 0) revert UnknownAgent();
        a.reputation += delta;
        emit ReputationChanged(agentId, delta, a.reputation);
    }

    // ──────────────────────────────────────────────
    // Views
    // ──────────────────────────────────────────────

    function getAgent(uint256 agentId) external view returns (AgentRecord memory) {
        if (agents[agentId].registeredAt == 0) revert UnknownAgent();
        return agents[agentId];
    }

    function agentOfSessionKey(address key) external view returns (uint256, bool) {
        uint256 id = sessionKeyToAgent[key];
        if (id == 0) return (0, false);
        return (id, agents[id].active);
    }

    function agentsOf(address owner_) external view returns (uint256[] memory) {
        return ownerAgents[owner_];
    }

    function agentCount() external view returns (uint256) {
        return nextAgentId - 1;
    }
}
