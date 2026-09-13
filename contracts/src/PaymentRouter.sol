// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20PR {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/// @title PaymentRouter — x402-style on-chain settlement for agent micropayments
/// @notice An agent (payer) signs an EIP-712 PaymentAuth offline; anyone can
///         submit it to settle. USDC moves payer → merchant, a receipt hash is
///         emitted so data purchases become audit evidence (feeds dataSourceHash).
///         Aligned with EIP-3009 transferWithAuthorization semantics, simplified
///         to a single-token (USDC) router for the competition build.
contract PaymentRouter {
    struct PaymentAuth {
        address payer;
        address merchant;
        uint256 amount;       // USDC 6-decimals units
        uint256 nonce;        // per-payer sequential nonce
        uint256 deadline;     // unix ts after which the auth is void
        bytes32 resourceHash; // purchased data/service content hash
    }

    IERC20PR public immutable usdc;
    address public owner;
    uint256 private receiptSeq;

    /// @notice per-payer next expected nonce (EIP-2612 style)
    mapping(address => uint256) public nonces;
    /// @notice consumed auth digests (belt-and-braces alongside nonces)
    mapping(bytes32 => bool) public consumed;
    /// @notice receiptId → auth summary for verification views
    mapping(uint256 => PaymentAuth) private receipts;

    // EIP-712 domain
    bytes32 public constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 public constant AUTH_TYPEHASH =
        keccak256("PaymentAuth(address payer,address merchant,uint256 amount,uint256 nonce,uint256 deadline,bytes32 resourceHash)");
    bytes32 public immutable DOMAIN_SEPARATOR;

    event PaymentSettled(
        uint256 indexed receiptId,
        address indexed payer,
        address indexed merchant,
        uint256 amount,
        bytes32 resourceHash
    );
    event FacilitatorSet(address indexed facilitator, bool enabled);

    error NotOwner();
    error NotFacilitator();
    error SignatureExpired();
    error NonceMismatch();
    error AuthAlreadyConsumed();
    error InvalidSignature();
    error ZeroAmount();
    error ZeroMerchant();

    mapping(address => bool) public facilitator;

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address usdc_) {
        owner = msg.sender;
        usdc = IERC20PR(usdc_);
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(DOMAIN_TYPEHASH, keccak256("VeriPay"), keccak256("1"), block.chainid, address(this))
        );
    }

    function setFacilitator(address f, bool enabled) external onlyOwner {
        facilitator[f] = enabled;
        emit FacilitatorSet(f, enabled);
    }

    /// @notice Settle one authorized payment. Callable by anyone (relayer /
    ///         facilitator / merchant) — the signature is the only authority.
    function settle(PaymentAuth calldata auth, bytes calldata sig)
        external
        returns (uint256 receiptId)
    {
        if (auth.amount == 0) revert ZeroAmount();
        if (auth.merchant == address(0)) revert ZeroMerchant();
        if (block.timestamp > auth.deadline) revert SignatureExpired();
        if (auth.nonce != nonces[auth.payer]) revert NonceMismatch();

        bytes32 structHash = keccak256(abi.encode(
            AUTH_TYPEHASH, auth.payer, auth.merchant, auth.amount, auth.nonce, auth.deadline, auth.resourceHash
        ));
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR, structHash));
        if (consumed[digest]) revert AuthAlreadyConsumed();

        address signer = _recover(digest, sig);
        if (signer == address(0) || signer != auth.payer) revert InvalidSignature();

        // effects
        consumed[digest] = true;
        nonces[auth.payer] = auth.nonce + 1;

        // interaction: payer must have approved this router for USDC
        usdc.transferFrom(auth.payer, auth.merchant, auth.amount);

        receiptId = ++receiptSeq;
        receipts[receiptId] = auth;
        emit PaymentSettled(receiptId, auth.payer, auth.merchant, auth.amount, auth.resourceHash);
    }

    /// @notice Verification view for panels/auditors.
    function verifyReceipt(uint256 receiptId) external view returns (PaymentAuth memory) {
        return receipts[receiptId];
    }

    function _recover(bytes32 digest, bytes calldata sig) internal pure returns (address) {
        if (sig.length != 65) return address(0);
        bytes32 r = bytes32(sig[0:32]);
        bytes32 s = bytes32(sig[32:64]);
        uint8 v = uint8(sig[64]);
        if (v < 27) v += 27;
        // reject malleable signatures (s > secp256k1n/2)
        if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) {
            return address(0);
        }
        return ecrecover(digest, v, r, s);
    }
}
