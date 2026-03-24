"""
TINY-HUB-NETWORK — On-Chain Trade Settler
Subscribes to both Pub/Sub topics (energy-pulse + district91-energy).
When a trade is SETTLED, it:
  1. Seller wallet calls listResource() on TinyHubMarketV2
  2. Buyer wallet calls purchaseResource() with ETH
  3. Logs the on-chain trade ID

Connects to the local Hardhat node at http://127.0.0.1:8545
Uses Hardhat's pre-funded test accounts.

Run:
  # Terminal 1: Make sure Hardhat node is running
  npx hardhat node

  # Terminal 2: Run the settler
  python3 d91_settler.py

Requires: pip install web3 --break-system-packages
"""

import os
import json
import time
import threading
from datetime import datetime
from collections import deque
from web3 import Web3
from google.cloud import pubsub_v1

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = "tiny-hub-network"
# Pub/Sub
D63_TOPIC = "energy-pulse"
D91_TOPIC = "district91-energy"
SETTLER_D63_SUB = "energy-pulse-settler-sub"
SETTLER_D91_SUB = "district91-energy-settler-sub"

# Hardhat local node
RPC_URL = os.environ.get("RPC_URL", "http://127.0.0.1:8545")
CONTRACT_ADDRESS = None  # loaded from deployment.json

# Load deployment address
if os.path.exists("deployment.json"):
    with open("deployment.json") as f:
        dep = json.load(f)
    CONTRACT_ADDRESS = dep.get("TinyHubMarketV2")
    # Token address — check both formats from different deploy scripts
    TOKEN_ADDRESS = None
    if "contracts" in dep and "TinyHubToken" in dep["contracts"]:
        TOKEN_ADDRESS = dep["contracts"]["TinyHubToken"]["address"]
    elif "TinyHubToken" in dep:
        TOKEN_ADDRESS = dep["TinyHubToken"]
    print(f"  Contract: {CONTRACT_ADDRESS}")
    print(f"  Token:    {TOKEN_ADDRESS}")
else:
    print("  ❌ deployment.json not found — run deploy_v2.js first")
    exit(1)

# ── TinyHubMarketV2 ABI (minimal — just what we need) ──────
CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "string", "name": "_id", "type": "string"},
            {"internalType": "string", "name": "_district", "type": "string"},
            {"internalType": "uint256", "name": "_amount", "type": "uint256"},
            {"internalType": "uint256", "name": "_price", "type": "uint256"},
            {"internalType": "enum TinyHubMarketV2.ResourceType", "name": "_type", "type": "uint8"}
        ],
        "name": "listResource",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "_tradeId", "type": "uint256"}
        ],
        "name": "purchaseResource",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "_tradeId", "type": "uint256"},
            {"internalType": "string", "name": "_buyerDistrict", "type": "string"}
        ],
        "name": "bridgeResource",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "tradeCount",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "PLATFORM_FEE",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "string", "name": "", "type": "string"}],
        "name": "districtTradeCount",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "string", "name": "", "type": "string"}],
        "name": "districtMWhSettled",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    # Events
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tradeId", "type": "uint256"},
            {"indexed": False, "internalType": "string", "name": "district", "type": "string"},
            {"indexed": False, "internalType": "string", "name": "stationId", "type": "string"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "pricePerUnit", "type": "uint256"},
            {"indexed": False, "internalType": "enum TinyHubMarketV2.ResourceType", "name": "rType", "type": "uint8"}
        ],
        "name": "ResourceListed",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tradeId", "type": "uint256"},
            {"indexed": False, "internalType": "string", "name": "district", "type": "string"},
            {"indexed": False, "internalType": "address", "name": "buyer", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "settledPrice", "type": "uint256"}
        ],
        "name": "ResourcePurchased",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tradeId", "type": "uint256"},
            {"indexed": False, "internalType": "string", "name": "fromDistrict", "type": "string"},
            {"indexed": False, "internalType": "string", "name": "toDistrict", "type": "string"},
            {"indexed": False, "internalType": "address", "name": "buyer", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "settledPrice", "type": "uint256"}
        ],
        "name": "ResourceBridged",
        "type": "event"
    },
]

# ── Web3 Setup ──────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print("  ❌ Cannot connect to Hardhat node at", RPC_URL)
    print("  Start it with: npx hardhat node")
    exit(1)

contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
platform_fee = contract.functions.PLATFORM_FEE().call()

