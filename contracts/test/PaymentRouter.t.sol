// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {PaymentRouter} from "../src/PaymentRouter.sol";

contract MockUSDC {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    function mint(address to, uint256 a) external { balanceOf[to] += a; }
    function approve(address s, uint256 a) external returns (bool) { allowance[msg.sender][s] = a; return true; }
    function transferFrom(address f, address t, uint256 a) external returns (bool) {
        allowance[f][msg.sender] -= a;
        balanceOf[f] -= a;
        balanceOf[t] += a;
        return true;
    }
}

contract PaymentRouterTest is Test {
    PaymentRouter internal router;
    MockUSDC internal usdc;

    uint256 internal payerPk = 0xA11CE;
    address internal payer;
    address internal merchant = address(0x1001);
    address internal facilitator = address(0x1002);
    address internal relayer = address(0x1003);

    uint256 internal constant AMT = 10_000; // $0.01 (6 decimals)

    function setUp() public {
        payer = vm.addr(payerPk);
        usdc = new MockUSDC();
        router = new PaymentRouter(address(usdc));
        usdc.mint(payer, 1_000_000);
        vm.prank(payer);
        usdc.approve(address(router), type(uint256).max);
    }

    function _auth(uint256 nonce, uint256 deadline, uint256 amount)
        internal view returns (PaymentRouter.PaymentAuth memory)
    {
        return PaymentRouter.PaymentAuth({
            payer: payer,
            merchant: merchant,
            amount: amount,
            nonce: nonce,
            deadline: deadline,
            resourceHash: keccak256("cmc:NVDA")
        });
    }

    function _sign(PaymentRouter.PaymentAuth memory a) internal view returns (bytes memory) {
        bytes32 structHash = keccak256(abi.encode(
            router.AUTH_TYPEHASH(), a.payer, a.merchant, a.amount, a.nonce, a.deadline, a.resourceHash
        ));
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", router.DOMAIN_SEPARATOR(), structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(payerPk, digest);
        return abi.encodePacked(r, s, v);
    }

    // ── happy path ────────────────────────────────

    function test_settle_success() public {
        PaymentRouter.PaymentAuth memory a = _auth(0, block.timestamp + 1 hours, AMT);
        vm.prank(relayer); // anyone may relay
        uint256 id = router.settle(a, _sign(a));

        assertEq(id, 1);
        assertEq(usdc.balanceOf(merchant), AMT);
        assertEq(usdc.balanceOf(payer), 1_000_000 - AMT);
        assertEq(router.nonces(payer), 1);
    }

    function test_settle_emitsReceipt() public {
        PaymentRouter.PaymentAuth memory a = _auth(0, block.timestamp + 1 hours, AMT);
        vm.expectEmit(true, true, true, true);
        emit PaymentRouter.PaymentSettled(1, payer, merchant, AMT, keccak256("cmc:NVDA"));
        router.settle(a, _sign(a));
    }

    function test_verifyReceipt_roundTrip() public {
        PaymentRouter.PaymentAuth memory a = _auth(0, block.timestamp + 1 hours, AMT);
        uint256 id = router.settle(a, _sign(a));
        PaymentRouter.PaymentAuth memory r = router.verifyReceipt(id);
        assertEq(r.payer, payer);
        assertEq(r.merchant, merchant);
        assertEq(r.amount, AMT);
        assertEq(r.resourceHash, keccak256("cmc:NVDA"));
    }

    function test_settle_sequentialNonces() public {
        for (uint256 i = 0; i < 3; i++) {
            PaymentRouter.PaymentAuth memory a = _auth(i, block.timestamp + 1 hours, AMT);
            router.settle(a, _sign(a));
        }
        assertEq(usdc.balanceOf(merchant), 3 * AMT);
        assertEq(router.nonces(payer), 3);
    }

    // ── attack paths ──────────────────────────────

    function test_settle_replayReverts() public {
        PaymentRouter.PaymentAuth memory a = _auth(0, block.timestamp + 1 hours, AMT);
        bytes memory sig = _sign(a);
        router.settle(a, sig);
        vm.expectRevert(PaymentRouter.NonceMismatch.selector);
        router.settle(a, sig); // replayed
    }

    function test_settle_expiredReverts() public {
        PaymentRouter.PaymentAuth memory a = _auth(0, block.timestamp + 10, AMT);
        bytes memory sig = _sign(a);
        vm.warp(block.timestamp + 11);
        vm.expectRevert(PaymentRouter.SignatureExpired.selector);
        router.settle(a, sig);
    }

    function test_settle_wrongSignerReverts() public {
        PaymentRouter.PaymentAuth memory a = _auth(0, block.timestamp + 1 hours, AMT);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(0xB0B, keccak256("junk"));
        bytes memory badSig = abi.encodePacked(r, s, v);
        vm.expectRevert(PaymentRouter.InvalidSignature.selector);
        router.settle(a, badSig);
    }

    function test_settle_tamperedAmountReverts() public {
        PaymentRouter.PaymentAuth memory a = _auth(0, block.timestamp + 1 hours, AMT);
        bytes memory sig = _sign(a);
        a.amount = AMT * 100; // tamper after signing
        vm.expectRevert(PaymentRouter.InvalidSignature.selector);
        router.settle(a, sig);
    }

    function test_settle_tamperedMerchantReverts() public {
        PaymentRouter.PaymentAuth memory a = _auth(0, block.timestamp + 1 hours, AMT);
        bytes memory sig = _sign(a);
        a.merchant = address(0xBEEF);
        vm.expectRevert(PaymentRouter.InvalidSignature.selector);
        router.settle(a, sig);
    }

    function test_settle_malleableSigReverts() public {
        PaymentRouter.PaymentAuth memory a = _auth(0, block.timestamp + 1 hours, AMT);
        bytes memory sig = _sign(a);
        // flip to high-s form: s' = n - s, v' = v^1
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := mload(add(sig, 32))
            s := mload(add(sig, 64))
            v := byte(0, mload(add(sig, 96)))
        }
        uint256 n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;
        bytes32 s2 = bytes32(n - uint256(s));
        uint8 v2 = v == 27 ? 28 : 27;
        bytes memory malleable = abi.encodePacked(r, s2, v2);
        vm.expectRevert(PaymentRouter.InvalidSignature.selector);
        router.settle(a, malleable);
    }

    function test_settle_wrongNonceReverts() public {
        PaymentRouter.PaymentAuth memory a = _auth(5, block.timestamp + 1 hours, AMT); // expected 0
        bytes memory sig = _sign(a);
        vm.expectRevert(PaymentRouter.NonceMismatch.selector);
        router.settle(a, sig);
    }

    function test_settle_zeroAmountReverts() public {
        PaymentRouter.PaymentAuth memory a = _auth(0, block.timestamp + 1 hours, 0);
        bytes memory sig = _sign(a);
        vm.expectRevert(PaymentRouter.ZeroAmount.selector);
        router.settle(a, sig);
    }

    function test_settle_zeroMerchantReverts() public {
        PaymentRouter.PaymentAuth memory a = _auth(0, block.timestamp + 1 hours, AMT);
        a.merchant = address(0);
        bytes memory sig = _sign(a);
        vm.expectRevert(PaymentRouter.ZeroMerchant.selector);
        router.settle(a, sig);
    }

    function test_settle_shortSigReverts() public {
        PaymentRouter.PaymentAuth memory a = _auth(0, block.timestamp + 1 hours, AMT);
        vm.expectRevert(PaymentRouter.InvalidSignature.selector);
        router.settle(a, hex"deadbeef");
    }

    // ── domain separation ─────────────────────────

    function test_domainSeparator_bindsChainAndContract() public {
        PaymentRouter other = new PaymentRouter(address(usdc));
        assertTrue(other.DOMAIN_SEPARATOR() != router.DOMAIN_SEPARATOR());
    }

    // ── admin ─────────────────────────────────────

    function test_setFacilitator_onlyOwner() public {
        vm.prank(facilitator);
        vm.expectRevert(PaymentRouter.NotOwner.selector);
        router.setFacilitator(facilitator, true);
    }
}
