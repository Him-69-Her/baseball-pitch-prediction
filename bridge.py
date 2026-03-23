import os
"""
TINY-HUB-NETWORK — Pub/Sub → Blockchain Bridge
Subscribes to energy-pulse, and when a trade is SETTLED,
calls listResource + purchaseResource on TinyHubMarket.

Run:
    pip install google-cloud-pubsub web3
    python bridge.py

Requires:
    - marketplace.py publishing trades to Pub/Sub
    - npx hardhat node running (local blockchain)
    - TinyHubMarket deployed (deployment.json must exist)
"""
import json
import time
import threading
from datetime import datetime
from google.cloud import pubsub_v1
from web3 import Web3

# ─── GCP Config ──────────────────────────────────────────────────
PROJECT_ID = "tiny-hub-network"
SUBSCRIPTION_ID = "energy-pulse-sub"
# ─── Blockchain Config ───────────────────────────────────────────
RPC_URL = os.environ.get("RPC_URL", "http://127.0.0.1:8545")  # Local Hardhat node

# Hardhat default accounts (pre-funded with 10000 ETH each)
# Account 0 = seller, Account 1 = buyer
SELLER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
BUYER_KEY  = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"

# ─── Load Contract ───────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    print("  ❌ Cannot connect to blockchain at", RPC_URL)
    print("     Make sure 'npx hardhat node' is running")
    exit(1)

# Load deployment info
with open("deployment.json", "r") as f:
    deployment = json.load(f)

# Support both old format (deployment["address"]) and new format (deployment["contracts"])
if "contracts" in deployment:
    MARKET_ADDRESS = deployment["contracts"]["TinyHubMarket"]["address"]
    TOKEN_ADDRESS = deployment["contracts"]["TinyHubToken"]["address"]
else:
    MARKET_ADDRESS = deployment["address"]
    TOKEN_ADDRESS = None

# Load Market contract
with open("TinyHubMarket.json", "r") as f:
    market_artifact = json.load(f)

market = w3.eth.contract(address=MARKET_ADDRESS, abi=market_artifact["abi"])

# Load Token contract (compiled by Hardhat)
token = None
if TOKEN_ADDRESS:
    token_artifact_path = "build/contracts_TinyHubToken_sol_TinyHubToken.abi"
    try:
        with open(token_artifact_path, "r") as f:
            token_abi = json.load(f)
        token = w3.eth.contract(address=TOKEN_ADDRESS, abi=token_abi)
        print(f"  [Token] TinyHubToken loaded at {TOKEN_ADDRESS}")
    except FileNotFoundError:
        print(f"  [Token] Artifact not found at {token_artifact_path} — token features disabled")

seller_account = w3.eth.account.from_key(SELLER_KEY)
buyer_account = w3.eth.account.from_key(BUYER_KEY)

COMED_TOLL_MWH = 0.02  # 0.02 MWh burned per trade as grid fee

# ResourceType enum: 0 = Energy, 1 = Compute
RESOURCE_ENERGY = 0

# ─── Stats ───────────────────────────────────────────────────────
bridge_stats = {
    "received": 0,
    "on_chain": 0,
    "skipped": 0,
    "errors": 0,
    "tokens_minted": 0.0,
    "tokens_burned": 0.0,
}

# ─── Bridge Logic ────────────────────────────────────────────────
chain_lock = threading.Lock()

def send_tx(account, private_key, func, value=0):
    """Build, sign, and send a transaction. Returns receipt."""
    nonce = w3.eth.get_transaction_count(account.address)
    tx = func.build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
        "value": value,
    })
    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return w3.eth.wait_for_transaction_receipt(tx_hash)

def settle_on_chain(trade_data):
    """Take a settled trade from Pub/Sub and record it on-chain."""
    with chain_lock:
        station_id = trade_data.get("station_id", "unknown")
        mwh = trade_data.get("mwh", 0)
        settled_price = trade_data.get("settled_price", 0)

        amount = int(mwh * 1000)  # milliMWh
        if amount == 0:
            amount = 1

        total_wei = int(mwh * settled_price * 1e18)
        price = total_wei // amount if amount > 0 else 0

        try:
            # Step 1: Seller lists the resource on the market
            send_tx(seller_account, SELLER_KEY,
                    market.functions.listResource(station_id, amount, price, RESOURCE_ENERGY))

            trade_id = market.functions.tradeCount().call()

            # Step 2: Buyer purchases the resource
            platform_fee = market.functions.PLATFORM_FEE().call()
            total_cost = (amount * price) + platform_fee

            send_tx(buyer_account, BUYER_KEY,
                    market.functions.purchaseResource(trade_id), value=total_cost)

            # Step 3: Mint THN tokens to seller (1 THN = 1 MWh)
            token_amount = int(mwh * 1e18)  # 18 decimal ERC-20
            toll_amount = int(COMED_TOLL_MWH * 1e18)

            if token:
                # Mint MWh tokens to seller
                send_tx(seller_account, SELLER_KEY,
                        token.functions.mint(seller_account.address, token_amount, station_id))

                # Burn ComEd toll from seller
                send_tx(seller_account, SELLER_KEY,
                        token.functions.burn(seller_account.address, toll_amount, "ComEd toll"))

                bridge_stats["tokens_minted"] += mwh
                bridge_stats["tokens_burned"] += COMED_TOLL_MWH

                seller_bal = token.functions.balanceOf(seller_account.address).call()
                total_supply = token.functions.totalSupply().call()

                print(f"  ⛓️  ON-CHAIN #{trade_id} | {station_id:22} | {mwh:.3f} MWh | ${settled_price:.4f}")
                print(f"     🪙 +{mwh:.3f} THN minted | -{COMED_TOLL_MWH} burned | Supply: {w3.from_wei(total_supply, 'ether'):.3f} THN")
            else:
                print(f"  ⛓️  ON-CHAIN #{trade_id} | {station_id:22} | {mwh:.3f} MWh | ${settled_price:.4f}")

            bridge_stats["on_chain"] += 1

        except Exception as e:
            bridge_stats["errors"] += 1
            print(f"  ❌ Chain error: {e}")


