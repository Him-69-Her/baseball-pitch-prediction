"""
TINY-HUB-NETWORK — Cross-District Energy Bridge
Connects McHenry D63 ↔ IL District 91 for surplus energy routing.

Subscribes to both Pub/Sub topics:
  - energy-pulse        (D63 — McHenry County, ComEd territory)
  - district91-energy   (D91 — Peoria/Tazewell/Woodford/McLean, Ameren IL)

When a district has surplus (settled trades with no local buyer match),
the bridge re-publishes the offer to the other district's topic with
a bridge toll applied.

Run:  python3 d91_bridge.py
"""
import json
import time
import random
import threading
from datetime import datetime
from collections import defaultdict
from google.cloud import pubsub_v1

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = "tiny-hub-network"
# Topics
D63_TOPIC = "energy-pulse"
D91_TOPIC = "district91-energy"

# Bridge subscriptions (separate from marketplace subs)
D63_BRIDGE_SUB = "energy-pulse-bridge-sub"
D91_BRIDGE_SUB = "district91-energy-bridge-sub"

# Bridge economics
BRIDGE_TOLL = 0.015           # $/MWh toll for cross-district transfer
TRANSMISSION_LOSS = 0.03      # 3% energy lost in transmission
SURPLUS_THRESHOLD = 0.10      # Settled price must be below this to qualify as surplus
BRIDGE_MARKUP = 1.12          # 12% markup on ask price for bridged offers

publisher = pubsub_v1.PublisherClient()
subscriber = pubsub_v1.SubscriberClient()

d63_topic_path = publisher.topic_path(PROJECT_ID, D63_TOPIC)
d91_topic_path = publisher.topic_path(PROJECT_ID, D91_TOPIC)
d63_sub_path = subscriber.subscription_path(PROJECT_ID, D63_BRIDGE_SUB)
d91_sub_path = subscriber.subscription_path(PROJECT_ID, D91_BRIDGE_SUB)

# ── Counters ────────────────────────────────────────────────
stats = {
    "d63_received": 0,
    "d91_received": 0,
    "d63_to_d91": 0,
    "d91_to_d63": 0,
    "d63_surplus_mwh": 0.0,
    "d91_surplus_mwh": 0.0,
    "bridge_profit": 0.0,
    "bridge_rejected": 0,
    "total_mwh_bridged": 0.0,
}
stats_lock = threading.Lock()

# Rolling price windows for surplus detection
d63_prices = []
d91_prices = []
PRICE_WINDOW = 50  # last N trades


def ensure_subscription(sub_path, topic_path, sub_id):
    """Create bridge subscription if it doesn't exist."""
    try:
        subscriber.create_subscription(
            request={
                "name": sub_path,
                "topic": topic_path,
                "ack_deadline_seconds": 30,
                "message_retention_duration": {"seconds": 3600},
                "retain_acked_messages": False,
            }
        )
        print(f"  ✅ Created subscription: {sub_id}")
    except Exception as e:
        if "lready" in str(e) or "ALREADY_EXISTS" in str(e):
            print(f"  ⏭️  Subscription exists: {sub_id}")
        else:
            print(f"  ❌ Subscription error: {e}")
            raise


def get_avg_price(prices):
    """Rolling average of recent settled prices."""
    if not prices:
        return 0.15
    return sum(prices) / len(prices)


def should_bridge(trade, source_prices, dest_prices):
    """
    Decide if a trade should be bridged to the other district.
    Bridge when:
      1. Trade was SETTLED (there's actual supply)
      2. Settled price is below the destination's average (arbitrage exists)
      3. Random factor simulating transmission availability
    """
    if trade.get("trade_status") not in ("SETTLED", "ISLAND_SETTLED"):
        return False

    settled = trade.get("settled_price", 0)
    if settled <= 0:
        return False

    dest_avg = get_avg_price(dest_prices)

    # Arbitrage: source price is cheaper than destination average
    if settled >= dest_avg:
        return False

    # Transmission availability (not every surplus can physically bridge)
    if random.random() > 0.35:
        return False

    return True


