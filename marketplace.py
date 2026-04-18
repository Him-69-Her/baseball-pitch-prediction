import json
import time
import random
from datetime import datetime
from google.cloud import pubsub_v1

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "tinyhub-data-dev")
TOPIC_ID = "energy-pulse"
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

SELLERS = [
    # Rooftop Solar (from audit)
    {"id": "coin-base-1", "district": "McHenry_D63", "type": "commercial", "label": "Walmart Woodstock", "capacity_mwh": 4.2},
    {"id": "coin-base-2", "district": "McHenry_D63", "type": "commercial", "label": "NW Medicine", "capacity_mwh": 1.9},
    {"id": "coin-base-3", "district": "McHenry_D63", "type": "commercial", "label": "Jewel-Osco", "capacity_mwh": 0.16},
    {"id": "coin-base-4", "district": "McHenry_D63", "type": "commercial", "label": "Walmart Huntley", "capacity_mwh": 3.3},
    {"id": "coin-base-5", "district": "McHenry_D63", "type": "residential", "label": "Woodstock Homes", "capacity_mwh": 0.8},
    {"id": "coin-base-6", "district": "McHenry_D63", "type": "municipal", "label": "Marengo Municipal", "capacity_mwh": 1.2},
    # Existing Solar Farms
    {"id": "farm-marengo-solar", "district": "McHenry_D63", "type": "solar_farm", "label": "Marengo Solar Farm", "capacity_mwh": 6.0},
    {"id": "farm-nexamp-harvard", "district": "McHenry_D63", "type": "solar_farm", "label": "Nexamp Harvard", "capacity_mwh": 3.0},
    {"id": "farm-hebron", "district": "McHenry_D63", "type": "solar_farm", "label": "Hebron Solar", "capacity_mwh": 2.5},
    # Existing Battery Storage
    {"id": "batt-marengo", "district": "McHenry_D63", "type": "battery", "label": "Marengo Battery 20MW", "capacity_mwh": 20.0},
    {"id": "batt-mchenry", "district": "McHenry_D63", "type": "battery", "label": "McHenry Battery 20MW", "capacity_mwh": 20.0},
]

BUYERS = [
    {"id": "buyer-neighbor-1", "type": "neighbor", "label": "Residential Block A", "max_bid": 0.18},
    {"id": "buyer-neighbor-2", "type": "neighbor", "label": "Residential Block B", "max_bid": 0.16},
    {"id": "buyer-school-1", "type": "school", "label": "Woodstock North HS", "max_bid": 0.15},
    {"id": "buyer-school-2", "type": "school", "label": "Marengo High School", "max_bid": 0.14},
    {"id": "buyer-biz-1", "type": "business", "label": "Route 47 Strip Mall", "max_bid": 0.20},
    {"id": "buyer-biz-2", "type": "business", "label": "NW Medicine Ops", "max_bid": 0.22},
    {"id": "buyer-dc-1", "type": "datacenter", "label": "Google Aurora Hub", "max_bid": 0.25},
    {"id": "buyer-dc-2", "type": "datacenter", "label": "Equinix Chicago", "max_bid": 0.23},
    {"id": "buyer-grid-1", "type": "grid", "label": "ComEd Buyback", "max_bid": 0.08},
    {"id": "buyer-muni-1", "type": "municipal", "label": "Harvard Fire Dept", "max_bid": 0.14},
    {"id": "buyer-muni-2", "type": "municipal", "label": "Woodstock PD", "max_bid": 0.15},
]

COMED_TOLL = 0.02
ISLAND_THRESHOLD = 0.30

trade_count = 0
rejected_count = 0
total_profit = 0
total_mwh_traded = 0
island_events = 0

def get_grid_price():
    hour = datetime.utcnow().hour
    base = 0.04 if (hour < 6 or hour > 22) else 0.20
    spike = random.random()
    if spike > 0.92:
        return round(base * random.uniform(2.5, 4.0), 4)
    return round(base * random.uniform(0.8, 1.3), 4)

