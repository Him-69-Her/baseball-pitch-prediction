"""
TINY-HUB-NETWORK — IL District 91 P2P Energy Marketplace (Full Network)
Live simulation across 15 towns in Peoria/Tazewell/Woodford/McLean counties.

Loads ALL sellers and buyers from district91_buildings.json at runtime:
  - 1,289 qualified sellers (≥5,000 sqft commercial/institutional rooftops)
  - 500 commercial buyers (from OSM scan)
  - 16,060 residential homes (aggregated into block buyers per town)
  - Grid buyback + industrial demand + institutional anchor buyers

Publishes to: district91-energy
Run:  python3 d91_marketplace.py
"""

import os
import json
import time
import random
from datetime import datetime
from collections import defaultdict
from google.cloud import pubsub_v1

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = "tiny-hub-network"
TOPIC_ID = "district91-energy"
BUILDINGS_FILE = "district91_buildings.json"
NAMES_FILE = "district91_names.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

# ── Load building data ──────────────────────────────────────
print()
print("  Loading building data...")

with open(BUILDINGS_FILE) as f:
    bdata = json.load(f)

# Load names overlay
names_overlay = {}
if os.path.exists(NAMES_FILE):
    with open(NAMES_FILE) as f:
        names_overlay = json.load(f)
    print(f"  Loaded {len(names_overlay)} name overrides")

# ── Build SELLERS from JSON ─────────────────────────────────
SELLERS = []
for i, s in enumerate(bdata["sellers"]):
    osm_id = str(s.get("osm_id", ""))
    ext_name = names_overlay.get(osm_id, "")

    # Best available label
    if ext_name and ext_name != "Unidentified":
        label = ext_name
    elif s.get("name"):
        label = s["name"]
    else:
        label = f"{s['category'].title()} {s['town']} #{i+1}"

    # Sim capacity: annual MWh / 1000, capped at 25 for sim pacing
    raw_mwh = s.get("capacity_mwh", 0) or s["solar"]["mwh_per_year"]
    sim_cap = round(min(raw_mwh / 1000, 25.0), 2)
    if sim_cap < 0.05:
        sim_cap = 0.05

    SELLERS.append({
        "id": f"d91-s-{i+1:04d}",
        "osm_id": osm_id,
        "district": "IL_D91",
        "type": s["category"],
        "label": label[:45],
        "town": s["town"],
        "capacity_mwh": sim_cap,
        "real_mwh_yr": s["solar"]["mwh_per_year"],
        "area_sqft": s["area_sqft"],
        "solar_source": s["solar"]["source"],
    })

print(f"  Sellers loaded: {len(SELLERS)}")

# ── Build BUYERS from JSON ──────────────────────────────────
BUYERS = []

# 1) All commercial buyers from the scan
for i, b in enumerate(bdata.get("commercial_buyers", [])):
    osm_id = str(b.get("osm_id", ""))
    ext_name = names_overlay.get(osm_id, "")

    if ext_name and ext_name != "Unidentified":
        label = ext_name
    elif b.get("name"):
        label = b["name"]
    else:
        label = f"{b['category'].title()} {b['town']} #{i+1}"

    # Max bid based on category/amenity
    amenity = b.get("amenity", "")
    shop = b.get("shop", "")
    if amenity in ("school", "library"):
        max_bid = round(random.uniform(0.12, 0.16), 3)
        btype = "school"
    elif amenity in ("hospital", "clinic"):
        max_bid = round(random.uniform(0.20, 0.26), 3)
        btype = "medical"
    elif amenity in ("theatre", "community_centre"):
        max_bid = round(random.uniform(0.14, 0.18), 3)
        btype = "civic"
    elif shop:
        max_bid = round(random.uniform(0.16, 0.22), 3)
        btype = "retail"
    else:
        max_bid = round(random.uniform(0.15, 0.23), 3)
        btype = "business"

    BUYERS.append({
        "id": f"d91-b-{i+1:04d}",
        "osm_id": osm_id,
        "type": btype,
        "label": label[:45],
        "town": b["town"],
        "max_bid": max_bid,
    })

print(f"  Commercial buyers loaded: {len(BUYERS)}")

# 2) Residential block buyers — one per town, weighted by density
residential_count = bdata.get("residential_count", 16060)
town_seller_counts = defaultdict(int)
for s in bdata["sellers"]:
    town_seller_counts[s["town"]] += 1

total_seller_count = sum(town_seller_counts.values())
res_buyers_added = 0
for town, count in sorted(town_seller_counts.items(), key=lambda x: -x[1]):
    share = count / total_seller_count
    homes = max(int(residential_count * share), 50)
    block_id = f"d91-res-{town.lower().replace(' ', '-')}"
    BUYERS.append({
        "id": block_id,
        "osm_id": "",
        "type": "neighbor",
        "label": f"{town} Residential ({homes:,} homes)",
        "town": town,
        "max_bid": round(random.uniform(0.14, 0.19), 3),
        "homes": homes,
    })
    res_buyers_added += 1

print(f"  Residential block buyers: {res_buyers_added} (representing {residential_count:,} homes)")

