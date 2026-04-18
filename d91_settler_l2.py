"""
TINY-HUB-NETWORK — On-Chain Trade Settler (L2 Arbitrum)
=======================================================
Subscribes to both Pub/Sub topics (energy-pulse + district91-energy).
When a trade is SETTLED, it calls settleTrade() on TinyHubMarketV3,
which does list + purchase atomically with on-chain idempotency.

Modes:
  NETWORK=local   → Hardhat localhost:8545 (dev, unsigned sends)
  NETWORK=l2      → Arbitrum Sepolia (signed txs via private key)

Run:
  # Local dev:
  NETWORK=local python3 d91_settler_l2.py

  # Arbitrum Sepolia:
  NETWORK=l2 python3 d91_settler_l2.py

Requires: pip install web3 google-cloud-pubsub google-cloud-secret-manager
"""

import os
import json
import time
import threading
from datetime import datetime
from collections import deque
from web3 import Web3
from google.cloud import pubsub_v1
from batch_aggregator import BatchAggregator

# ── Network mode ────────────────────────────────────────────
NETWORK = os.environ.get("NETWORK", "local")  # "local" or "l2"
IS_L2 = NETWORK == "l2"

print(f"  ╔══════════════════════════════════════════════════╗")
print(f"  ║  TINY-HUB SETTLER {'(Arbitrum L2)' if IS_L2 else '(Local Hardhat)':>20}  ║")
print(f"  ╚══════════════════════════════════════════════════╝")

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "tinyhub-data-dev")

# Pub/Sub subscriptions
SETTLER_D63_SUB = "energy-pulse-settler-sub"
SETTLER_D91_SUB = "district91-energy-settler-sub"

# ── Blockchain connection ───────────────────────────────────
if IS_L2:
    RPC_URL = os.environ.get("ARBITRUM_SEPOLIA_RPC", "https://sepolia-rollup.arbitrum.io/rpc")
    DEPLOYMENT_FILE = "deployment_l2.json"
else:
    RPC_URL = os.environ.get("RPC_URL", "http://127.0.0.1:8545")
    DEPLOYMENT_FILE = "deployment.json"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    print(f"  ❌ Cannot connect to blockchain at {RPC_URL}")
    if IS_L2:
        print("     Check ARBITRUM_SEPOLIA_RPC env var")
    else:
        print("     Make sure 'npx hardhat node' is running")
    exit(1)

chain_id = w3.eth.chain_id
print(f"  RPC:       {RPC_URL}")
print(f"  Chain ID:  {chain_id}")

# ── Load private key ────────────────────────────────────────
SETTLER_KEY = None
SETTLER_ACCOUNT = None

if IS_L2:
    # Try Secret Manager first, fall back to env var
    try:
        from google.cloud import secretmanager
        sm = secretmanager.SecretManagerServiceClient()
        secret_name = "projects/tinyhub-platform-dev/secrets/SETTLER_PRIVATE_KEY/versions/latest"
        SETTLER_KEY = sm.access_secret_version(request={"name": secret_name}).payload.data.decode("UTF-8").strip()
        print("  Key:       Loaded from Secret Manager")
    except Exception:
        SETTLER_KEY = os.environ.get("SETTLER_PRIVATE_KEY", "").strip()
        if SETTLER_KEY:
            print("  Key:       Loaded from env var")
        else:
            print("  ❌ No SETTLER_PRIVATE_KEY in Secret Manager or env")
            exit(1)

    account = w3.eth.account.from_key(SETTLER_KEY)
    SETTLER_ACCOUNT = account.address
    print(f"  Settler:   {SETTLER_ACCOUNT}")
    balance = w3.eth.get_balance(SETTLER_ACCOUNT)
    print(f"  Balance:   {w3.from_wei(balance, 'ether')} ETH")
    if balance == 0:
        print("  ⚠️  Zero balance — get test ETH from faucet.quicknode.com/arbitrum/sepolia")
