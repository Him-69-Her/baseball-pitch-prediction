"""
TINY-HUB-NETWORK — Batch On-Chain Settler
==========================================
Replaces per-trade settlement with hourly batch aggregation.

Trades arrive via Pub/Sub → buffered in memory → flushed to chain
every BATCH_INTERVAL_SEC (default: 1 hour).

Each flush:
  1. Aggregate net MWh per seller (building)
  2. One listResource() per seller
  3. One purchaseResource() per batch
  4. Bulk mint THN (1 THN = 1 MWh)
  5. Bulk burn tolls

Gas savings: ~95% vs per-trade settlement.

Modes:
  DOCKER:  Pub/Sub streaming subscriber + timer thread
  CLOUD:   Cloud Functions gen 2 (Pub/Sub push + Scheduler trigger)

Run:
  python3 -u batch_settler.py
"""

import os
import json
import time
import threading
from datetime import datetime, timezone
from collections import defaultdict, deque
from web3 import Web3

# ── Optional: Pub/Sub ───────────────────────────────────────
try:
    from google.cloud import pubsub_v1
    HAS_PUBSUB = True
except ImportError:
    HAS_PUBSUB = False

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "tinyhub-data-dev")
D63_TOPIC = "energy-pulse"
D91_TOPIC = "district91-energy"
SETTLER_D63_SUB = "energy-pulse-batch-settler-sub"
SETTLER_D91_SUB = "district91-energy-batch-settler-sub"

RPC_URL = os.environ.get("RPC_URL", "http://127.0.0.1:8545")
BATCH_INTERVAL_SEC = int(os.environ.get("BATCH_INTERVAL_SEC", "3600"))  # 1 hour
MIN_BATCH_SIZE = int(os.environ.get("MIN_BATCH_SIZE", "1"))  # flush even if 1 trade

# ── Blockchain ──────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print(f"  ❌ Cannot connect to blockchain at {RPC_URL}")
    exit(1)

# Load deployment
CONTRACT_ADDRESS = None
TOKEN_ADDRESS = None

if os.path.exists("deployment.json"):
    with open("deployment.json") as f:
        dep = json.load(f)
    if "contracts" in dep:
        CONTRACT_ADDRESS = dep["contracts"]["TinyHubMarket"]["address"]
        TOKEN_ADDRESS = dep["contracts"].get("TinyHubToken", {}).get("address")
    elif "TinyHubMarketV2" in dep:
        CONTRACT_ADDRESS = dep["TinyHubMarketV2"]
        TOKEN_ADDRESS = dep.get("TinyHubToken")
    else:
        CONTRACT_ADDRESS = dep.get("address")
else:
    print("  ❌ deployment.json not found")
    exit(1)

# Load contract ABIs
if os.path.exists("TinyHubMarket.json"):
    with open("TinyHubMarket.json") as f:
        market_artifact = json.load(f)
    contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=market_artifact["abi"])
else:
    print("  ❌ TinyHubMarket.json not found")
    exit(1)

# Token contract (optional)
token_contract = None
TOKEN_ABI = [
    {"inputs":[{"type":"address"},{"type":"uint256"},{"type":"string"}],"name":"mint","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"type":"address"},{"type":"uint256"},{"type":"string"}],"name":"burn","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"totalSupply","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"symbol","outputs":[{"type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"type":"address"}],"name":"balanceOf","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
]
if TOKEN_ADDRESS:
    try:
        token_contract = w3.eth.contract(address=TOKEN_ADDRESS, abi=TOKEN_ABI)
        print(f"  Token: {token_contract.functions.symbol().call()} at {TOKEN_ADDRESS}")
    except Exception as e:
        print(f"  ⚠️  Token contract error: {e}")

platform_fee = contract.functions.PLATFORM_FEE().call()
accounts = w3.eth.accounts
SELLER_ACCOUNT = accounts[0]
BUYER_ACCOUNT = accounts[1]

# ── Nonce Manager ───────────────────────────────────────────
chain_lock = threading.Lock()

class NonceManager:
    def __init__(self, w3_instance):
        self._w3 = w3_instance
        self._nonces = {}
        self._lock = threading.Lock()

    def get_nonce(self, account):
        with self._lock:
            if account not in self._nonces:
                self._nonces[account] = self._w3.eth.get_transaction_count(account)
            nonce = self._nonces[account]
            self._nonces[account] += 1
            return nonce

    def resync(self, account):
        with self._lock:
            self._nonces[account] = self._w3.eth.get_transaction_count(account)

