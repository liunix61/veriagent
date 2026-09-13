// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title DecisionRecorder - VeriAgent decision credential registry
/// @notice Every agent trading decision is committed on-chain BEFORE execution.
///         Full decision JSON lives off-chain (IPFS); only hashes are stored.
///         Two-phase: record() at decision time, bindTx() after execution.
contract DecisionRecorder {
    struct DecisionRecord {
        uint256 agentId;
        address vault;
        bytes32 actionHash;      // keccak(action JSON: side/amount/asset)
        bytes32 reasonHash;      // keccak(LLM reason summary)
        bytes32 dataSourceHash;  // keccak(data sources + x402 proofs)
        bytes32 modelHash;       // keccak(model/prompt version)
        uint64 timestamp;
        bytes32 txHash;          // execution tx hash (back-filled, 0 until bound)
    }

    /// @dev decisions can only be recorded by registered vaults
    mapping(address => bool) public authorizedVault;
    address public owner;

    uint256 public nextDecisionId = 1;
    mapping(uint256 => DecisionRecord) private records;
    /// @notice decisionIds per agent, for history queries
    mapping(uint256 => uint256[]) private agentDecisions;
    /// @notice decisionId lookup by execution tx hash
    mapping(bytes32 => uint256) public txToDecision;

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
    event VaultAuthorized(address indexed vault, bool authorized);
    event OwnershipTransferred(address indexed prev, address indexed next);

    error NotOwner();
    error NotAuthorizedVault();
    error ZeroHash();
    error UnknownDecision();
    error AlreadyBound();
    error TxAlreadyBound();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    // ──────────────────────────────────────────────
    // Admin
    // ──────────────────────────────────────────────

    function setVaultAuthorization(address vault, bool authorized) external onlyOwner {
        authorizedVault[vault] = authorized;
        emit VaultAuthorized(vault, authorized);
    }

    function transferOwnership(address next) external onlyOwner {
        emit OwnershipTransferred(owner, next);
        owner = next;
    }

    // ──────────────────────────────────────────────
    // Core: two-phase credential lifecycle
    // ──────────────────────────────────────────────

    /// @notice Commit a decision credential. Must precede execution.
    function record(
        uint256 agentId,
        bytes32 actionHash,
        bytes32 reasonHash,
        bytes32 dataSourceHash,
        bytes32 modelHash
    ) external returns (uint256 decisionId) {
        if (!authorizedVault[msg.sender]) revert NotAuthorizedVault();
        if (actionHash == bytes32(0) || reasonHash == bytes32(0)) revert ZeroHash();

        decisionId = nextDecisionId++;
        records[decisionId] = DecisionRecord({
            agentId: agentId,
            vault: msg.sender,
            actionHash: actionHash,
            reasonHash: reasonHash,
            dataSourceHash: dataSourceHash,
            modelHash: modelHash,
            timestamp: uint64(block.timestamp),
            txHash: bytes32(0)
        });
        agentDecisions[agentId].push(decisionId);

        emit DecisionRecorded(
            decisionId, agentId, msg.sender,
            actionHash, reasonHash, dataSourceHash, modelHash,
            uint64(block.timestamp)
        );
    }

    /// @notice Back-fill the execution tx hash after the trade settles.
    /// @dev    Callable by the vault that recorded the decision, or anyone
    ///         once the executing tx is known (txHash is self-attesting).
    function bindTx(uint256 decisionId, bytes32 txHash) external {
        DecisionRecord storage r = records[decisionId];
        if (r.timestamp == 0) revert UnknownDecision();
        if (r.txHash != bytes32(0)) revert AlreadyBound();
        if (txHash == bytes32(0)) revert ZeroHash();
        if (txToDecision[txHash] != 0) revert TxAlreadyBound();

        r.txHash = txHash;
        txToDecision[txHash] = decisionId;
        emit DecisionBound(decisionId, txHash);
    }

    // ──────────────────────────────────────────────
    // Verification views (Explorer / third parties)
    // ──────────────────────────────────────────────

    /// @notice Full self-attesting verification: txHash → complete record.
    function verifyTrade(bytes32 txHash) external view returns (DecisionRecord memory) {
        uint256 id = txToDecision[txHash];
        if (id == 0) revert UnknownDecision();
        return records[id];
    }

    function getDecision(uint256 decisionId) external view returns (DecisionRecord memory) {
        if (records[decisionId].timestamp == 0) revert UnknownDecision();
        return records[decisionId];
    }

    function decisionsOf(uint256 agentId) external view returns (uint256[] memory) {
        return agentDecisions[agentId];
    }

    function decisionCount() external view returns (uint256) {
        return nextDecisionId - 1;
    }
}