# 3) Anchor buyers — grid, heavy industry, institutional
ANCHOR_BUYERS = [
    {"id": "d91-anc-cat",    "type": "industrial", "label": "Caterpillar Ops Demand",     "town": "East Peoria",   "max_bid": 0.24},
    {"id": "d91-anc-park",   "type": "industrial", "label": "Parker-Hannifin Demand",     "town": "Morton",        "max_bid": 0.23},
    {"id": "d91-anc-nestle", "type": "industrial", "label": "Nestle USA Demand",           "town": "East Peoria",   "max_bid": 0.22},
    {"id": "d91-anc-winpak", "type": "industrial", "label": "Winpak Heat Seal Demand",    "town": "Pekin",         "max_bid": 0.21},
    {"id": "d91-anc-morton", "type": "industrial", "label": "Morton Industries Demand",    "town": "Morton",        "max_bid": 0.20},
    {"id": "d91-anc-hanna",  "type": "industrial", "label": "Hanna Steel Demand",          "town": "Pekin",         "max_bid": 0.22},
    {"id": "d91-anc-museum", "type": "municipal",  "label": "Peoria Riverfront Museum",    "town": "East Peoria",   "max_bid": 0.16},
    {"id": "d91-anc-embassy","type": "municipal",  "label": "Embassy Suites EP",            "town": "East Peoria",   "max_bid": 0.21},
    {"id": "d91-anc-grace",  "type": "municipal",  "label": "Grace Church Washington",     "town": "Washington",    "max_bid": 0.14},
    {"id": "d91-anc-ameren", "type": "grid",       "label": "Ameren IL Buyback",            "town": "District-wide", "max_bid": 0.08},
    {"id": "d91-anc-comed",  "type": "grid",       "label": "ComEd Interconnect",           "town": "District-wide", "max_bid": 0.07},
    {"id": "d91-anc-miso",   "type": "grid",       "label": "MISO Market Buyback",          "town": "District-wide", "max_bid": 0.06},
]

for ab in ANCHOR_BUYERS:
    ab["osm_id"] = ""
BUYERS.extend(ANCHOR_BUYERS)

print(f"  Anchor buyers: {len(ANCHOR_BUYERS)}")
print(f"  TOTAL BUYERS: {len(BUYERS)}")

# ── Market Parameters ───────────────────────────────────────
AMEREN_TOLL = 0.025
ISLAND_THRESHOLD = 0.32

# ── Counters ────────────────────────────────────────────────
trade_count = 0
rejected_count = 0
total_profit = 0.0
total_mwh_traded = 0.0
island_events = 0

# Per-town stats
town_trades = defaultdict(int)
town_mwh = defaultdict(float)
town_profit = defaultdict(float)


def get_grid_price():
    """Ameren IL real-time price simulation."""
    hour = datetime.utcnow().hour
    if hour < 6 or hour > 22:
        base = 0.035
    elif 16 <= hour <= 20:
        base = 0.24
    else:
        base = 0.18
    spike = random.random()
    if spike > 0.90:
        return round(base * random.uniform(2.5, 4.5), 4)
    return round(base * random.uniform(0.75, 1.35), 4)