def bridge_trade(trade, from_district, to_topic_path, to_district):
    """Re-publish a trade as a bridged offer on the other district's topic."""
    original_mwh = trade["mwh"]
    bridged_mwh = round(original_mwh * (1 - TRANSMISSION_LOSS), 3)
    original_price = trade["settled_price"]
    bridged_ask = round(original_price * BRIDGE_MARKUP + BRIDGE_TOLL, 4)
    profit = round(BRIDGE_TOLL * bridged_mwh, 4)

    bridged_msg = {
        "station_id": trade["station_id"],
        "district": to_district,
        "origin_district": from_district,
        "seller_type": trade.get("seller_type", "bridge"),
        "seller_label": f"[BRIDGE] {trade.get('seller_label', trade.get('station_id', 'unknown'))}",
        "seller_town": trade.get("seller_town", ""),
        "buyer_id": "bridge-pending",
        "buyer_type": "bridge",
        "buyer_label": f"{to_district} Bridge Market",
        "mwh": bridged_mwh,
        "original_mwh": original_mwh,
        "ask_price": bridged_ask,
        "bid_price": 0.0,
        "settled_price": 0.0,
        "net_profit": 0.0,
        "bridge_toll": BRIDGE_TOLL,
        "bridge_profit": profit,
        "grid_price": trade.get("grid_price", 0),
        "trade_status": "BRIDGE_LISTED",
        "transmission_loss_pct": TRANSMISSION_LOSS * 100,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    msg = json.dumps(bridged_msg).encode("utf-8")
    future = publisher.publish(to_topic_path, msg)

    return bridged_mwh, profit, future.result()


def d63_callback(message):
    """Handle messages from D63 (McHenry/ComEd)."""
    message.ack()
    try:
        trade = json.loads(message.data.decode("utf-8"))
    except:
        return

    with stats_lock:
        stats["d63_received"] += 1

    # Track prices
    if trade.get("settled_price", 0) > 0:
        d63_prices.append(trade["settled_price"])
        if len(d63_prices) > PRICE_WINDOW:
            d63_prices.pop(0)

    # Check if should bridge D63 → D91
    if should_bridge(trade, d63_prices, d91_prices):
        try:
            mwh, profit, msg_id = bridge_trade(trade, "McHenry_D63", d91_topic_path, "IL_D91")
            with stats_lock:
                stats["d63_to_d91"] += 1
                stats["d63_surplus_mwh"] += mwh
                stats["bridge_profit"] += profit
                stats["total_mwh_bridged"] += mwh
            seller = trade.get("seller_label", trade.get("station_id", "?"))[:25]
            print(f"  🌉 D63→D91 | {seller:25} | {mwh:.3f} MWh | ${trade['settled_price']:.4f} → bridge | toll: ${profit:.4f}")
        except Exception as e:
            with stats_lock:
                stats["bridge_rejected"] += 1
            print(f"  ❌ Bridge D63→D91 failed: {e}")


def d91_callback(message):
    """Handle messages from D91 (Ameren IL)."""
    message.ack()
    try:
        trade = json.loads(message.data.decode("utf-8"))
    except:
        return

    # Skip messages that are already bridged (avoid loops)
    if trade.get("trade_status") == "BRIDGE_LISTED":
        return

    with stats_lock:
        stats["d91_received"] += 1

    # Track prices
    if trade.get("settled_price", 0) > 0:
        d91_prices.append(trade["settled_price"])
        if len(d91_prices) > PRICE_WINDOW:
            d91_prices.pop(0)

    # Check if should bridge D91 → D63
    if should_bridge(trade, d91_prices, d63_prices):
        try:
            mwh, profit, msg_id = bridge_trade(trade, "IL_D91", d63_topic_path, "McHenry_D63")
            with stats_lock:
                stats["d91_to_d63"] += 1
                stats["d91_surplus_mwh"] += mwh
                stats["bridge_profit"] += profit
                stats["total_mwh_bridged"] += mwh
            seller = trade.get("seller_label", trade.get("station_id", "?"))[:25]
            print(f"  🌉 D91→D63 | {seller:25} | {mwh:.3f} MWh | ${trade['settled_price']:.4f} → bridge | toll: ${profit:.4f}")
        except Exception as e:
            with stats_lock:
                stats["bridge_rejected"] += 1
            print(f"  ❌ Bridge D91→D63 failed: {e}")


def print_scoreboard():
    """Periodic scoreboard output."""
    while True:
        time.sleep(30)
        with stats_lock:
            s = dict(stats)
        total_bridged = s["d63_to_d91"] + s["d91_to_d63"]
        d63_avg = f"${get_avg_price(d63_prices):.4f}" if d63_prices else "N/A"
        d91_avg = f"${get_avg_price(d91_prices):.4f}" if d91_prices else "N/A"

        print()
        print(f"  ╔═══════════════════════════════════════════════════════════════════════╗")
        print(f"  ║  BRIDGE SCOREBOARD — {datetime.utcnow().strftime('%H:%M:%S UTC'):>12}                                ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  D63 messages received:  {s['d63_received']:>6}  |  Avg price: {d63_avg:>8}           ║")
        print(f"  ║  D91 messages received:  {s['d91_received']:>6}  |  Avg price: {d91_avg:>8}           ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  D63 → D91 bridges:  {s['d63_to_d91']:>6}  |  {s['d63_surplus_mwh']:>9.2f} MWh               ║")
        print(f"  ║  D91 → D63 bridges:  {s['d91_to_d63']:>6}  |  {s['d91_surplus_mwh']:>9.2f} MWh               ║")
        print(f"  ║  Total bridged:       {total_bridged:>6}  |  {s['total_mwh_bridged']:>9.2f} MWh               ║")
        print(f"  ║  Bridge toll revenue:          ${s['bridge_profit']:>10.2f}                    ║")
        print(f"  ║  Rejected/failed:     {s['bridge_rejected']:>6}                                       ║")
        print(f"  ╚═══════════════════════════════════════════════════════════════════════╝")
        print()


# ── Setup ───────────────────────────────────────────────────
print()
print("  ╔═══════════════════════════════════════════════════════════════════════╗")
print("  ║     TINY-HUB-NETWORK — Cross-District Energy Bridge                 ║")
print("  ║     McHenry D63 (ComEd) ↔ IL District 91 (Ameren)                   ║")
print("  ╠═══════════════════════════════════════════════════════════════════════╣")
print(f"  ║  D63 topic: {D63_TOPIC:>25}  (McHenry, 11 sellers)           ║")
print(f"  ║  D91 topic: {D91_TOPIC:>25}  (4 counties, 1,289 sellers)     ║")
print(f"  ║  Bridge toll:      ${BRIDGE_TOLL}/MWh                                      ║")
print(f"  ║  Transmission loss: {TRANSMISSION_LOSS*100:.0f}%                                             ║")
print(f"  ║  Bridge markup:     {(BRIDGE_MARKUP-1)*100:.0f}%                                             ║")
print("  ╚═══════════════════════════════════════════════════════════════════════╝")
print()

# Create bridge subscriptions
ensure_subscription(d63_sub_path, d63_topic_path, D63_BRIDGE_SUB)
ensure_subscription(d91_sub_path, d91_topic_path, D91_BRIDGE_SUB)
print()

# ── Subscribe ───────────────────────────────────────────────
print("  Starting listeners...")

flow_control = pubsub_v1.types.FlowControl(max_messages=10)

d63_future = subscriber.subscribe(d63_sub_path, callback=d63_callback, flow_control=flow_control)
print(f"  ✅ Listening on {D63_BRIDGE_SUB}")

d91_future = subscriber.subscribe(d91_sub_path, callback=d91_callback, flow_control=flow_control)
print(f"  ✅ Listening on {D91_BRIDGE_SUB}")

# Start scoreboard thread
scoreboard_thread = threading.Thread(target=print_scoreboard, daemon=True)
scoreboard_thread.start()

print()
print("  🌉 Bridge active. Ctrl+C to stop.")
print("  ─────────────────────────────────────────────────────────────────")
print()

# ── Main Loop ───────────────────────────────────────────────
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    d63_future.cancel()
    d91_future.cancel()

    with stats_lock:
        s = dict(stats)

    total_bridged = s["d63_to_d91"] + s["d91_to_d63"]
    print()
    print("  ╔═══════════════════════════════════════════════════════════════════════╗")
    print("  ║                    BRIDGE FINAL REPORT                               ║")
    print("  ╠═══════════════════════════════════════════════════════════════════════╣")
    print(f"  ║  D63 messages processed: {s['d63_received']:>6}                                      ║")
    print(f"  ║  D91 messages processed: {s['d91_received']:>6}                                      ║")
    print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
    print(f"  ║  D63 → D91 bridges:  {s['d63_to_d91']:>6}  |  {s['d63_surplus_mwh']:>9.2f} MWh                ║")
    print(f"  ║  D91 → D63 bridges:  {s['d91_to_d63']:>6}  |  {s['d91_surplus_mwh']:>9.2f} MWh                ║")
    print(f"  ║  Total bridged:       {total_bridged:>6}  |  {s['total_mwh_bridged']:>9.2f} MWh                ║")
    print(f"  ║  Bridge toll revenue:          ${s['bridge_profit']:>10.2f}                     ║")
    print(f"  ║  Rejected/failed:     {s['bridge_rejected']:>6}                                        ║")
    print("  ╚═══════════════════════════════════════════════════════════════════════╝")