nonce_mgr = NonceManager(w3)

# ── Trade Buffer ────────────────────────────────────────────
# Aggregates trades by seller (station_id) per batch window
trade_buffer = defaultdict(lambda: {
    "mwh": 0.0,
    "trades": 0,
    "total_value": 0.0,
    "co2_tons": 0.0,
    "district": "",
    "label": "",
    "last_price": 0.0,
    "bridge_count": 0,
})
buffer_lock = threading.Lock()

# Stats
stats = {
    "trades_buffered": 0,
    "batches_flushed": 0,
    "buildings_settled": 0,
    "total_mwh": 0.0,
    "total_gas": 0,
    "failed": 0,
    "thn_minted": 0.0,
    "thn_burned": 0.0,
}
stats_lock = threading.Lock()

# Idempotency
seen_ids = set()
seen_ids_order = []
seen_ids_lock = threading.Lock()
MAX_SEEN = 10000

def is_duplicate(msg_id):
    with seen_ids_lock:
        if msg_id in seen_ids:
            return True
        seen_ids.add(msg_id)
        seen_ids_order.append(msg_id)
        while len(seen_ids_order) > MAX_SEEN:
            seen_ids.discard(seen_ids_order.pop(0))
        return False


# ── Buffer a trade ──────────────────────────────────────────
def buffer_trade(trade):
    """Add a trade to the aggregation buffer."""
    station_id = trade.get("station_id", "unknown")
    mwh = trade.get("mwh", 0)
    price = trade.get("settled_price", 0)
    co2 = trade.get("co2_tons", mwh * 0.42)
    district = trade.get("district", "IL_D91")
    label = trade.get("seller_label", station_id)
    is_bridge = trade.get("trade_status") == "BRIDGE_LISTED"

    with buffer_lock:
        b = trade_buffer[station_id]
        b["mwh"] += mwh
        b["trades"] += 1
        b["total_value"] += mwh * price
        b["co2_tons"] += co2
        b["district"] = district
        b["label"] = label
        b["last_price"] = price
        if is_bridge:
            b["bridge_count"] += 1

    with stats_lock:
        stats["trades_buffered"] += 1