else:
    # Hardhat pre-funded accounts
    accounts = w3.eth.accounts
    SETTLER_ACCOUNT = accounts[0]
    BUYER_ACCOUNT = accounts[1]
    print(f"  Settler:   {SETTLER_ACCOUNT} (Hardhat account[0])")

# ── Load contracts ──────────────────────────────────────────
if not os.path.exists(DEPLOYMENT_FILE):
    print(f"  ❌ {DEPLOYMENT_FILE} not found — run deploy script first")
    exit(1)

with open(DEPLOYMENT_FILE) as f:
    dep = json.load(f)

# MarketV3 / V2 address
CONTRACT_ADDRESS = dep.get("TinyHubMarketV2") or dep.get("contracts", {}).get("TinyHubMarketV3", {}).get("address")

# Token address
TOKEN_ADDRESS = dep.get("TinyHubToken") or dep.get("contracts", {}).get("TinyHubTokenL2", {}).get("address")

print(f"  Market:    {CONTRACT_ADDRESS}")
print(f"  Token:     {TOKEN_ADDRESS}")

# ── ABIs ────────────────────────────────────────────────────
# MarketV3 ABI — includes atomic settleTrade + isSettled
MARKET_ABI = [
    {
        "inputs": [
            {"internalType": "string", "name": "_messageId", "type": "string"},
            {"internalType": "string", "name": "_stationId", "type": "string"},
            {"internalType": "string", "name": "_district", "type": "string"},
            {"internalType": "uint256", "name": "_amount", "type": "uint256"},
            {"internalType": "uint256", "name": "_price", "type": "uint256"},
            {"internalType": "enum TinyHubMarketV3.ResourceType", "name": "_type", "type": "uint8"}
        ],
        "name": "settleTrade",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "string", "name": "_messageId", "type": "string"},
            {"internalType": "string", "name": "_stationId", "type": "string"},
            {"internalType": "string", "name": "_fromDistrict", "type": "string"},
            {"internalType": "string", "name": "_toDistrict", "type": "string"},
            {"internalType": "uint256", "name": "_amount", "type": "uint256"},
            {"internalType": "uint256", "name": "_price", "type": "uint256"},
            {"internalType": "enum TinyHubMarketV3.ResourceType", "name": "_type", "type": "uint8"}
        ],
        "name": "settleBridge",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "string", "name": "_messageId", "type": "string"}],
        "name": "isSettled",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
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
        "inputs": [],
        "name": "duplicatesBlocked",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    # settleBatch — bulk settlement in one tx
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "string", "name": "messageId", "type": "string"},
                    {"internalType": "string", "name": "stationId", "type": "string"},
                    {"internalType": "string", "name": "district", "type": "string"},
                    {"internalType": "uint256", "name": "amount", "type": "uint256"},
                    {"internalType": "uint256", "name": "price", "type": "uint256"},
                    {"internalType": "enum TinyHubMarketV3.ResourceType", "name": "rType", "type": "uint8"},
                    {"internalType": "bool", "name": "isBridge", "type": "bool"},
                    {"internalType": "string", "name": "toDistrict", "type": "string"}
                ],
                "internalType": "struct TinyHubMarketV3.BatchEntry[]",
                "name": "entries",
                "type": "tuple[]"
            }
        ],
        "name": "settleBatch",
        "outputs": [{"internalType": "uint256", "name": "settled", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    },
    # V2 compat — listResource + purchaseResource for local mode
    {
        "inputs": [
            {"internalType": "string", "name": "_id", "type": "string"},
            {"internalType": "string", "name": "_district", "type": "string"},
            {"internalType": "uint256", "name": "_amount", "type": "uint256"},
            {"internalType": "uint256", "name": "_price", "type": "uint256"},
            {"internalType": "enum TinyHubMarketV3.ResourceType", "name": "_type", "type": "uint8"}
        ],
        "name": "listResource",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "_tradeId", "type": "uint256"}],
        "name": "purchaseResource",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "_tradeId", "type": "uint256"},
            {"internalType": "string", "name": "_toDistrict", "type": "string"}
        ],
        "name": "bridgeResource",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
]

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

contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=MARKET_ABI)
platform_fee = contract.functions.PLATFORM_FEE().call()
print(f"  Fee:       {w3.from_wei(platform_fee, 'ether')} ETH")

token_contract = None
if TOKEN_ADDRESS:
    try:
        token_contract = w3.eth.contract(address=TOKEN_ADDRESS, abi=TOKEN_ABI)
        symbol = token_contract.functions.symbol().call()
        supply = token_contract.functions.totalSupply().call()
        print(f"  Token:     {symbol} — supply {w3.from_wei(supply, 'ether')} THN")
    except Exception as e:
        print(f"  ⚠️  Token contract error: {e}")
        token_contract = None

print("")

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

# ── Local-mode idempotency (L2 uses on-chain mapping) ──────
MAX_SEEN_IDS = 10_000
seen_ids: set[str] = set()
seen_ids_order: list[str] = []
seen_ids_lock = threading.Lock()


def is_duplicate_local(message_id: str) -> bool:
    """Local-mode dedup. On L2, the contract handles this."""
    with seen_ids_lock:
        if message_id in seen_ids:
            return True
        seen_ids.add(message_id)
        seen_ids_order.append(message_id)
        while len(seen_ids_order) > MAX_SEEN_IDS:
            evicted = seen_ids_order.pop(0)
            seen_ids.discard(evicted)
        return False


# ── Transaction helpers ─────────────────────────────────────
chain_lock = threading.Lock()
recent_txs = deque(maxlen=50)

# ── Batch settlement config ─────────────────────────────────
# BATCH_MODE=true  → buffer trades, flush 1 tx per hour (default on L2)
# BATCH_MODE=false → settle each trade immediately
BATCH_MODE = os.environ.get("BATCH_MODE", "true" if IS_L2 else "false").lower() == "true"
BATCH_INTERVAL = int(os.environ.get("BATCH_INTERVAL", "3600"))  # seconds

if BATCH_MODE:
    print(f"  Batch:     ON — flush every {BATCH_INTERVAL}s")
else:
    print(f"  Batch:     OFF — per-trade settlement")


def flush_batch_to_chain(entries: list[dict]):
    """
    Called by BatchAggregator when it's time to flush.
    Sends a single settleBatch() tx with all netted entries.
    """
    if not entries:
        return

    # Build the tuple array for the contract
    batch_tuples = []
    for e in entries:
        batch_tuples.append((
            e["messageId"],
            e["stationId"],
            e["district"],
            e["amount"],
            e["price"],
            e["rType"],
            e["isBridge"],
            e["toDistrict"],
        ))

    try:
        with chain_lock:
            if IS_L2:
                receipt = send_signed_tx(
                    contract.functions.settleBatch(batch_tuples),
                    value=0
                )
                gas = receipt.gasUsed
            else:
                receipt = send_local_tx(
                    contract.functions.settleBatch(batch_tuples),
                    SETTLER_ACCOUNT, value=0
                )
                gas = receipt.get("gasUsed", 0) if hasattr(receipt, "get") else 0

            trade_count = contract.functions.tradeCount().call()

            # Batch mint/burn THN for all entries
            total_mwh = sum(e["_net_mwh"] for e in entries)
            total_toll = 0.0
            for e in entries:
                toll = 0.02 if "D63" in e["district"] else 0.025
                total_toll += toll

            if token_contract and total_mwh > 0:
                mint_amount = w3.to_wei(total_mwh, "ether")
                burn_amount = w3.to_wei(total_toll, "ether")

                if IS_L2:
                    send_signed_tx(
                        token_contract.functions.mint(SETTLER_ACCOUNT, mint_amount, f"batch_{len(entries)}")
                    )
                    send_signed_tx(
                        token_contract.functions.burn(SETTLER_ACCOUNT, burn_amount, f"batch_toll_{len(entries)}")
                    )
                else:
                    send_local_tx(
                        token_contract.functions.mint(SETTLER_ACCOUNT, mint_amount, f"batch_{len(entries)}"),
                        SETTLER_ACCOUNT
                    )
                    send_local_tx(
                        token_contract.functions.burn(SETTLER_ACCOUNT, burn_amount, f"batch_toll_{len(entries)}"),
                        SETTLER_ACCOUNT
                    )

            with stats_lock:
                stats["settled_onchain"] += len(entries)
                stats["gas_used"] += gas
                stats["thn_minted"] += total_mwh
                stats["thn_burned"] += total_toll

            absorbed = sum(e["_trade_count"] for e in entries)
            print(f"  ⛓️  BATCH TX | {absorbed} trades → {len(entries)} entries | "
                  f"{total_mwh:.3f} MWh | gas {gas} | tradeCount={trade_count}")

    except Exception as e:
        with stats_lock:
            stats["failed"] += 1
        print(f"  ❌ Batch settlement error: {e}")


