"""
TINY-HUB-NETWORK — IL District 91 P2P Energy Marketplace (LIVE DATA)
Replaces random.uniform() with:
  1. MISO real-time 5-min LMP for grid prices (Ameren IL territory)
  2. Solar irradiance model for MWh generation (sun angle + cloud cover)

Loads all sellers/buyers from district91_buildings.json.
Publishes to: district91-energy

Run:
  pip install gridstatus --break-system-packages
  python3 -u d91_marketplace_live.py

Falls back to simulation if MISO API is unreachable.
"""

import os
import json
import time
import math
import hashlib
import random
import threading
from datetime import datetime, timezone
from collections import defaultdict
from google.cloud import pubsub_v1
from weather_feed import get_weather, cloud_factor, print_weather_status
from matching_engine import MatchingEngine, battery_output

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = "tiny-hub-network"
TOPIC_ID = "district91-energy"
TICK_TOPIC = "market-ticks"
TICK_SUB   = "market-ticks-d91-sub"
BUILDINGS_FILE = "district91_buildings.json"
NAMES_FILE = "district91_names.json"
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

# ── Grid Price: MISO Real-Time LMP ──────────────────────────
# D91 is in Ameren Illinois → MISO territory
# LMP is in $/MWh from the ISO, we convert to $/kWh for our marketplace
GRID_PRICE_CACHE = {"price": None, "timestamp": 0, "source": "init"}
GRID_PRICE_LOCK = threading.Lock()
LMP_REFRESH_SECONDS = 300  # refresh every 5 min
USE_GRIDSTATUS = True

try:
    import gridstatus
    miso = gridstatus.MISO()
    print("  [Grid] gridstatus loaded — MISO real-time LMP enabled")
except ImportError:
    USE_GRIDSTATUS = False
    print("  [Grid] gridstatus not installed — using simulation")
    print("         Install with: pip install gridstatus --break-system-packages")


def fetch_miso_lmp():
    """Fetch latest MISO Illinois Hub LMP. Returns $/kWh."""
    global GRID_PRICE_CACHE
    if not USE_GRIDSTATUS:
        return None

    try:
        df = miso.get_lmp("latest", market="REAL_TIME_5_MIN")
        if df is not None and len(df) > 0:
            # Look for Illinois Hub or take average
            il_rows = df[df["Location"].str.contains("ILLINOIS", case=False, na=False)]
            if len(il_rows) > 0:
                lmp_mwh = float(il_rows["LMP"].iloc[0])
            else:
                # Fall back to overall average
                lmp_mwh = float(df["LMP"].mean())

            # Convert $/MWh → $/kWh
            price_kwh = round(lmp_mwh / 1000, 6)
            # Clamp to reasonable range
            price_kwh = max(0.01, min(price_kwh, 0.50))

            with GRID_PRICE_LOCK:
                GRID_PRICE_CACHE = {
                    "price": price_kwh,
                    "timestamp": time.time(),
                    "source": "MISO_LMP",
                    "lmp_mwh": lmp_mwh,
                }
            return price_kwh
    except Exception as e:
        print(f"  [Grid] MISO fetch error: {str(e)[:60]}")
    return None


def get_grid_price_sim():
    """Fallback simulation price."""
    hour = datetime.now(timezone.utc).hour
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


def get_grid_price():
    """Get grid price — real MISO LMP if available, else sim."""
    with GRID_PRICE_LOCK:
        age = time.time() - GRID_PRICE_CACHE["timestamp"]
        if GRID_PRICE_CACHE["price"] is not None and age < LMP_REFRESH_SECONDS:
            # Add small jitter to cached price
            return round(GRID_PRICE_CACHE["price"] * random.uniform(0.95, 1.05), 4)

    # Try to fetch fresh
    price = fetch_miso_lmp()
    if price is not None:
        return round(price * random.uniform(0.95, 1.05), 4)

    # Fallback to sim
    with GRID_PRICE_LOCK:
        GRID_PRICE_CACHE["source"] = "simulated"
    return get_grid_price_sim()


def refresh_grid_price_loop():
    """Background thread to refresh MISO LMP every 5 minutes."""
    while True:
        fetch_miso_lmp()
        time.sleep(LMP_REFRESH_SECONDS)


