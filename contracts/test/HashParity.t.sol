// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";

/// @notice Cross-language hash parity: engine/abi_encode.py must produce the
/// same keccak256 commitment as Solidity abi.encode of the decision payload.
/// The vector is also asserted in tests/test_engine.py — if either side
/// drifts, one of the two suites fails.
contract HashParityTest is Test {
    function test_hashParity_pythonEncoder_matchesSolidity() public pure {
        bytes32 ctx = hex"abababababababababababababababababababababababababababababababab";
        bytes32 h = keccak256(abi.encode(
            address(0x1001),
            "arbitrum-sepolia",
            "buy",
            "uniswap-v3",
            "WETH",
            uint256(10 ** 16),
            uint256(50),
            uint256(1200),
            ctx,
            uint256(1),
            uint256(2000000000)
        ));
        assertEq(
            h,
            bytes32(0xe3b5c92cc8264fc527cdd99dff2271777fc9588852785422845227234a910f46),
            "python abi_encode.py drifted from Solidity abi.encode"
        );
    }
}
