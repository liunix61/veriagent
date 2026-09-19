// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface ITradeExecutor {
    /// @notice Execute one trade against a venue (DEX/bStocks market). Pulls `amount` of `asset` from this vault.
    function execute(address asset, uint256 amount, bool isBuy, bytes calldata data) external returns (bytes32 fillHash);
}

interface IDecisionRecorder {
    function record(
        uint256 agentId,
        bytes32 actionHash,
        bytes32 reasonHash,
        bytes32 dataSourceHash,
        bytes32 modelHash
    ) external returns (uint256 decisionId);

    function bindTx(uint256 decisionId, bytes32 txHash) external;
}

interface IAgentRegistry {
    function agentOfSessionKey(address key) external view returns (uint256, bool);
}

/// @title VeriAgentVault - policy-enforced strategy vault
/// @notice Users deposit assets; the bound agent can only trade within hard
///         on-chain constraints. Every trade is atomically preceded by a
///         decision credential (no credential, no trade).
contract VeriAgentVault {
    struct VaultPolicy {
        address[] assetWhitelist;
        uint16 maxPositionPctBps;   // per-asset cap, bps of total value (1000 = 10%)
        uint16 dailyLossLimitBps;   // daily-loss circuit breaker, bps
        uint32 tradeCooldown;       // min seconds between trades
        uint16 maxTradesPerDay;
    }

    struct Trade {
        uint256 agentId;
        address asset;
        uint256 amount;             // trade notional in `asset` units
        bool isBuy;
        bytes32 actionHash;         // keccak(action JSON)
        bytes32 reasonHash;         // keccak(reason)
        bytes32 dataSourceHash;     // keccak(data sources + x402 proofs)
        bytes32 modelHash;          // keccak(model/prompt version)
        bytes executorData;         // venue-specific payload
    }

    // ── config ────────────────────────────────────
    address public owner;
    uint256 public agentId;
    VaultPolicy private policy;          // active policy
    VaultPolicy private pendingPolicy;   // queued, takes effect after timelock
    bool public hasPendingPolicy;
    IAgentRegistry public registry;
    IDecisionRecorder public recorder;
    ITradeExecutor public executor;
    address public priceOracle;     // for position/daily-loss valuation (mockable)

    bool public paused;
    uint64 public policyEffectiveAt; // timelock gate for policy updates
    uint64 public constant POLICY_TIMELOCK = 24 hours;

    // ── state ─────────────────────────────────────
    uint64 public lastTradeAt;
    uint64 public currentDay;
    uint16 public tradesToday;
    /// @dev day-start total value snapshot for the daily-loss circuit breaker
    uint64 public snapshotDay;
    uint256 public snapshotTotal;

    event Deposited(address indexed asset, uint256 amount);
    event Withdrawn(address indexed asset, uint256 amount);
    event TradeExecuted(uint256 indexed decisionId, address indexed asset, uint256 amount, bool isBuy, bytes32 fillHash);
    event TradeRejected(bytes32 reason);
    event PolicyQueued(uint64 effectiveAt);
    event PolicyActivated();
    event PausedSet(bool paused);
    /// @notice Tokenized-equity dividend distribution acknowledged on-chain.
    ///         SEC "No Synthetics" (Innovation Exemption 2026-09-17): tokenized
    ///         shares must pass through the same dividend rights as the
    ///         underlying share — this event is the on-chain record of that
    ///         passthrough, mirroring the engine's dividend_ack credential.
    event DividendReceived(address indexed asset, uint256 amount, uint64 timestamp);

    error NotOwner();
    error NotSessionKey();
    error PausedError();
    error PolicyViolation(bytes32 reason);
    error NoFunds();
    error TimelockActive();
    error NothingQueued();

    // reason codes (hashed for gas-cheap comparison)
    bytes32 internal constant R_NOT_WHITELISTED = keccak256("NOT_WHITELISTED");
    bytes32 internal constant R_COOLDOWN        = keccak256("COOLDOWN");
    bytes32 internal constant R_DAILY_LIMIT     = keccak256("DAILY_TRADE_LIMIT");
    bytes32 internal constant R_POSITION_CAP    = keccak256("POSITION_CAP");
    bytes32 internal constant R_AGENT_MISMATCH  = keccak256("AGENT_MISMATCH");
    bytes32 internal constant R_DAILY_LOSS      = keccak256("DAILY_LOSS_LIMIT");

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address registry_, address recorder_, address executor_, address oracle_) {
        owner = msg.sender;
        registry = IAgentRegistry(registry_);
        recorder = IDecisionRecorder(recorder_);
        executor = ITradeExecutor(executor_);
        priceOracle = oracle_;
        // sentinel so the first _rollDay() always snapshots day-start value
        currentDay = type(uint64).max;
    }

    // ──────────────────────────────────────────────
    // Setup
    // ──────────────────────────────────────────────

    function initialize(uint256 agentId_, VaultPolicy calldata p) external onlyOwner {
        agentId = agentId_;
        _storePolicy(p);
        emit PolicyActivated();
    }

    function setExecutor(address executor_) external onlyOwner {
        executor = ITradeExecutor(executor_);
    }

    function setPaused(bool p) external onlyOwner {
        paused = p;
        emit PausedSet(p);
    }

    /// @notice Queue a policy change; takes effect after POLICY_TIMELOCK.
    function updatePolicy(VaultPolicy calldata p) external onlyOwner {
        _writePolicy(pendingPolicy, p);
        hasPendingPolicy = true;
        policyEffectiveAt = uint64(block.timestamp + POLICY_TIMELOCK);
        emit PolicyQueued(policyEffectiveAt);
    }

    /// @notice Activate queued policy once the timelock has elapsed.
    function activatePolicy() external {
        if (!hasPendingPolicy) revert NothingQueued();
        if (block.timestamp < policyEffectiveAt) revert TimelockActive();
        _copyPendingToActive();
        hasPendingPolicy = false;
        policyEffectiveAt = 0;
        emit PolicyActivated();
    }

    function _writePolicy(VaultPolicy storage dst, VaultPolicy calldata p) internal {
        delete dst.assetWhitelist;
        for (uint256 i = 0; i < p.assetWhitelist.length; i++) {
            dst.assetWhitelist.push(p.assetWhitelist[i]);
        }
        dst.maxPositionPctBps = p.maxPositionPctBps;
        dst.dailyLossLimitBps = p.dailyLossLimitBps;
        dst.tradeCooldown = p.tradeCooldown;
        dst.maxTradesPerDay = p.maxTradesPerDay;
    }

    function _copyPendingToActive() internal {
        delete policy.assetWhitelist;
        for (uint256 i = 0; i < pendingPolicy.assetWhitelist.length; i++) {
            policy.assetWhitelist.push(pendingPolicy.assetWhitelist[i]);
        }
        policy.maxPositionPctBps = pendingPolicy.maxPositionPctBps;
        policy.dailyLossLimitBps = pendingPolicy.dailyLossLimitBps;
        policy.tradeCooldown = pendingPolicy.tradeCooldown;
        policy.maxTradesPerDay = pendingPolicy.maxTradesPerDay;
    }

    function _storePolicy(VaultPolicy calldata p) internal {
        _writePolicy(policy, p);
    }

    // ──────────────────────────────────────────────
    // Funds
    // ──────────────────────────────────────────────

    function deposit(address asset, uint256 amount) external onlyOwner {
        if (!_isWhitelisted(asset)) revert PolicyViolation(R_NOT_WHITELISTED);
        IERC20(asset).transferFrom(msg.sender, address(this), amount);
        emit Deposited(asset, amount);
    }

    function withdraw(address asset, uint256 amount) external onlyOwner {
        IERC20(asset).transfer(msg.sender, amount);
        emit Withdrawn(asset, amount);
    }

    // ──────────────────────────────────────────────
    // Tokenized-equity dividends (bStocks on Robinhood Chain)
    // ──────────────────────────────────────────────

    /// @notice Cumulative dividends received per asset (tokenized equities).
    mapping(address => uint256) public dividendsReceived;

    /// @notice Record a dividend/distribution event for a whitelisted
    ///         tokenized-equity asset. SEC "No Synthetics" principle
    ///         (Innovation Exemption 2026-09-17): holders of stock tokens
    ///         must retain dividend rights identical to the traditional
    ///         share — this function is the on-chain record of that
    ///         passthrough. Callable by the bound agent session key (the
    ///         oracle/agent that observed the distribution) or the owner.
    function notifyDividend(address asset, uint256 amount) external {
        if (msg.sender != owner) {
            (uint256 keyAgentId, bool active) = registry.agentOfSessionKey(msg.sender);
            if (keyAgentId == 0 || !active || keyAgentId != agentId) revert NotSessionKey();
        }
        if (!_isWhitelisted(asset)) revert PolicyViolation(R_NOT_WHITELISTED);
        dividendsReceived[asset] += amount;
        emit DividendReceived(asset, amount, uint64(block.timestamp));
    }

    // ──────────────────────────────────────────────
    // Core: credential-then-trade
    // ──────────────────────────────────────────────

    /// @notice Execute one trade. Requires: active session key, policy pass,
    ///         and atomically records the decision credential BEFORE execution.
    function executeTrade(Trade calldata t) external returns (uint256 decisionId, bytes32 fillHash) {
        // 0. roll day: resets counters and snapshots day-start value for the loss breaker
        _rollDay();

        // 1. caller must be the bound agent's current session key
        (uint256 keyAgentId, bool active) = registry.agentOfSessionKey(msg.sender);
        if (keyAgentId == 0 || !active || keyAgentId != t.agentId || t.agentId != agentId) {
            revert NotSessionKey();
        }
        if (paused) revert PausedError();

        // 2. policy checks (all hard on-chain constraints)
        (bool ok, bytes32 reason) = checkPolicy(t);
        if (!ok) revert PolicyViolation(reason);

        // 3. decision credential FIRST — no credential, no trade
        decisionId = recorder.record(
            t.agentId, t.actionHash, t.reasonHash, t.dataSourceHash, t.modelHash
        );

        // 4. execution via pluggable venue adapter
        fillHash = executor.execute(t.asset, t.amount, t.isBuy, t.executorData);

        // 5. accounting
        lastTradeAt = uint64(block.timestamp);
        tradesToday += 1;

        emit TradeExecuted(decisionId, t.asset, t.amount, t.isBuy, fillHash);
    }

    // ──────────────────────────────────────────────
    // Policy engine: ordered checks, reason for self-correction
    // ──────────────────────────────────────────────

    function checkPolicy(Trade calldata t) public view returns (bool ok, bytes32 reason) {
        // agent binding
        if (t.agentId != agentId) return (false, R_AGENT_MISMATCH);
        // whitelist
        if (!_isWhitelisted(t.asset)) return (false, R_NOT_WHITELISTED);
        // cooldown (no constraint before the first trade ever)
        if (policy.tradeCooldown != 0 && lastTradeAt != 0 &&
            block.timestamp < lastTradeAt + policy.tradeCooldown) return (false, R_COOLDOWN);
        // daily frequency
        _Day memory d = _dayView();
        if (policy.maxTradesPerDay != 0 && d.isToday && tradesToday >= policy.maxTradesPerDay) {
            return (false, R_DAILY_LIMIT);
        }
        // daily-loss circuit breaker: current value vs day-start snapshot
        if (policy.dailyLossLimitBps != 0 && priceOracle != address(0) &&
            snapshotDay == uint64(block.timestamp / 1 days) && snapshotTotal > 0) {
            (uint256 totalNow, ) = _portfolioValue(address(0));
            if (totalNow * 10_000 < snapshotTotal * (10_000 - policy.dailyLossLimitBps)) {
                return (false, R_DAILY_LOSS);
            }
        }
        // position cap: post-trade asset value ≤ cap × total value (oracle-denominated, simplified:
        // if no oracle wired, skip valuation — tests use a mock oracle contract)
        if (policy.maxPositionPctBps != 0 && priceOracle != address(0)) {
            (bool capOk, ) = _positionWithinCap(t);
            if (!capOk) return (false, R_POSITION_CAP);
        }
        return (true, bytes32(0));
    }

    function _isWhitelisted(address asset) internal view returns (bool) {
        for (uint256 i = 0; i < policy.assetWhitelist.length; i++) {
            if (policy.assetWhitelist[i] == asset) return true;
        }
        return false;
    }

    struct _Day { uint64 day; bool isToday; }

    function _dayView() internal view returns (_Day memory) {
        return _Day({day: uint64(block.timestamp / 1 days), isToday: uint64(block.timestamp / 1 days) == currentDay});
    }

    function _rollDay() internal {
        uint64 today = uint64(block.timestamp / 1 days);
        if (today != currentDay) {
            currentDay = today;
            tradesToday = 0;
            snapshotDay = today;
            if (priceOracle != address(0)) {
                (uint256 tv, ) = _portfolioValue(address(0));
                snapshotTotal = tv;
            } else {
                snapshotTotal = 0;
            }
        }
    }

    /// @dev Position cap via oracle: MockPriceOracle(asset) → price in USD (1e18).
    function _positionWithinCap(Trade calldata t) internal view returns (bool, uint256) {
        (uint256 totalValue, uint256 assetValue) = _portfolioValue(t.asset);
        if (totalValue == 0) return (true, 0);
        // convert trade notional (asset units) to oracle-denominated value
        uint256 price = IPriceOracle(priceOracle).price(t.asset);
        uint256 tradeValue = t.amount * price / 1e18;
        // sells reduce the position; cap only constrains buys
        uint256 postValue = t.isBuy ? assetValue + tradeValue : assetValue;
        // post-trade portfolio total (buys add value, sells leave total unchanged here)
        uint256 postTotal = t.isBuy ? totalValue + tradeValue : totalValue;
        return (postValue * 10_000 <= postTotal * policy.maxPositionPctBps, postValue);
    }

    function _portfolioValue(address focusAsset)
        internal view returns (uint256 total, uint256 focusValue)
    {
        uint256 n = policy.assetWhitelist.length;
        for (uint256 i = 0; i < n; i++) {
            address a = policy.assetWhitelist[i];
            uint256 bal = IERC20(a).balanceOf(address(this));
            uint256 price = IPriceOracle(priceOracle).price(a);
            total += bal * price / 1e18;
            if (a == focusAsset) focusValue = bal * price / 1e18;
        }
    }

    // ──────────────────────────────────────────────
    // Views
    // ──────────────────────────────────────────────

    function getPolicy() external view returns (VaultPolicy memory) {
        return policy;
    }
}

interface IPriceOracle {
    function price(address asset) external view returns (uint256);
}