# ── TinyHubToken (THN) Setup ────────────────────────────────
TOKEN_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "_to", "type": "address"},
            {"internalType": "uint256", "name": "_amount", "type": "uint256"},
            {"internalType": "string", "name": "_stationId", "type": "string"}
        ],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "_from", "type": "address"},
            {"internalType": "uint256", "name": "_amount", "type": "uint256"},
            {"internalType": "string", "name": "_reason", "type": "string"}
        ],
        "name": "burn",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    },
]

token_contract = None
if TOKEN_ADDRESS:
    try:
        token_contract = w3.eth.contract(address=TOKEN_ADDRESS, abi=TOKEN_ABI)
        symbol = token_contract.functions.symbol().call()
        supply = token_contract.functions.totalSupply().call()
        print(f"  Token:     {symbol} at {TOKEN_ADDRESS}")
        print(f"  Supply:    {w3.from_wei(supply, 'ether')} {symbol}")
    except Exception as e:
        print(f"  ⚠️  Token contract error: {e}")
        token_contract = None
else:
    print("  ⚠️  No THN token address found — minting disabled")

# Hardhat test accounts (first 10 pre-funded with 10000 ETH each)
accounts = w3.eth.accounts
SELLER_ACCOUNT = accounts[0]   # Also the deployer
BUYER_ACCOUNT = accounts[1]    # Dedicated buyer wallet

print(f"  Seller wallet: {SELLER_ACCOUNT}")
print(f"  Buyer wallet:  {BUYER_ACCOUNT}")
print(f"  Platform fee:  {w3.from_wei(platform_fee, 'ether')} ETH")

# ── Counters ────────────────────────────────────────────────
stats = {
    "listed": 0,
    "settled_onchain": 0,
    "bridged_onchain": 0,
    "failed": 0,
    "skipped": 0,
    "duplicates": 0,
    "gas_used": 0,
    "thn_minted": 0.0,
    "thn_burned": 0.0,
}
stats_lock = threading.Lock()

# ── Idempotency: deduplicate Pub/Sub at-least-once delivery ─
# Pub/Sub guarantees at-least-once — the same message_id can
# arrive twice during network hiccups or subscriber restarts.
# We keep a bounded in-memory set of seen message IDs.
# On L2 deploy this moves into the smart contract (on-chain mapping).
MAX_SEEN_IDS = 10_000   # ~10K trades ≈ a few hours of history
seen_ids: set[str] = set()
seen_ids_order: list[str] = []   # FIFO eviction queue
seen_ids_lock = threading.Lock()


def is_duplicate(message_id: str) -> bool:
    """Return True if this message_id has already been processed."""
    with seen_ids_lock:
        if message_id in seen_ids:
            return True
        # Record it
        seen_ids.add(message_id)
        seen_ids_order.append(message_id)
        # Evict oldest if over limit
        while len(seen_ids_order) > MAX_SEEN_IDS:
            evicted = seen_ids_order.pop(0)
            seen_ids.discard(evicted)
        return False
recent_txs = deque(maxlen=50)
# ── Nonce Manager (Task #2 fix) ─────────────────────────────
# Prevents nonce collisions when multiple Pub/Sub messages arrive
# concurrently. Tracks the pending nonce locally instead of
# querying the chain each time (which returns the confirmed count,
# not the pending count).
chain_lock = threading.Lock()  # Serialize ALL on-chain operations

class NonceManager:
    """Thread-safe local nonce tracker per account."""
    def __init__(self, w3_instance):
        self._w3 = w3_instance
        self._nonces = {}  # account_address -> next_nonce
        self._lock = threading.Lock()

    def get_nonce(self, account: str) -> int:
        """Get the next nonce for an account. Call inside chain_lock."""
        with self._lock:
            if account not in self._nonces:
                # First call: sync from chain
                self._nonces[account] = self._w3.eth.get_transaction_count(account)
            nonce = self._nonces[account]
            self._nonces[account] += 1
            return nonce

    def resync(self, account: str):
        """Resync nonce from chain after a failure."""
        with self._lock:
            self._nonces[account] = self._w3.eth.get_transaction_count(account)

    def reset_all(self):
        """Clear all tracked nonces (force resync on next call)."""
        with self._lock:
            self._nonces.clear()

nonce_mgr = NonceManager(w3)


# ── Settle a trade on-chain ─────────────────────────────────
def settle_onchain(trade):
    """
    Two-step on-chain settlement with nonce management.
    Serialized via chain_lock to prevent nonce collisions.

    Steps:
      1. Seller calls listResource()
      2. Buyer calls purchaseResource() (or bridgeResource())
      3. Mint THN tokens to seller
      4. Burn toll from seller

    Retries once on failure with nonce resync.
    """
    with chain_lock:
        return _settle_onchain_inner(trade, retry=True)


