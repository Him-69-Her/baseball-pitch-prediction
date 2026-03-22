// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * TinyHubMarketV2 — Multi-District P2P Energy + Compute Marketplace
 *
 * Extends V1 with:
 *   - district field on every trade (e.g. "McHenry_D63", "IL_D91")
 *   - cross-district bridge trades via bridgeResource()
 *   - district-level stats (trade count, MWh settled per district)
 *   - event emissions for Pub/Sub bridge listeners
 */
contract TinyHubMarketV2 {

    // ── Enums ──────────────────────────────────────────────
    enum ResourceType { Energy, Compute }
    enum TradeStatus  { Open, Settled, Bridged, Cancelled }

    // ── Structs ────────────────────────────────────────────
    struct Trade {
        string   stationId;
        string   district;       // NEW: "McHenry_D63", "IL_D91", etc.
        address payable seller;
        address  buyer;
        uint256  amount;         // MWh or TFLOP-hours (scaled 1e18)
        uint256  pricePerUnit;
        ResourceType rType;
        TradeStatus  status;
        bool     exists;
    }

    // ── State ──────────────────────────────────────────────
    mapping(uint256 => Trade) public trades;
    uint256 public tradeCount;
    uint256 public constant PLATFORM_FEE = 0.01 ether;

    // District-level counters
    mapping(string => uint256) public districtTradeCount;
    mapping(string => uint256) public districtMWhSettled;

    // ── Events (for Pub/Sub bridge listeners) ──────────────
    event ResourceListed(
        uint256 indexed tradeId,
        string  district,
        string  stationId,
        uint256 amount,
        uint256 pricePerUnit,
        ResourceType rType
    );

    event ResourcePurchased(
        uint256 indexed tradeId,
        string  district,
        address buyer,
        uint256 settledPrice
    );

    event ResourceBridged(
        uint256 indexed tradeId,
        string  fromDistrict,
        string  toDistrict,
        address buyer,
        uint256 settledPrice
    );

    // ── List a resource for sale ───────────────────────────
    function listResource(
        string memory _id,
        string memory _district,
        uint256 _amount,
        uint256 _price,
        ResourceType _type
    ) public {
        tradeCount++;
        trades[tradeCount] = Trade({
            stationId:    _id,
            district:     _district,
            seller:       payable(msg.sender),
            buyer:        address(0),
            amount:       _amount,
            pricePerUnit: _price,
            rType:        _type,
            status:       TradeStatus.Open,
            exists:       true
        });

        emit ResourceListed(tradeCount, _district, _id, _amount, _price, _type);
    }

    // ── Purchase within same district ──────────────────────
    function purchaseResource(uint256 _tradeId) public payable {
        Trade storage trade = trades[_tradeId];
        uint256 totalCost = (trade.amount * trade.pricePerUnit) + PLATFORM_FEE;

        require(trade.exists && trade.status == TradeStatus.Open, "Invalid trade");
        require(msg.value >= totalCost, "Insufficient funds");

        trade.buyer  = msg.sender;
        trade.status = TradeStatus.Settled;
        trade.seller.transfer(trade.amount * trade.pricePerUnit);

        // Update district stats
        districtTradeCount[trade.district]++;
        districtMWhSettled[trade.district] += trade.amount;

        emit ResourcePurchased(_tradeId, trade.district, msg.sender, trade.pricePerUnit);
    }

    // ── Cross-district bridge purchase ─────────────────────
    //    Buyer in district B purchases surplus from district A
    function bridgeResource(uint256 _tradeId, string memory _buyerDistrict) public payable {
        Trade storage trade = trades[_tradeId];
        uint256 totalCost = (trade.amount * trade.pricePerUnit) + (PLATFORM_FEE * 2); // 2x fee for bridge

        require(trade.exists && trade.status == TradeStatus.Open, "Invalid trade");
        require(msg.value >= totalCost, "Insufficient funds");

        trade.buyer  = msg.sender;
        trade.status = TradeStatus.Bridged;
        trade.seller.transfer(trade.amount * trade.pricePerUnit);

        // Credit both districts
        districtTradeCount[trade.district]++;
        districtTradeCount[_buyerDistrict]++;
        districtMWhSettled[trade.district] += trade.amount;

        emit ResourceBridged(_tradeId, trade.district, _buyerDistrict, msg.sender, trade.pricePerUnit);
    }

    // ── Cancel a listing ───────────────────────────────────
    function cancelResource(uint256 _tradeId) public {
        Trade storage trade = trades[_tradeId];
        require(trade.exists && trade.status == TradeStatus.Open, "Invalid trade");
        require(msg.sender == trade.seller, "Not seller");
        trade.status = TradeStatus.Cancelled;
    }

    // ── View helpers ───────────────────────────────────────
    function getTradeDistrict(uint256 _tradeId) public view returns (string memory) {
        return trades[_tradeId].district;
    }

    function getTradeStatus(uint256 _tradeId) public view returns (TradeStatus) {
        return trades[_tradeId].status;
    }
}