# Initialize aggregator (only active if BATCH_MODE)
batch_agg = BatchAggregator(
    flush_interval=BATCH_INTERVAL,
    max_buffer_size=500,
    on_flush=flush_batch_to_chain
) if BATCH_MODE else None


def send_signed_tx(func, value=0):
    """Build, sign, send a transaction using the settler private key."""
    tx = func.build_transaction({
        "from": SETTLER_ACCOUNT,
        "nonce": w3.eth.get_transaction_count(SETTLER_ACCOUNT),
        "gas": 500000,
        "maxFeePerGas": w3.eth.gas_price * 2,
        "maxPriorityFeePerGas": w3.to_wei(0.1, "gwei"),
        "value": value,
        "chainId": chain_id,
    })
    signed = w3.eth.account.sign_transaction(tx, SETTLER_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)


def send_local_tx(func, from_addr, value=0):
    """Unsigned send for Hardhat local node."""
    tx = func.build_transaction({
        "from": from_addr,
        "nonce": w3.eth.get_transaction_count(from_addr),
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
        "value": value,
    })
    tx_hash = w3.eth.send_transaction(tx)
    return w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)


# ── Settle on L2 (atomic) ──────────────────────────────────
def settle_l2(trade, message_id):
    """
    Atomic settlement on Arbitrum via settleTrade().
    On-chain idempotency — contract reverts duplicates.
    """
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
        with chain_lock:
            if is_bridge:
                origin = trade.get("origin_district", "McHenry_D63")
                receipt = send_signed_tx(
                    contract.functions.settleBridge(
                        message_id, station_id, district, origin,
                        amount_milli, price_wei, 0  # Energy
                    ),
                    value=0
                )
            else:
                receipt = send_signed_tx(
                    contract.functions.settleTrade(
                        message_id, station_id, district,
                        amount_milli, price_wei, 0  # Energy
                    ),
                    value=0
                )

            gas = receipt.gasUsed
            trade_count = contract.functions.tradeCount().call()

            # Mint + burn THN
            thn_minted = 0.0
            thn_burned = 0.0
            if token_contract:
                mint_amount = w3.to_wei(mwh, "ether")
                toll = 0.02 if district == "McHenry_D63" else 0.025
                burn_amount = w3.to_wei(toll, "ether")

                send_signed_tx(
                    token_contract.functions.mint(SETTLER_ACCOUNT, mint_amount, station_id)
                )
                send_signed_tx(
                    token_contract.functions.burn(SETTLER_ACCOUNT, burn_amount, f"grid_toll_{district}")
                )
                thn_minted = mwh
                thn_burned = toll

            with stats_lock:
                if is_bridge:
                    stats["bridged_onchain"] += 1
                else:
                    stats["settled_onchain"] += 1
                stats["gas_used"] += gas
                stats["thn_minted"] += thn_minted
                stats["thn_burned"] += thn_burned

            tag = "BRIDGE" if is_bridge else "SETTLE"
            print(f"  ⛓️  L2 {tag} #{trade_count} | {station_id:22} | {mwh:.3f} MWh | ${settled_price:.4f} | gas {gas}")
            if thn_minted:
                supply = token_contract.functions.totalSupply().call()
                print(f"     🪙 +{thn_minted:.3f} THN | -{thn_burned} burned | Supply: {w3.from_wei(supply, 'ether'):.3f} THN")

            recent_txs.append({
                "trade_id": trade_count,
                "station": station_id,
                "mwh": mwh,
                "price": settled_price,
                "gas": gas,
                "time": datetime.now().isoformat(),
                "network": "arbitrum_sepolia",
            })

            return receipt

    except Exception as e:
        err_str = str(e)
        if "Duplicate message" in err_str:
            with stats_lock:
                stats["duplicates"] += 1
            print(f"  🔁 Duplicate blocked on-chain: {message_id[:16]}...")
            return None
        else:
            with stats_lock:
                stats["failed"] += 1
            print(f"  ❌ L2 settle error: {e}")
            return None