def pubsub_callback(message):
    """Process each Pub/Sub message."""
    try:
        data = json.loads(message.data.decode("utf-8"))
        message.ack()
        bridge_stats["received"] += 1

        status = data.get("trade_status", "")

        if status in ("SETTLED", "ISLAND_SETTLED"):
            settle_on_chain(data)
        else:
            bridge_stats["skipped"] += 1
            print(f"  ⏭️  SKIP {status:16} | {data.get('station_id', '?'):22} | {data.get('mwh', 0):.3f} MWh")

    except Exception as e:
        print(f"  ❌ Message error: {e}")
        message.nack()


# ─── Startup ─────────────────────────────────────────────────────
print()
print("  ╔══════════════════════════════════════════════════════════════╗")
print("  ║     TINY-HUB-NETWORK — Pub/Sub → Blockchain Bridge         ║")
print("  ╠══════════════════════════════════════════════════════════════╣")
print(f"  ║  Market:        {MARKET_ADDRESS}  ║")
if TOKEN_ADDRESS:
    print(f"  ║  Token (THN):   {TOKEN_ADDRESS}  ║")
print(f"  ║  Blockchain:    {RPC_URL:>42}  ║")
print(f"  ║  Subscription:  {SUBSCRIPTION_ID:>42}  ║")
print(f"  ║  Seller:        {seller_account.address}  ║")
print(f"  ║  Buyer:         {buyer_account.address}  ║")
print("  ╚══════════════════════════════════════════════════════════════╝")
print()

# Verify contracts are reachable
try:
    count = market.functions.tradeCount().call()
    fee = market.functions.PLATFORM_FEE().call()
    print(f"  ✅ Market live | Trades so far: {count} | Fee: {w3.from_wei(fee, 'ether')} ETH")
    if token:
        supply = token.functions.totalSupply().call()
        print(f"  ✅ Token live  | Supply: {w3.from_wei(supply, 'ether')} THN | 1 THN = 1 MWh")
    print()
except Exception as e:
    print(f"  ❌ Cannot reach contracts: {e}")
    exit(1)

# Start subscriber
subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)

streaming_pull = subscriber.subscribe(subscription_path, callback=pubsub_callback)
print(f"  🔗 Listening on {subscription_path}...")
print(f"     Settled trades → on-chain + mint THN | Rejected → skipped")
print()

try:
    streaming_pull.result()
except KeyboardInterrupt:
    streaming_pull.cancel()
    streaming_pull.result()
    print()
    print("  ╔══════════════════════════════════════════════════════════════╗")
    print("  ║                    BRIDGE REPORT                            ║")
    print("  ╠══════════════════════════════════════════════════════════════╣")
    print(f"  ║  Messages received:   {bridge_stats['received']:>6}                                 ║")
    print(f"  ║  Settled on-chain:    {bridge_stats['on_chain']:>6}                                 ║")
    print(f"  ║  Skipped (rejected):  {bridge_stats['skipped']:>6}                                 ║")
    print(f"  ║  Errors:              {bridge_stats['errors']:>6}                                 ║")
    total = market.functions.tradeCount().call()
    print(f"  ║  Total on-chain:      {total:>6}                                 ║")
    if token:
        supply = token.functions.totalSupply().call()
        seller_bal = token.functions.balanceOf(seller_account.address).call()
        print(f"  ╠══════════════════════════════════════════════════════════════╣")
        print(f"  ║  THN minted:       {bridge_stats['tokens_minted']:>9.3f} MWh                          ║")
        print(f"  ║  THN burned (toll): {bridge_stats['tokens_burned']:>8.3f} MWh                          ║")
        print(f"  ║  THN supply:       {w3.from_wei(supply, 'ether'):>9.3f} THN                          ║")
        print(f"  ║  Seller balance:   {w3.from_wei(seller_bal, 'ether'):>9.3f} THN                          ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
