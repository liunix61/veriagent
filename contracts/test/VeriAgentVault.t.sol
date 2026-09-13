// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {VeriAgentVault, ITradeExecutor, IPriceOracle} from "../src/VeriAgentVault.sol";
import {AgentIdentityRegistry} from "../src/AgentIdentityRegistry.sol";
import {DecisionRecorder} from "../src/DecisionRecorder.sol";

// ── mocks ─────────────────────────────────────────

contract MockERC20 {
    string public name;
    uint8 public decimals = 18;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor(string memory n) { name = n; }

    function mint(address to, uint256 amt) external { balanceOf[to] += amt; }
    function approve(address spender, uint256 amt) external returns (bool) {
        allowance[msg.sender][spender] = amt;
        return true;
    }
    function transfer(address to, uint256 amt) external returns (bool) {
        balanceOf[msg.sender] -= amt;
        balanceOf[to] += amt;
        return true;
    }
    function transferFrom(address from, address to, uint256 amt) external returns (bool) {
        allowance[from][msg.sender] -= amt;
        balanceOf[from] -= amt;
        balanceOf[to] += amt;
        return true;
    }
}

contract MockExecutor is ITradeExecutor {
    uint256 public callCount;
    address public lastAsset;
    uint256 public lastAmount;
    bool public lastIsBuy;

    function execute(address asset, uint256 amount, bool isBuy, bytes calldata)
        external returns (bytes32)
    {
        callCount += 1;
        lastAsset = asset;
        lastAmount = amount;
        lastIsBuy = isBuy;
        return keccak256(abi.encodePacked(asset, amount, isBuy, callCount));
    }
}

contract MockOracle is IPriceOracle {
    mapping(address => uint256) public prices;
    function price(address asset) external view returns (uint256) { return prices[asset]; }
    function setPrice(address asset, uint256 p) external { prices[asset] = p; }
}

// ── test ──────────────────────────────────────────

