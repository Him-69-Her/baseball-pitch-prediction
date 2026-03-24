// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * TinyHubMarketV3 — L2 Arbitrum Multi-District P2P Energy Marketplace
 *
 * Upgrades from V2:
 *   - On-chain idempotency mapping (replaces Python seen_ids)
 *   - Owner + settler access control (no more Hardhat open accounts)
 *   - Settler-only listResource/purchaseResource/bridge
 *   - Pausable for emergency stops
 *   - Batch settlement support (settleTradeBundle)
 *
 * Deploy target: Arbitrum Sepolia (chainId 421614)
 */
contract TinyHubMarketV3 {

    // ── Enums ──────────────────────────────────────────────
    enum ResourceType { Energy, Compute }
    enum TradeStatus  { Open, Settled, Bridged, Cancelled }

    // ── Structs ────────────────────────────────────────────
    struct Trade {
        string   stationId;
        string   district;
        address payable seller;
        address  buyer;
        uint256  amount;         // milliMWh (MWh * 1000)
        uint256  pricePerUnit;   // wei per milliMWh
        ResourceType rType;
        TradeStatus  status;
        bool     exists;
    }

    // ── State ──────────────────────────────────────────────
    mapping(uint256 => Trade) public trades;
    uint256 public tradeCount;
    uint256 public constant PLATFORM_FEE = 0.001 ether; // Lower for L2

    // District-level counters
    mapping(string => uint256) public districtTradeCount;
    mapping(string => uint256) public districtMWhSettled;

    // ── On-chain idempotency (replaces Python seen_ids) ────
    // Maps Pub/Sub message_id hash → true if already settled
    mapping(bytes32 => bool) public settledMessages;
    uint256 public duplicatesBlocked;

    // ── Access control ─────────────────────────────────────
    address public owner;
    mapping(address => bool) public settlers;   // Authorized settler wallets
    bool public paused;

    // ── Events ─────────────────────────────────────────────
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

    event DuplicateBlocked(bytes32 indexed messageHash);
    event SettlerUpdated(address indexed settler, bool authorized);
    event Paused(bool isPaused);

    // ── Modifiers ──────────────────────────────────────────
    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    modifier onlySettler() {
        require(settlers[msg.sender], "Only settler");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "Contract paused");
        _;
    }

    /// @notice Idempotency guard — revert if this message was already settled
    modifier notDuplicate(string memory _messageId) {
        bytes32 h = keccak256(abi.encodePacked(_messageId));
        if (settledMessages[h]) {
            duplicatesBlocked++;
            emit DuplicateBlocked(h);
            revert("Duplicate message");
        }
        settledMessages[h] = true;
        _;
    }

    // ── Constructor ────────────────────────────────────────
    constructor() {
        owner = msg.sender;
        settlers[msg.sender] = true;  // Deployer is first settler
    }

    // ── Admin functions ────────────────────────────────────
    function setSettler(address _settler, bool _authorized) external onlyOwner {
        settlers[_settler] = _authorized;
        emit SettlerUpdated(_settler, _authorized);
    }

    function setPaused(bool _paused) external onlyOwner {
        paused = _paused;
        emit Paused(_paused);
    }

    function transferOwnership(address _newOwner) external onlyOwner {
        require(_newOwner != address(0), "Zero address");
        owner = _newOwner;
    }

    // ── List a resource for sale ───────────────────────────
    function listResource(
        string memory _id,
        string memory _district,
        uint256 _amount,
        uint256 _price,
        ResourceType _type
    ) public onlySettler whenNotPaused {
        tradeCount++;
        trades[tradeCount] = Trade({
            stationId: _id,
            district: _district,
            seller: payable(msg.sender),
            buyer: address(0),
            amount: _amount,
            pricePerUnit: _price,
            rType: _type,
            status: TradeStatus.Open,
            exists: true
        });

        districtTradeCount[_district]++;

        emit ResourceListed(tradeCount, _district, _id, _amount, _price, _type);
    }

    // ── Purchase a listed resource ─────────────────────────
    function purchaseResource(uint256 _tradeId) public payable onlySettler whenNotPaused {
        Trade storage t = trades[_tradeId];
        require(t.exists, "Trade does not exist");
        require(t.status == TradeStatus.Open, "Not open");

        uint256 totalCost = (t.amount * t.pricePerUnit) + PLATFORM_FEE;
        require(msg.value >= totalCost, "Insufficient payment");

        t.buyer = msg.sender;
        t.status = TradeStatus.Settled;
        districtMWhSettled[t.district] += t.amount;

        // Transfer payment to seller
        t.seller.transfer(t.amount * t.pricePerUnit);

        emit ResourcePurchased(_tradeId, t.district, msg.sender, t.pricePerUnit);
    }

    // ── Bridge: cross-district purchase ────────────────────
    function bridgeResource(
        uint256 _tradeId,
        string memory _toDistrict
    ) public payable onlySettler whenNotPaused {
        Trade storage t = trades[_tradeId];
        require(t.exists, "Trade does not exist");
        require(t.status == TradeStatus.Open, "Not open");

        uint256 totalCost = (t.amount * t.pricePerUnit) + (PLATFORM_FEE * 2);
        require(msg.value >= totalCost, "Insufficient payment");

        t.buyer = msg.sender;
        t.status = TradeStatus.Bridged;
        districtMWhSettled[t.district] += t.amount;

        // Transfer payment to seller
        t.seller.transfer(t.amount * t.pricePerUnit);

        emit ResourceBridged(_tradeId, t.district, _toDistrict, msg.sender, t.pricePerUnit);
    }

    // ── Atomic settle: list + purchase in one tx ───────────
    // Saves gas on L2 by combining two calls into one
    function settleTrade(
        string memory _messageId,
        string memory _stationId,
        string memory _district,
        uint256 _amount,
        uint256 _price,
        ResourceType _type
    ) external payable onlySettler whenNotPaused notDuplicate(_messageId) {

        // List
        tradeCount++;
        trades[tradeCount] = Trade({
            stationId: _stationId,
            district: _district,
            seller: payable(msg.sender),
            buyer: msg.sender,     // Same settler wallet acts as both
            amount: _amount,
            pricePerUnit: _price,
            rType: _type,
            status: TradeStatus.Settled,
            exists: true
        });

        districtTradeCount[_district]++;
        districtMWhSettled[_district] += _amount;

        emit ResourceListed(tradeCount, _district, _stationId, _amount, _price, _type);
        emit ResourcePurchased(tradeCount, _district, msg.sender, _price);
    }

    // ── Atomic bridge settle ───────────────────────────────
    function settleBridge(
        string memory _messageId,
        string memory _stationId,
        string memory _fromDistrict,
        string memory _toDistrict,
        uint256 _amount,
        uint256 _price,
        ResourceType _type
    ) external payable onlySettler whenNotPaused notDuplicate(_messageId) {

        tradeCount++;
        trades[tradeCount] = Trade({
            stationId: _stationId,
            district: _fromDistrict,
            seller: payable(msg.sender),
            buyer: msg.sender,
            amount: _amount,
            pricePerUnit: _price,
            rType: _type,
            status: TradeStatus.Bridged,
            exists: true
        });

        districtTradeCount[_fromDistrict]++;
        districtMWhSettled[_fromDistrict] += _amount;

        emit ResourceListed(tradeCount, _fromDistrict, _stationId, _amount, _price, _type);
        emit ResourceBridged(tradeCount, _fromDistrict, _toDistrict, msg.sender, _price);
    }

    // ── Batch settlement ──────────────────────────────────
    // Aggregates net energy delta per building into 1 bulk tx
    // Called once per hour instead of per-trade

    struct BatchEntry {
        string   messageId;      // Pub/Sub dedup key
        string   stationId;      // Building / seller ID
        string   district;       // "IL_D91" or "McHenry_D63"
        uint256  amount;         // Net milliMWh for this building
        uint256  price;          // Volume-weighted avg price
        ResourceType rType;
        bool     isBridge;
        string   toDistrict;     // Only used if isBridge == true
    }

    event BatchSettled(
        uint256 indexed batchSize,
        uint256 totalAmount,
        uint256 firstTradeId,
        uint256 lastTradeId
    );

    /// @notice Settle an array of trades in one transaction.
    ///         Each entry is idempotency-checked individually.
    ///         Entries with duplicate messageIds are skipped (not reverted)
    ///         so one bad entry doesn't kill the whole batch.
    /// @return settled Number of entries actually settled (excludes dupes)
    function settleBatch(
        BatchEntry[] calldata entries
    ) external payable onlySettler whenNotPaused returns (uint256 settled) {
        require(entries.length > 0, "Empty batch");
        require(entries.length <= 200, "Batch too large");  // Gas safety

        uint256 firstId = tradeCount + 1;
        uint256 totalAmount = 0;
        settled = 0;

        for (uint256 i = 0; i < entries.length; i++) {
            // Per-entry idempotency (skip, don't revert)
            bytes32 h = keccak256(abi.encodePacked(entries[i].messageId));
            if (settledMessages[h]) {
                duplicatesBlocked++;
                emit DuplicateBlocked(h);
                continue;  // Skip this entry, settle the rest
            }
            settledMessages[h] = true;

            tradeCount++;

            TradeStatus st = entries[i].isBridge
                ? TradeStatus.Bridged
                : TradeStatus.Settled;

            trades[tradeCount] = Trade({
                stationId: entries[i].stationId,
                district:  entries[i].district,
                seller:    payable(msg.sender),
                buyer:     msg.sender,
                amount:    entries[i].amount,
                pricePerUnit: entries[i].price,
                rType:     entries[i].rType,
                status:    st,
                exists:    true
            });

            districtTradeCount[entries[i].district]++;
            districtMWhSettled[entries[i].district] += entries[i].amount;
            totalAmount += entries[i].amount;
            settled++;

            emit ResourceListed(
                tradeCount, entries[i].district, entries[i].stationId,
                entries[i].amount, entries[i].price, entries[i].rType
            );

            if (entries[i].isBridge) {
                emit ResourceBridged(
                    tradeCount, entries[i].district, entries[i].toDistrict,
                    msg.sender, entries[i].price
                );
            } else {
                emit ResourcePurchased(
                    tradeCount, entries[i].district, msg.sender, entries[i].price
                );
            }
        }

        if (settled > 0) {
            emit BatchSettled(settled, totalAmount, firstId, tradeCount);
        }
    }

    // ── View helpers ───────────────────────────────────────
    function isSettled(string memory _messageId) external view returns (bool) {
        return settledMessages[keccak256(abi.encodePacked(_messageId))];
    }

    function getTradeStatus(uint256 _tradeId) external view returns (TradeStatus) {
        require(trades[_tradeId].exists, "Trade does not exist");
        return trades[_tradeId].status;
    }

    // ── Withdraw accumulated platform fees ─────────────────
    function withdrawFees() external onlyOwner {
        payable(owner).transfer(address(this).balance);
    }

    receive() external payable {}
}