# ── Flush batch to chain ───────────────────────────────────
def flush_batch():
    """Aggregate buffered trades and settle on-chain in bulk."""
    with buffer_lock:
        if not trade_buffer:
            return
        # Snapshot and clear
        batch = dict(trade_buffer)
        trade_buffer.clear()

    total_buildings = len(batch)
    total_mwh = sum(b["mwh"] for b in batch.values())
    total_trades = sum(b["trades"] for b in batch.values())

    print()
    print(f"  ╔═══════════════════════════════════════════════════════════╗")
    print(f"  ║  BATCH FLUSH — {datetime.now(timezone.utc).strftime('%H:%M:%S UTC'):>12}                        ║")
    print(f"  ║  Buildings: {total_buildings:>4}  |  Trades: {total_trades:>6}  |  MWh: {total_mwh:>8.2f}  ║")
    print(f"  ╚═══════════════════════════════════════════════════════════╝")

    with chain_lock:
        nonce_mgr.resync(SELLER_ACCOUNT)
        nonce_mgr.resync(BUYER_ACCOUNT)

        batch_gas = 0
        batch_minted = 0.0
        batch_burned = 0.0
        settled_count = 0

        for station_id, data in batch.items():
            mwh = data["mwh"]
            if mwh <= 0:
                continue

            avg_price = data["total_value"] / mwh if mwh > 0 else 0
            district = data["district"]
            amount_milli = int(mwh * 1000)
            price_wei = int(avg_price * 10000)
            if price_wei <= 0:
                price_wei = 1

            try:
                # Step 1: Bulk list for this seller
                seller_nonce = nonce_mgr.get_nonce(SELLER_ACCOUNT)
                tx_list = contract.functions.listResource(
                    station_id, amount_milli, price_wei, 0
                ).build_transaction({
                    "from": SELLER_ACCOUNT,
                    "nonce": seller_nonce,
                    "gas": 300000,
                    "gasPrice": w3.eth.gas_price,
                })
                tx_hash = w3.eth.send_transaction(tx_list)
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
                batch_gas += receipt.gasUsed

                trade_id = contract.functions.tradeCount().call()

                # Step 2: Bulk purchase
                buyer_nonce = nonce_mgr.get_nonce(BUYER_ACCOUNT)
                total_cost = (amount_milli * price_wei) + platform_fee
                tx_buy = contract.functions.purchaseResource(trade_id).build_transaction({
                    "from": BUYER_ACCOUNT,
                    "nonce": buyer_nonce,
                    "gas": 300000,
                    "gasPrice": w3.eth.gas_price,
                    "value": total_cost,
                })
                tx_hash_buy = w3.eth.send_transaction(tx_buy)
                receipt_buy = w3.eth.wait_for_transaction_receipt(tx_hash_buy, timeout=30)
                batch_gas += receipt_buy.gasUsed

                # Step 3: Bulk mint THN
                if token_contract:
                    try:
                        token_amount = int(mwh * 1e18)
                        toll_amount = int(0.02 * data["trades"] * 1e18)  # toll per trade

                        mint_nonce = nonce_mgr.get_nonce(SELLER_ACCOUNT)
                        tx_mint = token_contract.functions.mint(
                            SELLER_ACCOUNT, token_amount, f"batch:{station_id}"
                        ).build_transaction({
                            "from": SELLER_ACCOUNT, "nonce": mint_nonce,
                            "gas": 200000, "gasPrice": w3.eth.gas_price,
                        })
                        w3.eth.send_transaction(tx_mint)
                        batch_minted += mwh

                        burn_nonce = nonce_mgr.get_nonce(SELLER_ACCOUNT)
                        tx_burn = token_contract.functions.burn(
                            SELLER_ACCOUNT, toll_amount, f"toll:{station_id}"
                        ).build_transaction({
                            "from": SELLER_ACCOUNT, "nonce": burn_nonce,
                            "gas": 200000, "gasPrice": w3.eth.gas_price,
                        })
                        w3.eth.send_transaction(tx_burn)
                        batch_burned += 0.02 * data["trades"]
                    except Exception as te:
                        print(f"  ⚠️  Token ops failed for {station_id}: {te}")

                settled_count += 1
                label = data["label"][:25]
                print(f"  ⛓  #{trade_id:>5} | {label:25} | {mwh:.3f} MWh ({data['trades']} trades) | ${avg_price:.4f} avg")

            except Exception as e:
                with stats_lock:
                    stats["failed"] += 1
                print(f"  ❌ {station_id}: {e}")
                nonce_mgr.resync(SELLER_ACCOUNT)
                nonce_mgr.resync(BUYER_ACCOUNT)

        with stats_lock:
            stats["batches_flushed"] += 1
            stats["buildings_settled"] += settled_count
            stats["total_mwh"] += total_mwh
            stats["total_gas"] += batch_gas
            stats["thn_minted"] += batch_minted
            stats["thn_burned"] += batch_burned

        print(f"  ──────────────────────────────────────────────────")
        print(f"  Batch done: {settled_count}/{total_buildings} buildings | Gas: {batch_gas:,}")
        print()


# ── Pub/Sub Callback ────────────────────────────────────────
def on_trade(message, source):
    message.ack()

    if is_duplicate(message.message_id):
        return

    try:
        trade = json.loads(message.data.decode("utf-8"))
    except:
        return

    status = trade.get("trade_status", "")
    if status not in ("SETTLED", "ISLAND_SETTLED", "BRIDGE_LISTED"):
        return

    buffer_trade(trade)

def d63_callback(message):
    on_trade(message, "D63")

def d91_callback(message):
    on_trade(message, "D91")


# ── Timer thread for batch flush ────────────────────────────
def batch_flush_loop():
    """Flush batch every BATCH_INTERVAL_SEC."""
    while True:
        time.sleep(BATCH_INTERVAL_SEC)
        try:
            flush_batch()
        except Exception as e:
            print(f"  ❌ Batch flush error: {e}")