contract VeriAgentVaultTest is Test {
    AgentIdentityRegistry internal reg;
    DecisionRecorder internal recorder;
    VeriAgentVault internal vault;
    MockExecutor internal executor;
    MockOracle internal oracle;
    MockERC20 internal usdc;
    MockERC20 internal nvda;

    address internal user = address(this);
    address internal key = address(0xA11CE);
    address internal stranger = address(0xBAD);
    address internal executorAddr;

    uint256 internal agentId;

    function setUp() public {
        // real integrations
        reg = new AgentIdentityRegistry();
        recorder = new DecisionRecorder();
        // mocks
        executor = new MockExecutor();
        oracle = new MockOracle();
        usdc = new MockERC20("USD Coin");
        nvda = new MockERC20("Tokenized NVIDIA");

        executorAddr = address(executor);
        vault = new VeriAgentVault(address(reg), address(recorder), executorAddr, address(oracle));

        // wire: agent with session key; vault authorized to record
        agentId = reg.registerAgent(keccak256("strategy-v1"), "veri-001.eth", key);
        recorder.setVaultAuthorization(address(vault), true);

        // prices: USDC $1, NVDA $100 (1e18 scale)
        oracle.setPrice(address(usdc), 1e18);
        oracle.setPrice(address(nvda), 100e18);

        // policy: NVDA/USDC whitelist, 10% position cap, 2% daily loss,
        //         60s cooldown, 10 trades/day
        address[] memory wl = new address[](2);
        wl[0] = address(usdc);
        wl[1] = address(nvda);
        VeriAgentVault.VaultPolicy memory p = VeriAgentVault.VaultPolicy({
            assetWhitelist: wl,
            maxPositionPctBps: 1000,
            dailyLossLimitBps: 200,
            tradeCooldown: 60,
            maxTradesPerDay: 10
        });
        vault.initialize(agentId, p);

        // fund vault: $1,000 USDC
        usdc.mint(address(this), 1_000e18);
        usdc.approve(address(vault), type(uint256).max);
        vault.deposit(address(usdc), 1_000e18);
    }

    function _trade(uint256 amount, bool isBuy) internal view returns (VeriAgentVault.Trade memory t) {
        t = VeriAgentVault.Trade({
            agentId: agentId,
            asset: address(nvda),
            amount: amount,
            isBuy: isBuy,
            actionHash: keccak256("action"),
            reasonHash: keccak256("reason"),
            dataSourceHash: keccak256("sources"),
            modelHash: keccak256("model"),
            executorData: ""
        });
    }

    // ── deposit/withdraw ──────────────────────────

    function test_deposit_success() public {
        assertEq(usdc.balanceOf(address(vault)), 1_000e18);
    }

    function test_deposit_revertsNotWhitelisted() public {
        MockERC20 doge = new MockERC20("Doge");
        doge.mint(address(this), 1e18);
        doge.approve(address(vault), 1e18);
        vm.expectRevert(abi.encodeWithSelector(VeriAgentVault.PolicyViolation.selector, keccak256("NOT_WHITELISTED")));
        vault.deposit(address(doge), 1e18);
    }

    function test_withdraw_onlyOwner() public {
        vm.prank(stranger);
        vm.expectRevert(VeriAgentVault.NotOwner.selector);
        vault.withdraw(address(usdc), 1e18);
    }

    // ── executeTrade happy path ───────────────────

    function test_executeTrade_happyPath() public {
        vm.prank(key);
        (uint256 decisionId, bytes32 fillHash) = vault.executeTrade(_trade(1e18, true));

        assertEq(decisionId, 1);
        assertEq(executor.callCount(), 1);
        assertEq(executor.lastAsset(), address(nvda));
        assertTrue(executor.lastIsBuy());
        assertTrue(fillHash != bytes32(0));
        assertEq(vault.tradesToday(), 1);
    }

    function test_executeTrade_credentialExistsOnRecorder() public {
        vm.prank(key);
        (uint256 decisionId, ) = vault.executeTrade(_trade(1e18, true));

        DecisionRecorder.DecisionRecord memory r = recorder.getDecision(decisionId);
        assertEq(r.agentId, agentId);
        assertEq(r.vault, address(vault));
        assertEq(r.reasonHash, keccak256("reason"));
    }

    // ── auth paths ────────────────────────────────

    function test_executeTrade_revertsNotSessionKey() public {
        vm.prank(stranger);
        vm.expectRevert(VeriAgentVault.NotSessionKey.selector);
        vault.executeTrade(_trade(1e18, true));
    }

    function test_executeTrade_revertsWrongAgentId() public {
        VeriAgentVault.Trade memory t = _trade(1e18, true);
        t.agentId = agentId + 1;
        vm.prank(key);
        vm.expectRevert(VeriAgentVault.NotSessionKey.selector);
        vault.executeTrade(t);
    }

    function test_executeTrade_revertsWhenPaused() public {
        vault.setPaused(true);
        vm.prank(key);
        vm.expectRevert(VeriAgentVault.PausedError.selector);
        vault.executeTrade(_trade(1e18, true));
    }

    function test_stolenKeyBlockedAfterRotation() public {
        // rotate to a new key; the old (leaked) key must no longer trade
        address newKey = address(0xB0B);
        reg.rotateSessionKey(agentId, newKey);
        vm.prank(key);
        vm.expectRevert(VeriAgentVault.NotSessionKey.selector);
        vault.executeTrade(_trade(1e18, true));
        vm.prank(newKey);
        (uint256 id, ) = vault.executeTrade(_trade(1e18, true));
        assertEq(id, 1);
    }

    // ── policy rules ──────────────────────────────

    function test_policy_cooldownBlocksFastRetrade() public {
        vm.prank(key);
        vault.executeTrade(_trade(1e18, true));
        vm.prank(key);
        vm.expectRevert(abi.encodeWithSelector(VeriAgentVault.PolicyViolation.selector, keccak256("COOLDOWN")));
        vault.executeTrade(_trade(1e18, true));
    }

    function test_policy_cooldownExpires() public {
        vm.prank(key);
        vault.executeTrade(_trade(1e18, true));
        vm.warp(block.timestamp + 61);
        vm.prank(key);
        (uint256 id, ) = vault.executeTrade(_trade(1e18, true));
        assertEq(id, 2);
    }

    function test_policy_dailyTradeLimit() public {
        // policy: 10/day — set lower for the test
        _reinitPolicy(1000, 200, 1, 2);
        vm.startPrank(key);
        vault.executeTrade(_trade(1e18, true));
        vm.warp(block.timestamp + 61);
        vault.executeTrade(_trade(1e18, true));
        vm.warp(block.timestamp + 61);
        vm.expectRevert(abi.encodeWithSelector(VeriAgentVault.PolicyViolation.selector, keccak256("DAILY_TRADE_LIMIT")));
        vault.executeTrade(_trade(1e18, true));
        vm.stopPrank();
    }

    function test_policy_dailyLimitResetsNextDay() public {
        _reinitPolicy(1000, 200, 1, 1);
        vm.prank(key);
        vault.executeTrade(_trade(1e18, true));
        vm.warp(block.timestamp + 1 days);
        vm.prank(key);
        (uint256 id, ) = vault.executeTrade(_trade(1e18, true));
        assertEq(id, 2);
    }

    function test_policy_notWhitelistedAsset() public {
        MockERC20 doge = new MockERC20("Doge");
        oracle.setPrice(address(doge), 1e18);
        VeriAgentVault.Trade memory t = _trade(1e18, true);
        t.asset = address(doge);
        vm.prank(key);
        vm.expectRevert(abi.encodeWithSelector(VeriAgentVault.PolicyViolation.selector, keccak256("NOT_WHITELISTED")));
        vault.executeTrade(t);
    }

    function test_policy_positionCap_blocksOversizedBuy() public {
        // vault value $1,000; cap 10% = $100; NVDA $100 → max 1 token
        vm.prank(key);
        (uint256 id, ) = vault.executeTrade(_trade(0.5e18, true)); // $50 — under cap
        assertEq(id, 1);

        vm.warp(block.timestamp + 61);
        vm.prank(key);
        vm.expectRevert(abi.encodeWithSelector(VeriAgentVault.PolicyViolation.selector, keccak256("POSITION_CAP")));
        vault.executeTrade(_trade(2e18, true)); // $200 — over remaining cap
    }

    function test_policy_dailyLossBreaker_blocksTrades() public {
        // no position cap for this scenario (NVDA pre-mint would trip it)
        _reinitPolicy(10_000, 200, 1, 10);
        // give vault a large NVDA position directly (simulates accumulated holdings)
        nvda.mint(address(vault), 20e18); // $2,000 worth at $100
        vm.prank(key);
        vault.executeTrade(_trade(0.1e18, true)); // first trade of day → snapshot $3,005
        vm.warp(block.timestamp + 61);

        // crash: NVDA → $80 (-20%): position loses $400 > 2% of $3,005
        oracle.setPrice(address(nvda), 80e18);

        vm.prank(key);
        vm.expectRevert(abi.encodeWithSelector(VeriAgentVault.PolicyViolation.selector, keccak256("DAILY_LOSS_LIMIT")));
        vault.executeTrade(_trade(0.1e18, true));
    }

    // ── credential-before-trade invariant ─────────

    function test_invariant_noCredentialNoTrade() public {
        // de-authorize the vault on the recorder → record() reverts → no execution
        recorder.setVaultAuthorization(address(vault), false);
        vm.prank(key);
        vm.expectRevert(); // DecisionRecorder.NotAuthorizedVault
        vault.executeTrade(_trade(1e18, true));
        assertEq(executor.callCount(), 0); // trade never happened
    }

    // ── policy timelock ───────────────────────────

    function test_policy_timelock() public {
        address[] memory wl = new address[](1);
        wl[0] = address(usdc);
        VeriAgentVault.VaultPolicy memory p = VeriAgentVault.VaultPolicy({
            assetWhitelist: wl,
            maxPositionPctBps: 10_000, // no cap: buying USDC (treasury) would trip any cap
            dailyLossLimitBps: 100,
            tradeCooldown: 30,
            maxTradesPerDay: 5
        });
        vault.updatePolicy(p);

        // new policy NOT yet effective: old cooldown still applies
        vm.prank(key);
        vault.executeTrade(_trade(1e18, true));
        vm.warp(block.timestamp + 31); // > new cooldown 30, < old cooldown 60
        vm.prank(key);
        vm.expectRevert(abi.encodeWithSelector(VeriAgentVault.PolicyViolation.selector, keccak256("COOLDOWN")));
        vault.executeTrade(_trade(1e18, true));

        // after timelock: new cooldown 30s applies; new whitelist is USDC-only
        vm.warp(block.timestamp + 24 hours);
        vault.activatePolicy();
        vm.prank(key);
        VeriAgentVault.Trade memory t2 = _trade(1e18, true);
        t2.asset = address(usdc);
        (uint256 id, ) = vault.executeTrade(t2);
        assertEq(id, 2);
    }

    function test_policy_activateTooEarly_reverts() public {
        address[] memory wl = new address[](1);
        wl[0] = address(usdc);
        vault.updatePolicy(VeriAgentVault.VaultPolicy({
            assetWhitelist: wl, maxPositionPctBps: 500, dailyLossLimitBps: 100,
            tradeCooldown: 30, maxTradesPerDay: 5}));
        vm.expectRevert(VeriAgentVault.TimelockActive.selector);
        vault.activatePolicy();
    }

    // ── helper ────────────────────────────────────

    function _reinitPolicy(uint16 capBps, uint16 lossBps, uint32 cooldown, uint16 maxPerDay) internal {
        address[] memory wl = new address[](2);
        wl[0] = address(usdc);
        wl[1] = address(nvda);
        vault.initialize(agentId, VeriAgentVault.VaultPolicy({
            assetWhitelist: wl, maxPositionPctBps: capBps, dailyLossLimitBps: lossBps,
            tradeCooldown: cooldown, maxTradesPerDay: maxPerDay}));
    }
}