def _settle_onchain_inner(trade, retry=True):
    """Inner settlement logic — always called inside chain_lock."""
    station_id = trade.get("station_id", "unknown")
    district = trade.get("district", "IL_D91")
    mwh = trade.get("mwh", 0)
    settled_price = trade.get("settled_price", 0)
    is_bridge = trade.get("trade_status") == "BRIDGE_LISTED"

    amount_milli = int(mwh * 1000)
    if amount_milli <= 0:
        return None

    price_wei = int(settled_price * 10000)
    if price_wei <= 0:
        price_wei = 1

    try:
        # Step 1: Seller lists the resource
        seller_nonce = nonce_mgr.get_nonce(SELLER_ACCOUNT)
        tx_list = contract.functions.listResource(
            station_id,
            district,
            amount_milli,
            price_wei,
            0  # ResourceType.Energy
        ).build_transaction({
            "from": SELLER_ACCOUNT,
            "nonce": seller_nonce,
            "gas": 300000,
            "gasPrice": w3.eth.gas_price,
        })
        tx_hash_list = w3.eth.send_transaction(tx_list)
        receipt_list = w3.eth.wait_for_transaction_receipt(tx_hash_list, timeout=30)

        trade_id = contract.functions.tradeCount().call()

        # Step 2: Buyer purchases (or bridges)
        buyer_nonce = nonce_mgr.get_nonce(BUYER_ACCOUNT)
        total_cost = (amount_milli * price_wei) + platform_fee

        if is_bridge:
            buyer_district = trade.get("origin_district", "McHenry_D63")
            total_cost = (amount_milli * price_wei) + (platform_fee * 2)
            tx_buy = contract.functions.bridgeResource(
                trade_id,
                buyer_district
            ).build_transaction({
                "from": BUYER_ACCOUNT,
                "nonce": buyer_nonce,
                "gas": 300000,
                "gasPrice": w3.eth.gas_price,
                "value": total_cost,
            })
        else:
            tx_buy = contract.functions.purchaseResource(
                trade_id
            ).build_transaction({
                "from": BUYER_ACCOUNT,
                "nonce": buyer_nonce,
                "gas": 300000,
                "gasPrice": w3.eth.gas_price,
                "value": total_cost,
            })

        tx_hash_buy = w3.eth.send_transaction(tx_buy)
        receipt_buy = w3.eth.wait_for_transaction_receipt(tx_hash_buy, timeout=30)

        total_gas = receipt_list.gasUsed + receipt_buy.gasUsed

        # Step 3 & 4: Mint THN + burn toll (non-critical)
        thn_minted = 0.0
        thn_burned = 0.0
        if token_contract:
            try:
                token_amount = int(mwh * 1e18)
                toll = int(0.02 * 1e18)  # Grid toll in THN

                mint_nonce = nonce_mgr.get_nonce(SELLER_ACCOUNT)
                tx_mint = token_contract.functions.mint(
                    SELLER_ACCOUNT,
                    token_amount,
                    station_id
                ).build_transaction({
                    "from": SELLER_ACCOUNT,
                    "nonce": mint_nonce,
                    "gas": 200000,
                    "gasPrice": w3.eth.gas_price,
                })
                w3.eth.send_transaction(tx_mint)

                burn_nonce = nonce_mgr.get_nonce(SELLER_ACCOUNT)
                tx_burn = token_contract.functions.burn(
                    SELLER_ACCOUNT,
                    toll,
                    "grid_toll"
                ).build_transaction({
                    "from": SELLER_ACCOUNT,
                    "nonce": burn_nonce,
                    "gas": 200000,
                    "gasPrice": w3.eth.gas_price,
                })
                w3.eth.send_transaction(tx_burn)

                thn_minted = mwh
                thn_burned = 0.02
            except Exception as te:
                print(f"  ⚠️  Token ops failed (non-critical): {te}")

        # Update stats
        with stats_lock:
            if is_bridge:
                stats["bridged_onchain"] += 1
            else:
                stats["settled_onchain"] += 1
            stats["listed"] += 1
            stats["gas_used"] += total_gas
            stats["thn_minted"] += thn_minted
            stats["thn_burned"] += thn_burned

        result = {
            "trade_id": trade_id,
            "tx_list": tx_hash_list.hex(),
            "tx_buy": tx_hash_buy.hex(),
            "gas": total_gas,
            "type": "BRIDGE" if is_bridge else "SETTLE",
            "thn_minted": thn_minted,
            "thn_burned": thn_burned,
        }
        recent_txs.appendleft(result)
        return result

    except Exception as e:
        if retry and ("nonce" in str(e).lower() or "underpriced" in str(e).lower()):
            # Nonce desync — resync and retry once
            print(f"  ⚠️  Nonce error, resyncing: {e}")
            nonce_mgr.resync(SELLER_ACCOUNT)
            nonce_mgr.resync(BUYER_ACCOUNT)
            return _settle_onchain_inner(trade, retry=False)
        else:
            with stats_lock:
                stats["failed"] += 1
            print(f"  ❌ Settlement failed: {e}")
            # Resync nonces even on non-retry failure
            nonce_mgr.resync(SELLER_ACCOUNT)
            nonce_mgr.resync(BUYER_ACCOUNT)
            return {"error": str(e)}


