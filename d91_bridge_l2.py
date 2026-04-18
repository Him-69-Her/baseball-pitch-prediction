"""
TINY-HUB-NETWORK — Cross-District Energy Bridge (L2 Arbitrum)
=============================================================
Routes surplus energy between D63 (McHenry/ComEd/PJM) and
D91 (Peoria/Ameren/MISO) with toll, transmission loss, and markup.

On L2, uses atomic settleBridge() on TinyHubMarketV3.
On local, uses two-step list + bridgeResource on V2.

Modes:
  NETWORK=local   → Hardhat localhost:8545
  NETWORK=l2      → Arbitrum Sepolia (signed txs)

Run:
  NETWORK=l2 python3 d91_bridge_l2.py
"""

import os
import json
import time
import threading
from datetime import datetime
from google.cloud import pubsub_v1
from web3 import Web3

# ── Network mode ────────────────────────────────────────────
NETWORK = os.environ.get("NETWORK", "local")
IS_L2 = NETWORK == "l2"

print(f"  ╔══════════════════════════════════════════════════╗")
print(f"  ║  TINY-HUB BRIDGE  {'(Arbitrum L2)' if IS_L2 else '(Local Hardhat)':>20}  ║")
print(f"  ╚══════════════════════════════════════════════════╝")

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "tinyhub-data-dev")
D63_SUB = "energy-pulse-sub"
D91_SUB = "district91-energy-bridge-sub"

# Bridge economics
BRIDGE_TOLL = 0.015    # $/MWh toll
TX_LOSS_PCT = 0.03     # 3% transmission loss
MARKUP_PCT  = 0.12     # 12% price markup
COMED_TOLL  = 0.02     # ComEd grid toll (THN burned)
AMEREN_TOLL = 0.025    # Ameren grid toll (THN burned)

# ── Blockchain ──────────────────────────────────────────────
if IS_L2:
    RPC_URL = os.environ.get("ARBITRUM_SEPOLIA_RPC", "https://sepolia-rollup.arbitrum.io/rpc")
    DEPLOYMENT_FILE = "deployment_l2.json"
else:
    RPC_URL = os.environ.get("RPC_URL", "http://127.0.0.1:8545")
    DEPLOYMENT_FILE = "deployment.json"

w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    print(f"  ❌ Cannot connect to {RPC_URL}")
    exit(1)

chain_id = w3.eth.chain_id
print(f"  RPC:       {RPC_URL}")
print(f"  Chain ID:  {chain_id}")

# ── Keys ────────────────────────────────────────────────────
BRIDGE_KEY = None
BRIDGE_ACCOUNT = None

if IS_L2:
    # Try Secret Manager, then env
    try:
        from google.cloud import secretmanager
        sm = secretmanager.SecretManagerServiceClient()
        secret_name = "projects/tinyhub-platform-dev/secrets/BRIDGE_PRIVATE_KEY/versions/latest"
        BRIDGE_KEY = sm.access_secret_version(request={"name": secret_name}).payload.data.decode("UTF-8").strip()
        print("  Key:       Secret Manager")
    except Exception:
        # Fall back to settler key — bridge can share wallet
        BRIDGE_KEY = os.environ.get("BRIDGE_PRIVATE_KEY") or os.environ.get("SETTLER_PRIVATE_KEY", "").strip()
        if BRIDGE_KEY:
            print("  Key:       env var")
        else:
            print("  ❌ No BRIDGE_PRIVATE_KEY found")
            exit(1)

    account = w3.eth.account.from_key(BRIDGE_KEY)
    BRIDGE_ACCOUNT = account.address
    print(f"  Bridge:    {BRIDGE_ACCOUNT}")
else:
    # Hardhat accounts
    SELLER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    BUYER_KEY  = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
    seller_account = w3.eth.account.from_key(SELLER_KEY)
    buyer_account = w3.eth.account.from_key(BUYER_KEY)
    BRIDGE_ACCOUNT = seller_account.address
    print(f"  Bridge:    {BRIDGE_ACCOUNT} (Hardhat)")