# ── Settle on local Hardhat (V2 two-step) ──────────────────
def settle_local(trade, message_id):
    """
    Two-step settlement on local Hardhat (backward compat with V2).
    Uses Python-side idempotency.
    """
    if is_duplicate_local(message_id):
        with stats_lock:
            stats["duplicates"] += 1
        return None

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
        with chain_lock:
            # Step 1: List
            send_local_tx(
                contract.functions.listResource(station_id, district, amount_milli, price_wei, 0),
                SETTLER_ACCOUNT
            )

            trade_id = contract.functions.tradeCount().call()

            # Step 2: Purchase
            total_cost = (amount_milli * price_wei) + platform_fee
            if is_bridge:
                buyer_district = trade.get("origin_district", "McHenry_D63")
                total_cost = (amount_milli * price_wei) + (platform_fee * 2)
                send_local_tx(
                    contract.functions.bridgeResource(trade_id, buyer_district),
                    BUYER_ACCOUNT, value=total_cost
                )
            else:
                send_local_tx(
                    contract.functions.purchaseResource(trade_id),
                    BUYER_ACCOUNT, value=total_cost
                )

            # Mint + burn THN
            thn_minted = 0.0
            thn_burned = 0.0
            if token_contract:
                mint_amount = w3.to_wei(mwh, "ether")
                toll = 0.02 if district == "McHenry_D63" else 0.025
                burn_amount = w3.to_wei(toll, "ether")

                send_local_tx(
                    token_contract.functions.mint(SETTLER_ACCOUNT, mint_amount, station_id),
                    SETTLER_ACCOUNT
                )
                send_local_tx(
                    token_contract.functions.burn(SETTLER_ACCOUNT, burn_amount, f"grid_toll_{district}"),
                    SETTLER_ACCOUNT
                )
                thn_minted = mwh
                thn_burned = toll

            with stats_lock:
                if is_bridge:
                    stats["bridged_onchain"] += 1
                else:
                    stats["settled_onchain"] += 1
                stats["thn_minted"] += thn_minted
                stats["thn_burned"] += thn_burned

            tag = "BRIDGE" if is_bridge else "SETTLE"
            print(f"  ⛓️  LOCAL {tag} #{trade_id} | {station_id:22} | {mwh:.3f} MWh | ${settled_price:.4f}")

            return True

    except Exception as e:
        with stats_lock:
            stats["failed"] += 1
        print(f"  ❌ Local settle error: {e}")
        return None


