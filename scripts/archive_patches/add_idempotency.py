#!/usr/bin/env python3
"""
TINY-HUB — Add idempotency keys to d91_settler.py

Patches three things:
  1. Adds seen_ids set + lock after the stats dict
  2. Adds duplicate check at the top of on_trade()
  3. Adds "duplicates" counter to stats dict and scoreboard

Run from your project root:
    python3 add_idempotency.py
"""

from pathlib import Path

TARGET = Path("d91_settler.py")

if not TARGET.exists():
    print(f"  ❌ {TARGET} not found. Run from your project root.")
    exit(1)

source = TARGET.read_text(encoding="utf-8")

# ── Patch 1: Add seen_ids after stats dict ──────────────────
OLD_STATS = '''"skipped": 0,
    "gas_used": 0,
    "thn_minted": 0.0,
    "thn_burned": 0.0,
}
stats_lock = threading.Lock()'''

NEW_STATS = '''"skipped": 0,
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
        return False'''

if OLD_STATS not in source:
    print("  ❌ Patch 1 failed — stats block not found. Has the file changed?")
    exit(1)

source = source.replace(OLD_STATS, NEW_STATS, 1)
print("  ✅ Patch 1: seen_ids set added")

# ── Patch 2: Add duplicate check inside on_trade() ─────────
OLD_ON_TRADE = '''def on_trade(message, source):
    message.ack()
    try:
        trade = json.loads(message.data.decode("utf-8"))
    except:
        return

    status = trade.get("trade_status", "")'''

NEW_ON_TRADE = '''def on_trade(message, source):
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

    status = trade.get("trade_status", "")'''

if OLD_ON_TRADE not in source:
    print("  ❌ Patch 2 failed — on_trade() signature not found. Has the file changed?")
    exit(1)

source = source.replace(OLD_ON_TRADE, NEW_ON_TRADE, 1)
print("  ✅ Patch 2: duplicate check added to on_trade()")

# ── Patch 3: Add duplicates to scoreboard print ─────────────
OLD_SCOREBOARD = '''    print(f"  ║  Skipped (rejected):  {s['skipped']:>6}                                         ║")'''

NEW_SCOREBOARD = '''    print(f"  ║  Skipped (rejected):  {s['skipped']:>6}                                         ║")
        print(f"  ║  Duplicates blocked:  {s['duplicates']:>6}                                         ║")'''

if OLD_SCOREBOARD not in source:
    print("  ⚠️  Patch 3: scoreboard line not found — skipping (non-critical)")
else:
    source = source.replace(OLD_SCOREBOARD, NEW_SCOREBOARD, 1)
    print("  ✅ Patch 3: duplicates counter added to scoreboard")

# ── Write result ────────────────────────────────────────────
TARGET.write_text(source, encoding="utf-8")
print()
print("  ✅ d91_settler.py patched successfully.")
print("     Restart d91_settler.py to apply.")
print()