# ── Solar Irradiance Model ──────────────────────────────────
# Replaces random.uniform() for MWh generation
# Based on sun altitude angle at the building's lat/lng

# D91 center coordinates
D91_LAT = 40.65
D91_LNG = -89.50

def solar_altitude(lat, lng, utc_hour, day_of_year):
    """Calculate solar altitude angle in degrees."""
    # Solar declination
    declination = 23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81)))
    # Approximate solar noon in UTC for this longitude
    solar_noon_utc = 12 - lng / 15
    # Hour angle
    hour_angle = 15 * (utc_hour - solar_noon_utc)
    # Altitude
    alt = math.asin(
        math.sin(math.radians(lat)) * math.sin(math.radians(declination)) +
        math.cos(math.radians(lat)) * math.cos(math.radians(declination)) *
        math.cos(math.radians(hour_angle))
    )
    return math.degrees(alt)


def solar_output(capacity_mwh, lat=D91_LAT, lng=D91_LNG):
    """
    Calculate solar MWh output based on:
    - Sun altitude angle (time of day + season)
    - Cloud cover (random perturbation)
    - Panel efficiency curve
    Returns MWh for this trade interval.
    """
    now = datetime.now(timezone.utc)
    utc_hour = now.hour + now.minute / 60
    day_of_year = now.timetuple().tm_yday

    alt_deg = solar_altitude(lat, lng, utc_hour, day_of_year)

    if alt_deg <= 0:
        # Nighttime — batteries or zero
        # Small chance of battery discharge
        if random.random() < 0.15:
            return round(capacity_mwh * random.uniform(0.05, 0.15), 3)
        return 0.0

    # Irradiance factor: 0 at horizon, 1 at 90°
    irradiance = math.sin(math.radians(alt_deg))

    # Cloud cover: real weather from Open-Meteo
    weather = get_weather(lat, lng)
    cloud = cloud_factor(weather["cloud_cover"])

    # Panel efficiency (degrades slightly at very high/low angles)
    efficiency = 0.85 if alt_deg > 15 else 0.65

    # Output
    mwh = capacity_mwh * irradiance * cloud * efficiency * random.uniform(0.2, 0.4)
    return round(max(0.01, mwh), 3)


# ── Load Building Data ──────────────────────────────────────
print()
print("  Loading building data...")

with open(BUILDINGS_FILE) as f:
    bdata = json.load(f)

names_overlay = {}
if os.path.exists(NAMES_FILE):
    with open(NAMES_FILE) as f:
        names_overlay = json.load(f)
    print(f"  Loaded {len(names_overlay)} name overrides")

# Build SELLERS
SELLERS = []
for i, s in enumerate(bdata["sellers"]):
    osm_id = str(s.get("osm_id", ""))
    ext_name = names_overlay.get(osm_id, "")
    if ext_name and ext_name != "Unidentified":
        label = ext_name
    elif s.get("name"):
        label = s["name"]
    else:
        label = f"{s['category'].title()} {s['town']} #{i+1}"

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
        "lat": s.get("lat", D91_LAT),
        "lng": s.get("lng", D91_LNG),
        "capacity_mwh": sim_cap,
        "real_mwh_yr": s["solar"]["mwh_per_year"],
        "area_sqft": s["area_sqft"],
        "solar_source": s["solar"]["source"],
    })

print(f"  Sellers loaded: {len(SELLERS)}")

# ── EV Battery Residential Nodes ────────────────────────────
# 15% of residential sellers are also EV battery owners.
# They appear in both SELLERS (can discharge) and BUYERS (charge from grid).
# Uses same hash as app.py so map markers match marketplace behavior.

def _is_ev_battery(osm_id, category):
    if category != "residential":
        return False
    h = int(hashlib.md5(str(osm_id).encode()).hexdigest(), 16)
    return (h % 100) < 15

EV_SELLERS = []
EV_BUYERS  = []