# ── Pub/Sub callback ────────────────────────────────────────
def on_trade(message, source):
    message.ack()

    try:
        trade = json.loads(message.data.decode("utf-8"))
    except Exception:
        return

    status = trade.get("trade_status", "")
    if status not in ("SETTLED", "BRIDGE_LISTED"):
        with stats_lock:
            stats["skipped"] += 1
        return

    message_id = message.message_id

    # ── Batch mode: buffer trades, flush periodically ───────
    if BATCH_MODE and batch_agg:
        batch_agg.add_trade(trade, message_id)
        return

    # ── Immediate mode: settle each trade now ───────────────
    if IS_L2:
        settle_l2(trade, message_id)
    else:
        settle_local(trade, message_id)


# ── Scoreboard ──────────────────────────────────────────────
def scoreboard():
    while True:
        time.sleep(30)
        with stats_lock:
            s = dict(stats)

        dupes_onchain = 0
        try:
            dupes_onchain = contract.functions.duplicatesBlocked().call()
        except Exception:
            pass

        total = s["settled_onchain"] + s["bridged_onchain"]
        net_mode = "Arbitrum Sepolia" if IS_L2 else "Hardhat Local"
        print(f"\n  ┌── SETTLER SCOREBOARD ({net_mode}) ─────────────────────")
        print(f"  │ Settled:     {s['settled_onchain']}")
        print(f"  │ Bridged:     {s['bridged_onchain']}")
        print(f"  │ Total:       {total}")
        print(f"  │ Skipped:     {s['skipped']}")
        print(f"  │ Failed:      {s['failed']}")
        print(f"  │ Duplicates:  {s['duplicates']} (python) + {dupes_onchain} (on-chain)")
        print(f"  │ THN minted:  {s['thn_minted']:.3f}")
        print(f"  │ THN burned:  {s['thn_burned']:.3f}")
        if IS_L2:
            print(f"  │ Gas used:    {s['gas_used']:,}")
            balance = w3.eth.get_balance(SETTLER_ACCOUNT)
            print(f"  │ ETH balance: {w3.from_wei(balance, 'ether'):.6f}")
        if BATCH_MODE and batch_agg:
            bs = batch_agg.stats
            print(f"  ├── BATCH ──────────────────────────────────────")
            print(f"  │ Buffered:   {bs['buffered_trades']} trades / {bs['buffered_buildings']} buildings")
            print(f"  │ Flushes:    {bs['flushes']}")
            print(f"  │ Absorbed:   {bs['total_trades_absorbed']} trades → {bs['total_settled']} entries")
            print(f"  │ Compress:   {bs['compression_ratio']:.1f}x")
            print(f"  │ Next flush: {max(0, BATCH_INTERVAL - bs['seconds_since_flush'])}s")
        print(f"  └──────────────────────────────────────────────\n")


# ── Main ────────────────────────────────────────────────────
def main():
    subscriber = pubsub_v1.SubscriberClient()

    d91_path = subscriber.subscription_path(PROJECT_ID, SETTLER_D91_SUB)
    d63_path = subscriber.subscription_path(PROJECT_ID, SETTLER_D63_SUB)

    print(f"  Subscribing to D91: {SETTLER_D91_SUB}")
    print(f"  Subscribing to D63: {SETTLER_D63_SUB}")
    print(f"  Mode: {'L2 Arbitrum (signed txs)' if IS_L2 else 'Local Hardhat (unsigned)'}")
    print("")

    future_d91 = subscriber.subscribe(d91_path, callback=lambda msg: on_trade(msg, "D91"))
    future_d63 = subscriber.subscribe(d63_path, callback=lambda msg: on_trade(msg, "D63"))

    # Start scoreboard thread
    sb_thread = threading.Thread(target=scoreboard, daemon=True)
    sb_thread.start()

    print("  ✅ Settler running — waiting for trades...")
    print("")

    try:
        future_d91.result()
    except KeyboardInterrupt:
        future_d91.cancel()
        future_d63.cancel()
        print("\n  Settler stopped.")


if __name__ == "__main__":
    main()
