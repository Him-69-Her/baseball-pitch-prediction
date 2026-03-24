// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {FunctionsClient} from "@chainlink/contracts/src/v0.8/functions/v1_0_0/FunctionsClient.sol";
import {FunctionsRequest} from "@chainlink/contracts/src/v0.8/functions/v1_0_0/libraries/FunctionsRequest.sol";

/**
 * TinyHub Price Oracle — Chainlink Functions Consumer
 *
 * Fetches real-time LMP (Locational Marginal Price) from:
 *   - MISO (Midcontinent ISO) for District 91 / Ameren
 *   - PJM for District 63 / ComEd
 *
 * The settler checks this oracle price before settling trades.
 * If the P2P settled price deviates more than TOLERANCE from the
 * oracle LMP, the trade is flagged as suspicious.
 *
 * Arbitrum Sepolia:
 *   Router: 0x234a5fb5Bd614a7AA2FfAB244D603abFA0Ac5C5C
 *   DON ID: fun-arbitrum-sepolia-1
 */
contract TinyHubPriceOracle is FunctionsClient {
    using FunctionsRequest for FunctionsRequest.Request;

    // ── State ──────────────────────────────────────────────
    address public owner;

    // Latest LMP prices (scaled: $0.05/kWh = 5000)
    // Stored as price * 100000 to avoid decimals
    mapping(string => uint256) public latestLMP;       // district → price
    mapping(string => uint256) public lastUpdated;     // district → timestamp
    mapping(bytes32 => string) public pendingRequests;  // requestId → district

    // Config
    uint64  public subscriptionId;
    bytes32 public donId;
    uint32  public gasLimit = 300000;
    string  public misoSource;     // JavaScript source for MISO API call
    string  public pjmSource;      // JavaScript source for PJM API call

    // Price tolerance: 20% deviation from oracle = suspicious
    uint256 public constant TOLERANCE_BPS = 2000; // 20% in basis points
    uint256 public constant PRICE_SCALE = 100000; // $0.05 = 5000

    // ── Events ─────────────────────────────────────────────
    event PriceUpdated(string district, uint256 lmpPrice, uint256 timestamp);
    event PriceRequested(bytes32 indexed requestId, string district);
    event PriceRequestFailed(bytes32 indexed requestId, bytes error);

    // ── Modifiers ──────────────────────────────────────────
    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    // ── Constructor ────────────────────────────────────────
    constructor(
        address _router,
        uint64 _subscriptionId,
        bytes32 _donId
    ) FunctionsClient(_router) {
        owner = msg.sender;
        subscriptionId = _subscriptionId;
        donId = _donId;
    }

    // ── Admin ──────────────────────────────────────────────
    function setSubscriptionId(uint64 _subId) external onlyOwner {
        subscriptionId = _subId;
    }

    function setDonId(bytes32 _donId) external onlyOwner {
        donId = _donId;
    }

    function setGasLimit(uint32 _gasLimit) external onlyOwner {
        gasLimit = _gasLimit;
    }

    function setMisoSource(string memory _source) external onlyOwner {
        misoSource = _source;
    }

    function setPjmSource(string memory _source) external onlyOwner {
        pjmSource = _source;
    }

    function transferOwnership(address _newOwner) external onlyOwner {
        require(_newOwner != address(0), "Zero address");
        owner = _newOwner;
    }

    // ── Request price update ───────────────────────────────
    function requestMisoPrice() external onlyOwner returns (bytes32) {
        require(bytes(misoSource).length > 0, "MISO source not set");

        FunctionsRequest.Request memory req;
        req.initializeRequestForInlineJavaScript(misoSource);

        bytes32 requestId = _sendRequest(
            req.encodeCBOR(),
            subscriptionId,
            gasLimit,
            donId
        );

        pendingRequests[requestId] = "IL_D91";
        emit PriceRequested(requestId, "IL_D91");
        return requestId;
    }

    function requestPjmPrice() external onlyOwner returns (bytes32) {
        require(bytes(pjmSource).length > 0, "PJM source not set");

        FunctionsRequest.Request memory req;
        req.initializeRequestForInlineJavaScript(pjmSource);

        bytes32 requestId = _sendRequest(
            req.encodeCBOR(),
            subscriptionId,
            gasLimit,
            donId
        );

        pendingRequests[requestId] = "McHenry_D63";
        emit PriceRequested(requestId, "McHenry_D63");
        return requestId;
    }

    // ── Chainlink callback ─────────────────────────────────
    function fulfillRequest(
        bytes32 requestId,
        bytes memory response,
        bytes memory err
    ) internal override {
        string memory district = pendingRequests[requestId];

        if (err.length > 0) {
            emit PriceRequestFailed(requestId, err);
            return;
        }

        // Response is the LMP price as uint256 (scaled by PRICE_SCALE)
        uint256 price = abi.decode(response, (uint256));

        latestLMP[district] = price;
        lastUpdated[district] = block.timestamp;

        emit PriceUpdated(district, price, block.timestamp);

        delete pendingRequests[requestId];
    }

    // ── Price verification (called by settler/market) ──────

    /// @notice Check if a settled price is within tolerance of the oracle LMP
    /// @param _district "IL_D91" or "McHenry_D63"
    /// @param _settledPrice The P2P clearing price (scaled by PRICE_SCALE)
    /// @return valid True if within tolerance
    /// @return oraclePrice The oracle's latest LMP for reference
    function verifyPrice(
        string memory _district,
        uint256 _settledPrice
    ) external view returns (bool valid, uint256 oraclePrice) {
        oraclePrice = latestLMP[_district];

        // If no oracle price yet, can't verify — allow trade
        if (oraclePrice == 0) {
            return (true, 0);
        }

        // Check staleness (price older than 15 min = stale)
        if (block.timestamp - lastUpdated[_district] > 900) {
            return (true, oraclePrice); // Stale data — allow but flag
        }

        // Calculate tolerance band
        uint256 tolerance = (oraclePrice * TOLERANCE_BPS) / 10000;
        uint256 lower = oraclePrice > tolerance ? oraclePrice - tolerance : 0;
        uint256 upper = oraclePrice + tolerance;

        valid = (_settledPrice >= lower && _settledPrice <= upper);
        return (valid, oraclePrice);
    }

    /// @notice Get the latest oracle price for a district
    function getPrice(string memory _district) external view returns (uint256 price, uint256 timestamp) {
        return (latestLMP[_district], lastUpdated[_district]);
    }

    /// @notice Check if oracle data is fresh (< 15 minutes old)
    function isFresh(string memory _district) external view returns (bool) {
        return (block.timestamp - lastUpdated[_district]) < 900;
    }
}