def run_trade():
    global trade_count, rejected_count, total_profit, total_mwh_traded, island_events

    grid_price = get_grid_price()
    islanding = grid_price >= ISLAND_THRESHOLD

    if islanding:
        island_events += 1

    seller = random.choice(SELLERS)
    buyer = random.choice(BUYERS)
    mwh = round(random.uniform(0.1, seller["capacity_mwh"] * 0.4), 3)
    ask_price = round(grid_price * random.uniform(0.55, 0.85), 4)

    if islanding:
        ask_price = round(grid_price * random.uniform(0.3, 0.5), 4)

    bid_price = round(min(buyer["max_bid"], grid_price * random.uniform(0.7, 1.1)), 4)
    settled = round((ask_price + bid_price) / 2, 4)
    profit = round((settled - COMED_TOLL) * mwh, 4)

    if bid_price >= ask_price:
        status = "ISLAND_SETTLED" if islanding else "SETTLED"
        trade_count += 1
        total_profit += profit
        total_mwh_traded += mwh
    else:
        status = "REJECTED"
        rejected_count += 1
        settled = 0.0
        profit = 0.0

    data = {
        "station_id": seller["id"],
        "district": seller["district"],
        "seller_type": seller["type"],
        "buyer_type": buyer["type"],
        "mwh": mwh,
        "ask_price": ask_price,
        "bid_price": bid_price,
        "settled_price": settled,
        "net_profit": profit,
        "trade_status": status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    msg = json.dumps(data).encode("utf-8")
    future = publisher.publish(topic_path, msg)

    icon = "🏝️" if islanding else "⚡" if status != "REJECTED" else "❌"
    print(f"{icon} {seller['label']:22} -> {buyer['label']:20} | {mwh:6.3f} MWh | Grid: ${grid_price:.4f} | Settled: ${settled:.4f} | Profit: ${profit:.4f} | {status}")

    total = trade_count + rejected_count
    if total > 0 and total % 15 == 0:
        rate = trade_count / total * 100
        print()
        print(f"  ╔══════════════════════════════════════════════════════════════╗")
        print(f"  ║  SCOREBOARD                                                ║")
        print(f"  ║  Trades settled: {trade_count:>6}  |  Rejected: {rejected_count:>6}  |  Rate: {rate:>5.1f}%  ║")
        print(f"  ║  MWh traded:  {total_mwh_traded:>9.2f}  |  Community profit: ${total_profit:>10.2f}  ║")
        print(f"  ║  Island events: {island_events:>5}  |  Sellers: {len(SELLERS):>2}  |  Buyers: {len(BUYERS):>2}    ║")
        print(f"  ╚══════════════════════════════════════════════════════════════╝")
        print()

print()
print("  ╔══════════════════════════════════════════════════════════════╗")
print("  ║         TINY-HUB-NETWORK P2P ENERGY MARKETPLACE            ║")
print("  ║              McHenry County — Live Simulation               ║")
print("  ╠══════════════════════════════════════════════════════════════╣")
print(f"  ║  Sellers: {len(SELLERS):>2} nodes (rooftop + solar farms + batteries)   ║")
print(f"  ║  Buyers:  {len(BUYERS):>2} community members                          ║")
print(f"  ║  ComEd toll: ${COMED_TOLL}/MWh                                   ║")
print(f"  ║  Island threshold: ${ISLAND_THRESHOLD}/MWh (auto-disconnect)          ║")
print("  ╚══════════════════════════════════════════════════════════════╝")
print()

while True:
    try:
        run_trade()
        time.sleep(random.uniform(3, 8))
    except KeyboardInterrupt:
        total = trade_count + rejected_count
        rate = (trade_count / total * 100) if total > 0 else 0
        print()
        print("  ╔══════════════════════════════════════════════════════════════╗")
        print("  ║                      FINAL REPORT                           ║")
        print("  ╠══════════════════════════════════════════════════════════════╣")
        print(f"  ║  Trades settled:    {trade_count:>6}                                 ║")
        print(f"  ║  Trades rejected:   {rejected_count:>6}                                 ║")
        print(f"  ║  Settlement rate:   {rate:>6.1f}%                                ║")
        print(f"  ║  Total MWh traded:  {total_mwh_traded:>9.2f}                            ║")
        print(f"  ║  Community profit:  ${total_profit:>10.2f}                           ║")
        print(f"  ║  Island events:     {island_events:>6}                                 ║")
        print("  ╚══════════════════════════════════════════════════════════════╝")
        break
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)

