#!/usr/bin/env python3
"""
TINY-HUB — Task #2 Fix: Settler On-Chain Settlement
====================================================
Fixes the Pub/Sub → Hardhat pipeline that was silently failing.

Root causes:
  1. No threading lock — concurrent Pub/Sub callbacks (up to 5)
     all read the same nonce → "nonce too low" for 4 of 5
  2. No local nonce tracking — each tx queries the chain for the
     nonce, but previous tx may still be pending in mempool
  3. No retry — once a nonce gets stuck, all subsequent txs fail

Fix:
  1. Add a global chain_lock (threading.Lock) around settle_onchain()
  2. Add a NonceManager that tracks pending nonce locally per account
  3. Add retry with nonce resync on failure
  4. Reduce flow_control to max_messages=1 (serialize at Pub/Sub level)

Run from project root:
    python3 fix_task2_settler.py
"""
from pathlib import Path

SETTLER = Path("d91_settler.py")
if not SETTLER.exists():
    print("  ❌ d91_settler.py not found")
    exit(1)

src = SETTLER.read_text(encoding="utf-8")
patches_applied = 0

# ══════════════════════════════════════════════════════════════
# PATCH 1: Add chain_lock and NonceManager after the imports
# ══════════════════════════════════════════════════════════════

NONCE_MANAGER_CODE = '''
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
'''

# Insert after the existing stats/counters block
ANCHOR_NONCE = "seen_ids_lock = threading.Lock()"

if "NonceManager" not in src:
    if ANCHOR_NONCE in src:
        # Find the end of the is_duplicate function to insert after it
        idx = src.find("        return False")
        if idx != -1:
            # Find the next line after "return False" in is_duplicate
            end_of_func = src.find("\n", idx)
            next_block = src.find("\n", end_of_func + 1)
            src = src[:next_block] + NONCE_MANAGER_CODE + src[next_block:]
            patches_applied += 1
            print("  ✅ Patch 1: NonceManager + chain_lock added")
        else:
            print("  ⚠️  Patch 1: Could not find is_duplicate return — add manually")
    else:
        print("  ⚠️  Patch 1: Anchor not found — add NonceManager manually")
else:
    print("  ⏭️  Patch 1: NonceManager already exists")

# Re-read src after patch 1
# (we modified it in-memory, so just continue)

# ══════════════════════════════════════════════════════════════
# PATCH 2: Rewrite settle_onchain to use chain_lock + NonceManager
# ══════════════════════════════════════════════════════════════

# Find the old settle_onchain function and replace it entirely
OLD_SETTLE_START = 'def settle_onchain(trade):'
OLD_SETTLE_DOCSTRING = '    """\n    Two-step on-chain settlement:'

NEW_SETTLE_FUNC = '''def settle_onchain(trade):
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
'''

# We need to find and replace the entire settle_onchain function
if OLD_SETTLE_START in src:
    # Find the start of the function
    func_start = src.find(OLD_SETTLE_START)

    # Find the next top-level function or class definition after it
    # Look for "\ndef " or "\nclass " after the function body
    search_from = func_start + len(OLD_SETTLE_START)
    next_func = src.find("\ndef ", search_from)
    next_comment = src.find("\n# ── Pub/Sub", search_from)

    # Use whichever comes first
    candidates = [x for x in [next_func, next_comment] if x != -1]
    if candidates:
        func_end = min(candidates)
    else:
        print("  ⚠️  Patch 2: Could not find end of settle_onchain — manual fix needed")
        func_end = None

    if func_end:
        src = src[:func_start] + NEW_SETTLE_FUNC + "\n" + src[func_end:]
        patches_applied += 1
        print("  ✅ Patch 2: settle_onchain rewritten with chain_lock + NonceManager + retry")
else:
    print("  ⏭️  Patch 2: settle_onchain not found (may already be patched)")


# ══════════════════════════════════════════════════════════════
# PATCH 3: Reduce Pub/Sub flow control from 5 to 1
# ══════════════════════════════════════════════════════════════
OLD_FLOW = "flow = pubsub_v1.types.FlowControl(max_messages=5)"
NEW_FLOW = "flow = pubsub_v1.types.FlowControl(max_messages=1)  # Serialize to prevent nonce races"

if OLD_FLOW in src:
    src = src.replace(OLD_FLOW, NEW_FLOW, 1)
    patches_applied += 1
    print("  ✅ Patch 3: Flow control reduced to max_messages=1")
elif "max_messages=1" in src:
    print("  ⏭️  Patch 3: Flow control already set to 1")
else:
    print("  ⚠️  Patch 3: Flow control line not found — set manually")


# ══════════════════════════════════════════════════════════════
# Write
# ══════════════════════════════════════════════════════════════
SETTLER.write_text(src, encoding="utf-8")

print()
print(f"  ✅ Task #2 complete — {patches_applied} patches applied to d91_settler.py")
print()
print("  What changed:")
print("    • chain_lock (threading.Lock) serializes ALL on-chain ops")
print("    • NonceManager tracks pending nonces locally per account")
print("    • settle_onchain wrapped in chain_lock context manager")
print("    • Nonce errors trigger resync + 1 automatic retry")
print("    • Pub/Sub flow control reduced to 1 (belt + suspenders)")
print()
print("  Rebuild:")
print("    sudo docker-compose up -d --build settler")
print()
print("  Verify:")
print("    sudo docker logs -f tinyhub-settler")
print("    # Should see ⛓️ ON-CHAIN lines instead of ❌ Chain error")
print()