# ── Pub/Sub Callbacks ───────────────────────────────────────
def on_trade(message, source):
    message.ack()

    # ── Idempotency check ───────────────────────────────────
    if is_duplicate(message.message_id):
        with stats_lock:
            stats["duplicates"] += 1
        return  # Already settled — do NOT mint again

    try:
        trade = json.loads(message.data.decode("utf-8"))
    except:
        return

    status = trade.get("trade_status", "")

    # Only settle SETTLED, ISLAND_SETTLED, or BRIDGE_LISTED trades
    if status not in ("SETTLED", "ISLAND_SETTLED", "BRIDGE_LISTED"):
        with stats_lock:
            stats["skipped"] += 1
        return

    result = settle_onchain(trade)

    if result and "error" not in result:
        seller = (trade.get("seller_label") or trade.get("station_id", "?"))[:25]
        icon = "🌉" if result["type"] == "BRIDGE" else "⛓"
        thn = result.get("thn_minted", 0)
        thn_b = result.get("thn_burned", 0)
        thn_str = f" | 🪙 +{thn:.3f} THN -{thn_b:.3f} burned" if thn > 0 else ""
        print(f"  {icon} #{result['trade_id']:>5} | {source} | {seller:25} | {trade.get('mwh',0):.3f} MWh | Gas: {result['gas']:>6}{thn_str}")
    elif result:
        print(f"  ❌ {source} | Failed: {result['error'][:60]}")


def d63_callback(message):
    on_trade(message, "D63")

def d91_callback(message):
    on_trade(message, "D91")


# ── Scoreboard ──────────────────────────────────────────────
def print_scoreboard():
    while True:
        time.sleep(30)
        with stats_lock:
            s = dict(stats)

        # Query on-chain stats
        try:
            chain_count = contract.functions.tradeCount().call()
            d63_count = contract.functions.districtTradeCount("McHenry_D63").call()
            d91_count = contract.functions.districtTradeCount("IL_D91").call()
            d63_mwh = contract.functions.districtMWhSettled("McHenry_D63").call()
            d91_mwh = contract.functions.districtMWhSettled("IL_D91").call()
        except:
            chain_count = d63_count = d91_count = d63_mwh = d91_mwh = "?"

        # Query THN supply
        thn_supply = "?"
        if token_contract:
            try:
                raw = token_contract.functions.totalSupply().call()
                thn_supply = f"{float(w3.from_wei(raw, 'ether')):.3f}"
            except:
                pass

        print()
        print(f"  ╔═══════════════════════════════════════════════════════════════════════╗")
        print(f"  ║  ON-CHAIN SETTLER — {datetime.utcnow().strftime('%H:%M:%S UTC'):>12}                                ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  Listed on-chain:     {s['listed']:>6}                                         ║")
        print(f"  ║  Settled on-chain:    {s['settled_onchain']:>6}                                         ║")
        print(f"  ║  Bridged on-chain:    {s['bridged_onchain']:>6}                                         ║")
        print(f"  ║  Failed:              {s['failed']:>6}                                         ║")
        print(f"  ║  Skipped (rejected):  {s['skipped']:>6}                                         ║")
        print(f"  ║  Duplicates blocked:  {s['duplicates']:>6}                                         ║")
        print(f"  ║  Total gas used:      {s['gas_used']:>10,}                                     ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  CONTRACT STATE                                                      ║")
        print(f"  ║  Total trades:        {str(chain_count):>6}                                         ║")
        print(f"  ║  D63 trades:          {str(d63_count):>6}  |  D63 MWh: {str(d63_mwh):>10}              ║")
        print(f"  ║  D91 trades:          {str(d91_count):>6}  |  D91 MWh: {str(d91_mwh):>10}              ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  🪙 THN TOKEN                                                        ║")
        print(f"  ║  Total supply:   {str(thn_supply):>10} THN                                     ║")
        print(f"  ║  Minted:         {s['thn_minted']:>10.3f} THN  (1 THN = 1 MWh)                 ║")
        print(f"  ║  Burned (tolls): {s['thn_burned']:>10.3f} THN                                  ║")
        print(f"  ╚═══════════════════════════════════════════════════════════════════════╝")
        print()