# ── Scoreboard ──────────────────────────────────────────────
def print_scoreboard():
    while True:
        time.sleep(60)
        with stats_lock:
            s = dict(stats)
        with buffer_lock:
            pending = sum(b["trades"] for b in trade_buffer.values())
            pending_mwh = sum(b["mwh"] for b in trade_buffer.values())
            pending_buildings = len(trade_buffer)

        thn_supply = "?"
        if token_contract:
            try:
                raw = token_contract.functions.totalSupply().call()
                thn_supply = f"{float(w3.from_wei(raw, 'ether')):.3f}"
            except:
                pass

        print()
        print(f"  ╔═══════════════════════════════════════════════════════════════════════╗")
        print(f"  ║  BATCH SETTLER — {datetime.now(timezone.utc).strftime('%H:%M:%S UTC'):>12}                                ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  BUFFER                                                              ║")
        print(f"  ║  Pending trades:    {pending:>6}  |  Pending MWh: {pending_mwh:>8.2f}              ║")
        print(f"  ║  Pending buildings: {pending_buildings:>6}  |  Next flush: {BATCH_INTERVAL_SEC}s             ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  LIFETIME                                                            ║")
        print(f"  ║  Trades buffered:   {s['trades_buffered']:>6}                                         ║")
        print(f"  ║  Batches flushed:   {s['batches_flushed']:>6}                                         ║")
        print(f"  ║  Buildings settled: {s['buildings_settled']:>6}                                         ║")
        print(f"  ║  Total MWh:         {s['total_mwh']:>10.2f}                                     ║")
        print(f"  ║  Total gas:         {s['total_gas']:>10,}                                     ║")
        print(f"  ║  Failed:            {s['failed']:>6}                                         ║")
        print(f"  ║  THN minted:        {s['thn_minted']:>10.3f}  |  THN supply: {thn_supply:>10}    ║")
        print(f"  ╚═══════════════════════════════════════════════════════════════════════╝")
        print()


# ── Cloud Functions Gen 2 Entry Points ──────────────────────
# These are called when deployed as Cloud Functions.
# In Docker mode, they're unused — the streaming subscriber runs instead.

def cf_ingest_trade(cloud_event):
    """Cloud Functions gen 2 entry: Pub/Sub push trigger.
    Buffers the trade for next batch flush."""
    import base64
    data = base64.b64decode(cloud_event.data["message"]["data"])
    trade = json.loads(data)
    status = trade.get("trade_status", "")
    if status in ("SETTLED", "ISLAND_SETTLED", "BRIDGE_LISTED"):
        buffer_trade(trade)
    return "ok"

def cf_flush_batch(request):
    """Cloud Functions gen 2 entry: Cloud Scheduler HTTP trigger.
    Flushes the batch to chain."""
    flush_batch()
    with stats_lock:
        s = dict(stats)
    return json.dumps(s), 200, {"Content-Type": "application/json"}


# ── Docker Mode: Main ───────────────────────────────────────
if __name__ == "__main__":
    print()
    print("  ╔═══════════════════════════════════════════════════════════════════════╗")
    print("  ║     TINY-HUB-NETWORK — Batch On-Chain Settler                        ║")
    print("  ║     Aggregates trades per building → 1 tx/building/hour               ║")
    print("  ╠═══════════════════════════════════════════════════════════════════════╣")
    print(f"  ║  Contract:  {CONTRACT_ADDRESS}       ║")
    print(f"  ║  Token:     {TOKEN_ADDRESS or 'NOT FOUND':42}       ║")
    print(f"  ║  RPC:       {RPC_URL:>45}       ║")
    print(f"  ║  Batch interval: {BATCH_INTERVAL_SEC:>4}s ({BATCH_INTERVAL_SEC // 60} min)                                   ║")
    print(f"  ║  Seller:    {SELLER_ACCOUNT}       ║")
    print(f"  ║  Buyer:     {BUYER_ACCOUNT}       ║")
    print("  ╚═══════════════════════════════════════════════════════════════════════╝")
    print()

    if not HAS_PUBSUB:
        print("  ❌ google-cloud-pubsub not installed")
        exit(1)

    # Create subscriptions
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

    # Subscribe
    flow = pubsub_v1.types.FlowControl(max_messages=20)
    d63_path = subscriber.subscription_path(PROJECT_ID, SETTLER_D63_SUB)
    d91_path = subscriber.subscription_path(PROJECT_ID, SETTLER_D91_SUB)

    subscriber.subscribe(d63_path, callback=d63_callback, flow_control=flow)
    subscriber.subscribe(d91_path, callback=d91_callback, flow_control=flow)
    print("  ✅ Subscribed to both topics")
    print()

    # Start batch flush timer
    threading.Thread(target=batch_flush_loop, daemon=True).start()
    print(f"  ⏱  Batch flush every {BATCH_INTERVAL_SEC}s ({BATCH_INTERVAL_SEC // 60} min)")

    # Start scoreboard
    threading.Thread(target=print_scoreboard, daemon=True).start()

    print("  ⛓  Batch settler active. Ctrl+C to stop.")
    print("  ─────────────────────────────────────────────────────────────────")
    print()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # Final flush on exit
        print("  Flushing remaining buffer...")
        flush_batch()
        with stats_lock:
            s = dict(stats)
        print()
        print(f"  ✅ Final: {s['trades_buffered']} trades → {s['batches_flushed']} batches → {s['buildings_settled']} buildings")