# Load from residential_sellers (populated by scan_residential_d91.py)
for r in bdata.get("residential_sellers", []):
    if not r.get("ev_battery", False):
        continue

    osm_id = str(r.get("osm_id", ""))
    label  = r.get("name") or f"EV Home {r.get('county','D91')}"
    ev_cap = r.get("ev_cap_mwh", 0.013)
    town   = r.get("county", "Peoria")
    station_id = f"ev-{osm_id or len(EV_SELLERS)}"

    EV_SELLERS.append({
        "id": station_id,
        "osm_id": osm_id,
        "district": "IL_D91",
        "type": "battery",
        "label": f"⚡ {label[:38]}",
        "town": town,
        "lat": r.get("lat", D91_LAT),
        "lng": r.get("lng", D91_LNG),
        "capacity_mwh": ev_cap,
        "real_mwh_yr": ev_cap * 365,
        "area_sqft": r.get("area_sqft", 1800),
        "solar_source": "ev_battery",
        "is_ev": True,
    })

    EV_BUYERS.append({
        "id": f"evb-{osm_id or len(EV_BUYERS)}",
        "osm_id": osm_id,
        "type": "ev_home",
        "label": f"⚡ {label[:38]}",
        "town": town,
        "max_bid": round(random.uniform(0.12, 0.18), 3),
        "is_ev": True,
    })

print(f"  EV battery homes staged: {len(EV_SELLERS)} sellers + {len(EV_BUYERS)} buyers")

# Build BUYERS
BUYERS = []
for i, b in enumerate(bdata.get("commercial_buyers", [])):
    osm_id = str(b.get("osm_id", ""))
    ext_name = names_overlay.get(osm_id, "")
    if ext_name and ext_name != "Unidentified":
        label = ext_name
    elif b.get("name"):
        label = b["name"]
    else:
        label = f"{b['category'].title()} {b['town']} #{i+1}"

    amenity = b.get("amenity", "")
    shop = b.get("shop", "")
    if amenity in ("school", "library"):
        max_bid = round(random.uniform(0.12, 0.16), 3)
        btype = "school"
    elif amenity in ("hospital", "clinic"):
        max_bid = round(random.uniform(0.20, 0.26), 3)
        btype = "medical"
    elif shop:
        max_bid = round(random.uniform(0.16, 0.22), 3)
        btype = "retail"
    else:
        max_bid = round(random.uniform(0.15, 0.23), 3)
        btype = "business"

    BUYERS.append({
        "id": f"d91-b-{i+1:04d}", "osm_id": osm_id, "type": btype,
        "label": label[:45], "town": b["town"], "max_bid": max_bid,
    })

print(f"  Commercial buyers loaded: {len(BUYERS)}")

# Residential blocks
residential_count = bdata.get("residential_count", 16060)
town_seller_counts = defaultdict(int)
for s in bdata["sellers"]:
    town_seller_counts[s["town"]] += 1
total_seller_count = sum(town_seller_counts.values())
for town, count in sorted(town_seller_counts.items(), key=lambda x: -x[1]):
    share = count / total_seller_count
    homes = max(int(residential_count * share), 50)
    BUYERS.append({
        "id": f"d91-res-{town.lower().replace(' ', '-')}", "osm_id": "", "type": "neighbor",
        "label": f"{town} Residential ({homes:,} homes)", "town": town,
        "max_bid": round(random.uniform(0.14, 0.19), 3),
    })

# Anchor buyers
for ab in [
    {"id": "d91-anc-cat",    "type": "industrial", "label": "Caterpillar Ops Demand",     "town": "East Peoria",   "max_bid": 0.24},
    {"id": "d91-anc-park",   "type": "industrial", "label": "Parker-Hannifin Demand",     "town": "Morton",        "max_bid": 0.23},
    {"id": "d91-anc-nestle", "type": "industrial", "label": "Nestle USA Demand",           "town": "East Peoria",   "max_bid": 0.22},
    {"id": "d91-anc-winpak", "type": "industrial", "label": "Winpak Heat Seal Demand",    "town": "Pekin",         "max_bid": 0.21},
    {"id": "d91-anc-ameren", "type": "grid",       "label": "Ameren IL Buyback",           "town": "District-wide", "max_bid": 0.08},
    {"id": "d91-anc-comed",  "type": "grid",       "label": "ComEd Interconnect",          "town": "District-wide", "max_bid": 0.07},
    {"id": "d91-anc-miso",   "type": "grid",       "label": "MISO Market Buyback",         "town": "District-wide", "max_bid": 0.06},
]:
    ab["osm_id"] = ""
    BUYERS.append(ab)