def run_trade():
    global trade_count, rejected_count, total_profit, total_mwh_traded, island_events

    grid_price = get_grid_price()
    islanding = grid_price >= ISLAND_THRESHOLD

    if islanding:
        island_events += 1

    seller = random.choice(SELLERS)
    buyer = random.choice(BUYERS)
    mwh = round(random.uniform(0.05, seller["capacity_mwh"] * 0.4), 3)
    ask_price = round(grid_price * random.uniform(0.55, 0.85), 4)

    if islanding:
        ask_price = round(grid_price * random.uniform(0.3, 0.5), 4)

    bid_price = round(min(buyer["max_bid"], grid_price * random.uniform(0.7, 1.1)), 4)
    settled = round((ask_price + bid_price) / 2, 4)
    profit = round((settled - AMEREN_TOLL) * mwh, 4)

    if bid_price >= ask_price:
        status = "ISLAND_SETTLED" if islanding else "SETTLED"
        trade_count += 1
        total_profit += profit
        total_mwh_traded += mwh
        town_trades[seller["town"]] += 1
        town_mwh[seller["town"]] += mwh
        town_profit[seller["town"]] += profit
    else:
        status = "REJECTED"
        rejected_count += 1
        settled = 0.0
        profit = 0.0

    data = {
        "station_id": seller["id"],
        "district": seller["district"],
        "seller_type": seller["type"],
        "seller_label": seller["label"],
        "seller_town": seller["town"],
        "buyer_id": buyer["id"],
        "buyer_type": buyer["type"],
        "buyer_label": buyer["label"],
        "mwh": mwh,
        "ask_price": ask_price,
        "bid_price": bid_price,
        "settled_price": settled,
        "net_profit": profit,
        "grid_price": grid_price,
        "trade_status": status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    msg = json.dumps(data).encode("utf-8")
    future = publisher.publish(topic_path, msg)

    icon = "🏝️" if islanding else "⚡" if status != "REJECTED" else "❌"
    print(f"  {icon} {seller['label']:30} -> {buyer['label']:30} | {mwh:6.3f} MWh | Grid: ${grid_price:.4f} | Settled: ${settled:.4f} | ${profit:+.4f} | {status}")

    # Scoreboard every 25 trades
    total = trade_count + rejected_count
    if total > 0 and total % 25 == 0:
        rate = trade_count / total * 100
        print()
        print(f"  ╔═══════════════════════════════════════════════════════════════════════╗")
        print(f"  ║  D91 SCOREBOARD — Trade #{total:,}                                        ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  Settled: {trade_count:>6}  |  Rejected: {rejected_count:>6}  |  Rate: {rate:>5.1f}%               ║")
        print(f"  ║  MWh traded: {total_mwh_traded:>10.2f}  |  Community profit: ${total_profit:>11.2f}       ║")
        print(f"  ║  Island events: {island_events:>5}  |  Sellers: {len(SELLERS):>5}  |  Buyers: {len(BUYERS):>5}        ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  TOP TOWNS BY MWh:                                                  ║")
        sorted_towns = sorted(town_mwh.items(), key=lambda x: -x[1])[:5]
        for t_name, t_mwh in sorted_towns:
            t_trades = town_trades[t_name]
            t_profit = town_profit[t_name]
            print(f"  ║    {t_name:20} | {t_trades:>5} trades | {t_mwh:>9.2f} MWh | ${t_profit:>9.2f}   ║")
        print(f"  ╚═══════════════════════════════════════════════════════════════════════╝")
        print()


# ── Banner ──────────────────────────────────────────────────
towns = sorted(set(s["town"] for s in SELLERS))
total_cap = sum(s["capacity_mwh"] for s in SELLERS)
total_real = sum(s["real_mwh_yr"] for s in SELLERS)
api_sellers = sum(1 for s in SELLERS if s["solar_source"] == "solar_api")
sm = bdata["summary"]

print()
print("  ╔═══════════════════════════════════════════════════════════════════════╗")
print("  ║       TINY-HUB-NETWORK — IL District 91 P2P Energy Marketplace      ║")
print("  ║       Peoria · Tazewell · Woodford · McLean Counties                 ║")
print("  ╠═══════════════════════════════════════════════════════════════════════╣")
print(f"  ║  Sellers:  {len(SELLERS):>5} nodes across {len(towns)} towns                           ║")
print(f"  ║  Buyers:   {len(BUYERS):>5} (commercial + residential blocks + anchors)        ║")
print(f"  ║  Buildings scanned: {sm['total_buildings']:>6,}                                       ║")
print(f"  ║  Solar API verified: {api_sellers:>5} / {len(SELLERS)} sellers                         ║")
print(f"  ║  Real MWh/yr potential: {total_real:>12,.2f}                                ║")
print(f"  ║  Sim capacity total:    {total_cap:>9,.2f} MWh                                ║")
print(f"  ║  Roof space:  {sm['seller_roof_sqft']:>12,} sqft                                  ║")
print(f"  ║  Solar panels: {sm['seller_panels']:>11,}                                         ║")
print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
print(f"  ║  Ameren toll: ${AMEREN_TOLL}/MWh  |  Island threshold: ${ISLAND_THRESHOLD}/MWh          ║")
print(f"  ║  Pub/Sub topic: {TOPIC_ID}                                          ║")
print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
print(f"  ║  Towns: {', '.join(towns[:6]):63}  ║")
print(f"  ║         {', '.join(towns[6:]):63}  ║")
print(f"  ╚═══════════════════════════════════════════════════════════════════════╝")
print()

# ── Main Loop ───────────────────────────────────────────────
while True:
    try:
        run_trade()
        time.sleep(random.uniform(2, 6))
    except KeyboardInterrupt:
        total = trade_count + rejected_count
        rate = (trade_count / total * 100) if total > 0 else 0
        print()
        print("  ╔═══════════════════════════════════════════════════════════════════════╗")
        print("  ║                      D91 FINAL REPORT                                ║")
        print("  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  Trades settled:    {trade_count:>6}                                           ║")
        print(f"  ║  Trades rejected:   {rejected_count:>6}                                           ║")
        print(f"  ║  Settlement rate:   {rate:>6.1f}%                                          ║")
        print(f"  ║  Total MWh traded:  {total_mwh_traded:>10.2f}                                    ║")
        print(f"  ║  Community profit:  ${total_profit:>11.2f}                                    ║")
        print(f"  ║  Island events:     {island_events:>6}                                           ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  FINAL TOWN BREAKDOWN:                                               ║")
        for t_name in sorted(town_mwh.keys(), key=lambda x: -town_mwh[x]):
            t_trades = town_trades[t_name]
            t_mwh_val = town_mwh[t_name]
            t_profit_val = town_profit[t_name]
            print(f"  ║    {t_name:20} | {t_trades:>5} trades | {t_mwh_val:>9.2f} MWh | ${t_profit_val:>9.2f}    ║")
        print(f"  ╚═══════════════════════════════════════════════════════════════════════╝")
        break
    except Exception as e:
        print(f"  Error: {e}")
        time.sleep(5)