# ── Load contracts ──────────────────────────────────────────
with open(DEPLOYMENT_FILE) as f:
    dep = json.load(f)

MARKET_ADDRESS = dep.get("TinyHubMarketV2") or dep.get("contracts", {}).get("TinyHubMarketV3", {}).get("address")
TOKEN_ADDRESS = dep.get("TinyHubToken") or dep.get("contracts", {}).get("TinyHubTokenL2", {}).get("address")
print(f"  Market:    {MARKET_ADDRESS}")
print(f"  Token:     {TOKEN_ADDRESS}")

# Minimal ABIs
MARKET_ABI = [
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
        "inputs": [
            {"internalType": "string", "name": "_id", "type": "string"},
            {"internalType": "uint256", "name": "_amount", "type": "uint256"},
            {"internalType": "uint256", "name": "_price", "type": "uint256"},
            {"internalType": "enum TinyHubMarket.ResourceType", "name": "_type", "type": "uint8"}
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
]

market = w3.eth.contract(address=MARKET_ADDRESS, abi=MARKET_ABI)
token = None
if TOKEN_ADDRESS:
    try:
        token = w3.eth.contract(address=TOKEN_ADDRESS, abi=TOKEN_ABI)
    except Exception:
        pass

chain_lock = threading.Lock()

# ── Stats ───────────────────────────────────────────────────
bridge_stats = {
    "received": 0,
    "bridged": 0,
    "skipped": 0,
    "errors": 0,
    "tokens_minted": 0.0,
    "tokens_burned": 0.0,
}


# ── Tx helpers ──────────────────────────────────────────────
def send_signed(func, value=0):
    """Signed tx for L2."""
    tx = func.build_transaction({
        "from": BRIDGE_ACCOUNT,
        "nonce": w3.eth.get_transaction_count(BRIDGE_ACCOUNT),
        "gas": 500000,
        "maxFeePerGas": w3.eth.gas_price * 2,
        "maxPriorityFeePerGas": w3.to_wei(0.1, "gwei"),
        "value": value,
        "chainId": chain_id,
    })
    signed = w3.eth.account.sign_transaction(tx, BRIDGE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)


def send_local(account_obj, key, func, value=0):
    """Signed tx for local Hardhat (original bridge pattern)."""
    nonce = w3.eth.get_transaction_count(account_obj.address)
    tx = func.build_transaction({
        "from": account_obj.address,
        "nonce": nonce,
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
        "value": value,
    })
    signed = w3.eth.account.sign_transaction(tx, key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return w3.eth.wait_for_transaction_receipt(tx_hash)


# ── Bridge logic ────────────────────────────────────────────
def bridge_trade(trade_data, message_id):
    """Bridge a surplus trade between districts."""
    station_id = trade_data.get("station_id", "unknown")
    mwh = trade_data.get("mwh", 0)
    price = trade_data.get("settled_price", 0)
    from_district = trade_data.get("district", "IL_D91")
    to_district = "McHenry_D63" if from_district == "IL_D91" else "IL_D91"

    # Apply bridge economics
    delivered_mwh = mwh * (1 - TX_LOSS_PCT)
    bridge_price = price * (1 + MARKUP_PCT) + BRIDGE_TOLL

    amount_milli = int(delivered_mwh * 1000)
    if amount_milli <= 0:
        return

    price_wei = int(bridge_price * 10000)
    if price_wei <= 0:
        price_wei = 1

    try:
        with chain_lock:
            if IS_L2:
                receipt = send_signed(
                    market.functions.settleBridge(
                        message_id, station_id, from_district, to_district,
                        amount_milli, price_wei, 0
                    ),
                    value=0
                )
                gas = receipt.gasUsed
            else:
                # Local two-step
                send_local(seller_account, SELLER_KEY,
                           market.functions.listResource(station_id, amount_milli, price_wei, 0))
                trade_id = market.functions.tradeCount().call()
                platform_fee = market.functions.PLATFORM_FEE().call()
                total_cost = (amount_milli * price_wei) + platform_fee
                send_local(buyer_account, BUYER_KEY,
                           market.functions.purchaseResource(trade_id), value=total_cost)
                gas = 0

            # Mint + burn THN
            toll = COMED_TOLL if "D63" in to_district else AMEREN_TOLL
            if token:
                mint_amt = w3.to_wei(delivered_mwh, "ether")
                burn_amt = w3.to_wei(toll, "ether")

                if IS_L2:
                    send_signed(token.functions.mint(BRIDGE_ACCOUNT, mint_amt, station_id))
                    send_signed(token.functions.burn(BRIDGE_ACCOUNT, burn_amt, f"bridge_toll_{to_district}"))
                else:
                    send_local(seller_account, SELLER_KEY,
                               token.functions.mint(seller_account.address, mint_amt, station_id))
                    send_local(seller_account, SELLER_KEY,
                               token.functions.burn(seller_account.address, burn_amt, f"bridge_toll_{to_district}"))

                bridge_stats["tokens_minted"] += delivered_mwh
                bridge_stats["tokens_burned"] += toll

            bridge_stats["bridged"] += 1
            net = "L2" if IS_L2 else "LOCAL"
            print(f"  🌉 {net} BRIDGE | {station_id:22} | {mwh:.3f}→{delivered_mwh:.3f} MWh | "
                  f"{from_district}→{to_district} | ${bridge_price:.4f}")
            if IS_L2:
                print(f"     gas: {gas}")

    except Exception as e:
        if "Duplicate" in str(e):
            print(f"  🔁 Bridge duplicate blocked: {message_id[:16]}...")
        else:
            bridge_stats["errors"] += 1
            print(f"  ❌ Bridge error: {e}")


def on_message(message):
    """Pub/Sub callback — bridge surplus trades."""
    message.ack()
    bridge_stats["received"] += 1

    try:
        data = json.loads(message.data.decode("utf-8"))
    except Exception:
        return

    status = data.get("trade_status", "")
    if status != "SURPLUS":
        bridge_stats["skipped"] += 1
        return

    bridge_trade(data, message.message_id)


# ── Scoreboard ──────────────────────────────────────────────
def scoreboard():
    while True:
        time.sleep(30)
        s = bridge_stats
        net = "Arbitrum L2" if IS_L2 else "Local"
        print(f"\n  ┌── BRIDGE SCOREBOARD ({net}) ────────────────────")
        print(f"  │ Received:  {s['received']}")
        print(f"  │ Bridged:   {s['bridged']}")
        print(f"  │ Skipped:   {s['skipped']}")
        print(f"  │ Errors:    {s['errors']}")
        print(f"  │ THN mint:  {s['tokens_minted']:.3f}")
        print(f"  │ THN burn:  {s['tokens_burned']:.3f}")
        if IS_L2:
            bal = w3.eth.get_balance(BRIDGE_ACCOUNT)
            print(f"  │ ETH bal:   {w3.from_wei(bal, 'ether'):.6f}")
        print(f"  └──────────────────────────────────────────────\n")


# ── Main ────────────────────────────────────────────────────
def main():
    subscriber = pubsub_v1.SubscriberClient()

    d91_path = subscriber.subscription_path(PROJECT_ID, D91_SUB)
    print(f"  Subscribing: {D91_SUB}")
    print(f"  Mode: {'L2 Arbitrum (signed txs)' if IS_L2 else 'Local Hardhat'}")
    print("")

    future = subscriber.subscribe(d91_path, callback=on_message)

    sb = threading.Thread(target=scoreboard, daemon=True)
    sb.start()

    print("  ✅ Bridge running — waiting for surplus...")
    print("")

    try:
        future.result()
    except KeyboardInterrupt:
        future.cancel()
        print("\n  Bridge stopped.")


if __name__ == "__main__":
    main()