# Add EV battery homes to main lists
SELLERS.extend(EV_SELLERS)
BUYERS.extend(EV_BUYERS)
print(f"  EV battery homes: {len(EV_SELLERS)} sellers + {len(EV_BUYERS)} buyers")
print(f"  TOTAL BUYERS: {len(BUYERS)}")

# ── Market Parameters ───────────────────────────────────────
AMEREN_TOLL = 0.025

# ── Deterministic order matching engine ─────────────────────
_engine = MatchingEngine(toll=AMEREN_TOLL, mode="pro_rata")
ISLAND_THRESHOLD = 0.32

trade_count = 0
rejected_count = 0
total_profit = 0.0
total_mwh_traded = 0.0
island_events = 0
town_trades = defaultdict(int)
town_mwh = defaultdict(float)
town_profit = defaultdict(float)


def run_trade():
    global trade_count, rejected_count, total_profit, total_mwh_traded, island_events

    grid_price = get_grid_price()
    islanding = grid_price >= ISLAND_THRESHOLD
    if islanding:
        island_events += 1

    # ── Deterministic order matching ───────────────────────
    for seller in SELLERS:
        # Battery VPP: use arbitrage logic instead of solar irradiance
        if seller.get("type") == "battery":
            with GRID_PRICE_LOCK:
                gp = GRID_PRICE_CACHE.get("price") or grid_price
            mwh = battery_output(
                seller["id"], seller.get("label", seller["id"]),
                seller["capacity_mwh"], gp, toll=AMEREN_TOLL
            )
        else:
            mwh = solar_output(seller["capacity_mwh"], seller.get("lat", D91_LAT), seller.get("lng", D91_LNG))
        if mwh <= 0:
            continue
        ask_price = round(grid_price * random.uniform(0.55, 0.85), 4)
        if islanding:
            ask_price = round(grid_price * random.uniform(0.3, 0.5), 4)
        _engine.add_sell_order(
            seller["id"], seller.get("label", seller["id"]),
            seller.get("town", ""), seller.get("type", "solar"),
            mwh, ask_price,
            lat=seller.get("lat"), lng=seller.get("lng"),
        )

    for buyer in BUYERS:
        bid_price = round(min(buyer["max_bid"], grid_price * random.uniform(0.7, 1.1)), 4)
        _engine.add_buy_order(
            buyer["id"], buyer.get("label", buyer["id"]),
            buyer.get("town", ""), buyer.get("type", "business"),
            bid_price, demand_mwh=1.0,
            lat=buyer.get("lat"), lng=buyer.get("lng"),
        )

    matched_trades = _engine.match(grid_price=grid_price)
    _engine.clear()

    if not matched_trades:
        rejected_count += 1
        return

    for mt in matched_trades:
        status = "ISLAND_SETTLED" if islanding else "SETTLED"
        trade_count += 1
        total_profit += mt.net_profit
        total_mwh_traded += mt.mwh
        town_trades[mt.seller_town] = town_trades.get(mt.seller_town, 0) + 1
        town_mwh[mt.seller_town]    = town_mwh.get(mt.seller_town, 0.0) + mt.mwh
        town_profit[mt.seller_town] = town_profit.get(mt.seller_town, 0.0) + mt.net_profit

        with GRID_PRICE_LOCK:
            price_source = GRID_PRICE_CACHE.get("source", "simulated")
            lmp_mwh = GRID_PRICE_CACHE.get("lmp_mwh", 0)
        weather = get_weather(D91_LAT, D91_LNG)

        trade_data = {
            "station_id": mt.seller_id,
            "district": "IL_D91",
            "seller_type": mt.seller_type,
            "seller_label": mt.seller_label,
            "seller_town": mt.seller_town,
            "buyer_id": mt.buyer_id,
            "buyer_type": mt.buyer_type,
            "buyer_label": mt.buyer_label,
            "mwh": mt.mwh,
            "ask_price": mt.ask_price,
            "bid_price": mt.bid_price,
            "settled_price": mt.settled_price,
            "net_profit": mt.net_profit,
            "grid_price": grid_price,
            "trade_status": status,
            "match_type": mt.match_type,
            "distance_km": mt.distance_km,
            "price_source": price_source,
            "lmp_mwh": lmp_mwh,
            "data_mode": "live" if price_source == "MISO_LMP" else "sim",
            "weather_source": weather["source"],
            "cloud_cover": weather["cloud_cover"],
            "temperature": weather["temperature"],
            "dni": weather.get("dni", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        publisher.publish(topic_path, json.dumps(trade_data).encode("utf-8"))

        src = "🛰️" if price_source == "MISO_LMP" else "📊"
        icon = "🏝️" if islanding else "⚡"
        print(f"  {icon}{src} [PR] {mt.seller_label:30} -> {mt.buyer_label:28} | {mt.mwh:6.3f} MWh | Settled: ${mt.settled_price:.4f} | ${mt.net_profit:+.4f} | {status}")

    return  # already published above

    # Get price source
    with GRID_PRICE_LOCK:
        price_source = GRID_PRICE_CACHE.get("source", "simulated")
        lmp_mwh = GRID_PRICE_CACHE.get("lmp_mwh", 0)

    # Get weather for seller location
    weather = get_weather(seller.get("lat", D91_LAT), seller.get("lng", D91_LNG))

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
        "price_source": price_source,
        "lmp_mwh": lmp_mwh,
        "data_mode": "live" if price_source == "MISO_LMP" else "sim",
        "weather_source": weather["source"],
        "cloud_cover": weather["cloud_cover"],
        "temperature": weather["temperature"],
        "dni": weather.get("dni", 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    msg = json.dumps(data).encode("utf-8")
    future = publisher.publish(topic_path, msg)

    src = "🛰️" if price_source == "MISO_LMP" else "📊"
    icon = "🏝️" if islanding else "⚡" if status != "REJECTED" else "❌"
    print(f"  {icon}{src} {seller['label']:30} -> {buyer['label']:28} | {mwh:6.3f} MWh | Grid: ${grid_price:.4f} | Settled: ${settled:.4f} | ${profit:+.4f} | {status}")

    total = trade_count + rejected_count
    if total > 0 and total % 25 == 0:
        rate = trade_count / total * 100
        with GRID_PRICE_LOCK:
            src_info = GRID_PRICE_CACHE.get("source", "?")
            lmp_info = GRID_PRICE_CACHE.get("lmp_mwh", 0)
        print()
        print(f"  ╔═══════════════════════════════════════════════════════════════════════╗")
        print(f"  ║  D91 LIVE SCOREBOARD — Trade #{total:,}                                    ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  Settled: {trade_count:>6}  |  Rejected: {rejected_count:>6}  |  Rate: {rate:>5.1f}%               ║")
        print(f"  ║  MWh traded: {total_mwh_traded:>10.2f}  |  Community profit: ${total_profit:>11.2f}       ║")
        print(f"  ║  Island events: {island_events:>5}  |  Sellers: {len(SELLERS):>5}  |  Buyers: {len(BUYERS):>5}        ║")
        print(f"  ╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"  ║  DATA SOURCE: {src_info:>12}  |  MISO LMP: ${lmp_info:>8.2f}/MWh              ║")
        print(f"  ╚═══════════════════════════════════════════════════════════════════════╝")
        print()


# ── Banner ──────────────────────────────────────────────────
towns = sorted(set(s["town"] for s in SELLERS))
sm = bdata["summary"]

print()
print("  ╔═══════════════════════════════════════════════════════════════════════╗")
print("  ║   TINY-HUB-NETWORK — D91 P2P Energy Marketplace (LIVE DATA)         ║")
print("  ║   Peoria · Tazewell · Woodford · McLean Counties                     ║")
print("  ╠═══════════════════════════════════════════════════════════════════════╣")
print(f"  ║  Sellers:  {len(SELLERS):>5}  |  Buyers: {len(BUYERS):>5}                               ║")
print(f"  ║  Grid price source:  {'MISO Real-Time LMP' if USE_GRIDSTATUS else 'Simulation':>30}       ║")
print(f"  ║  Solar output:       {'Irradiance Model (sun angle)':>30}       ║")
print(f"  ║  Pub/Sub topic:      {TOPIC_ID:>30}       ║")
print(f"  ║  Ameren toll: ${AMEREN_TOLL}/MWh  |  Island: ${ISLAND_THRESHOLD}/MWh                    ║")
print("  ╚═══════════════════════════════════════════════════════════════════════╝")
print()

# Start grid price refresh thread
if USE_GRIDSTATUS:
    threading.Thread(target=refresh_grid_price_loop, daemon=True).start()
    # Initial fetch
    p = fetch_miso_lmp()
    if p:
        print(f"  [Grid] Initial MISO LMP: ${GRID_PRICE_CACHE['lmp_mwh']:.2f}/MWh (${p:.4f}/kWh)")
    else:
        print("  [Grid] Initial MISO fetch failed — using simulation until next refresh")
    print()

# Initial weather check
print_weather_status(D91_LAT, D91_LNG, "D91 Weather")

# ── Cloud Scheduler Tick Mode ──────────────────────────────
# Instead of time.sleep(), we subscribe to the market-ticks
# topic. Cloud Scheduler publishes a message every 5 minutes.
# This is more reliable, auto-restarts on failure, and doesn't
# block the VM with a polling loop.

def on_tick(message):
    """Called by Pub/Sub when a market-tick arrives."""
    message.ack()
    try:
        payload = json.loads(message.data.decode("utf-8"))
        district = payload.get("district", "")
        if district and district != "IL_D91":
            return  # Not our district
    except Exception:
        pass  # Malformed tick — run anyway

    try:
        run_trade()
    except Exception as e:
        print(f"  ⚠️  Trade error on tick: {e}")


def ensure_tick_sub(subscriber):
    """Create the tick subscription if it doesn't exist."""
    tick_topic_path = f"projects/{PROJECT_ID}/topics/{TICK_TOPIC}"
    tick_sub_path   = subscriber.subscription_path(PROJECT_ID, TICK_SUB)
    try:
        subscriber.create_subscription(
            request={
                "name": tick_sub_path,
                "topic": tick_topic_path,
                "ack_deadline_seconds": 60,
            }
        )
        print(f"  ✅ Created tick subscription: {TICK_SUB}")
    except Exception as e:
        if "ALREADY_EXISTS" in str(e) or "lready" in str(e):
            print(f"  ⏭️  Tick subscription exists: {TICK_SUB}")
        else:
            print(f"  ⚠️  Tick sub error (will fall back to local loop): {e}")
            return False
    return True


# Try to set up Cloud Scheduler tick mode
_tick_subscriber = pubsub_v1.SubscriberClient()
_tick_ok = ensure_tick_sub(_tick_subscriber)

if _tick_ok:
    # ── Tick-driven mode (Cloud Scheduler) ─────────────────
    _tick_sub_path = _tick_subscriber.subscription_path(PROJECT_ID, TICK_SUB)
    _streaming = _tick_subscriber.subscribe(_tick_sub_path, callback=on_tick)
    print()
    print("  ⏱  Tick-driven mode active — waiting for Cloud Scheduler ticks")
    print("     (ticks every 5 min from GCP Cloud Scheduler)")
    print("     Ctrl+C to stop.")
    print()
    try:
        _streaming.result()
    except KeyboardInterrupt:
        _streaming.cancel()
        _streaming.result()
else:
    # ── Fallback: local sleep loop ──────────────────────────
    print()
    print("  ⚠️  Falling back to local sleep loop (Cloud Scheduler not reachable)")
    print()
    while True:
        try:
            run_trade()
            time.sleep(300)  # 5 minutes
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(30)

total = trade_count + rejected_count
rate = (trade_count / total * 100) if total > 0 else 0
print()
print("  ╔═══════════════════════════════════════════════════════════════════════╗")
print("  ║                   D91 LIVE FINAL REPORT                              ║")
print("  ╠═══════════════════════════════════════════════════════════════════════╣")
print(f"  ║  Trades settled:    {trade_count:>6}                                           ║")
print(f"  ║  Trades rejected:   {rejected_count:>6}                                           ║")
print(f"  ║  Settlement rate:   {rate:>6.1f}%                                          ║")
print(f"  ║  Total MWh traded:  {total_mwh_traded:>10.2f}                                    ║")
print(f"  ║  Community profit:  ${total_profit:>11.2f}                                    ║")
print(f"  ║  Island events:     {island_events:>6}                                           ║")
print("  ╚═══════════════════════════════════════════════════════════════════════╝")