# ── Setup ───────────────────────────────────────────────────
print()
print("  ╔═══════════════════════════════════════════════════════════════════════╗")
print("  ║     TINY-HUB-NETWORK — On-Chain Trade Settler                       ║")
print("  ║     Pub/Sub → TinyHubMarketV2 (Hardhat Local)                        ║")
print("  ╠═══════════════════════════════════════════════════════════════════════╣")
print(f"  ║  Contract:  {CONTRACT_ADDRESS}       ║")
print(f"  ║  Token:     {TOKEN_ADDRESS or 'NOT FOUND':42}       ║")
print(f"  ║  RPC:       {RPC_URL:>45}       ║")
print(f"  ║  Chain ID:  {w3.eth.chain_id:>45}       ║")
print(f"  ║  Seller:    {SELLER_ACCOUNT}       ║")
print(f"  ║  Buyer:     {BUYER_ACCOUNT}       ║")
print("  ╠═══════════════════════════════════════════════════════════════════════╣")
print("  ║  Listening on:                                                       ║")
print(f"  ║    {D63_TOPIC:>25}  →  listResource + purchaseResource     ║")
print(f"  ║    {D91_TOPIC:>25}  →  listResource + purchaseResource     ║")
print("  ╚═══════════════════════════════════════════════════════════════════════╝")
print()

# ── Create settler subscriptions ────────────────────────────
subscriber = pubsub_v1.SubscriberClient()
publisher = pubsub_v1.PublisherClient()

for sub_id, topic_id in [(SETTLER_D63_SUB, D63_TOPIC), (SETTLER_D91_SUB, D91_TOPIC)]:
    sub_path = subscriber.subscription_path(PROJECT_ID, sub_id)
    topic_path = publisher.topic_path(PROJECT_ID, topic_id)
    try:
        subscriber.create_subscription(
            request={"name": sub_path, "topic": topic_path, "ack_deadline_seconds": 60}
        )
        print(f"  ✅ Created {sub_id}")
    except Exception as e:
        if "ALREADY_EXISTS" in str(e) or "lready" in str(e):
            print(f"  ⏭️  {sub_id} exists")
        else:
            print(f"  ❌ {sub_id}: {e}")
            raise

# ── Subscribe ───────────────────────────────────────────────
flow = pubsub_v1.types.FlowControl(max_messages=1)  # Serialize to prevent nonce races  # Throttle to avoid nonce issues

d63_sub_path = subscriber.subscription_path(PROJECT_ID, SETTLER_D63_SUB)
d91_sub_path = subscriber.subscription_path(PROJECT_ID, SETTLER_D91_SUB)

subscriber.subscribe(d63_sub_path, callback=d63_callback, flow_control=flow)
subscriber.subscribe(d91_sub_path, callback=d91_callback, flow_control=flow)
print("  ✅ Subscribed — settling trades on-chain")
print()

# Start scoreboard
threading.Thread(target=print_scoreboard, daemon=True).start()

print("  ⛓ Settler active. Ctrl+C to stop.")
print("  ─────────────────────────────────────────────────────────────────")
print()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    with stats_lock:
        s = dict(stats)
    print()
    print("  ╔═══════════════════════════════════════════════════════════════════════╗")
    print("  ║                   SETTLER FINAL REPORT                               ║")
    print("  ╠═══════════════════════════════════════════════════════════════════════╣")
    print(f"  ║  Listed on-chain:     {s['listed']:>6}                                         ║")
    print(f"  ║  Settled on-chain:    {s['settled_onchain']:>6}                                         ║")
    print(f"  ║  Bridged on-chain:    {s['bridged_onchain']:>6}                                         ║")
    print(f"  ║  Failed:              {s['failed']:>6}                                         ║")
    print(f"  ║  Skipped:             {s['skipped']:>6}                                         ║")
    print(f"  ║  Total gas:           {s['gas_used']:>10,}                                     ║")
    print("  ╚═══════════════════════════════════════════════════════════════════════╝")
