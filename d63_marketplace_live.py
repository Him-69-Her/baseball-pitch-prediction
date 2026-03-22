"""
TINY-HUB-NETWORK — McHenry County D63 P2P Energy Marketplace (LIVE DATA)
Replaces random.uniform() with:
  1. PJM real-time LMP for grid prices (ComEd is in PJM territory)
  2. Solar irradiance model for MWh generation (sun angle + cloud cover)

Publishes to: energy-pulse

Run:
  pip install gridstatus --break-system-packages
  python3 -u d63_marketplace_live.py

Falls back to simulation if PJM API is unreachable.
"""

import os
import json
import time
import math
import random
import threading
from datetime import datetime, timezone
from google.cloud import pubsub_v1
from weather_feed import get_weather, cloud_factor, print_weather_status

# ── Config ──────────────────────────────────────────────────
PROJECT_ID = "tiny-hub-network"
TOPIC_ID = "energy-pulse"
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

# ── Grid Price: PJM Real-Time LMP ───────────────────────────
# D63 is ComEd territory → PJM
GRID_PRICE_CACHE = {"price": None, "timestamp": 0, "source": "init"}
GRID_PRICE_LOCK = threading.Lock()
LMP_REFRESH_SECONDS = 300
USE_GRIDSTATUS = True

try:
    import gridstatus
    pjm_key = os.environ.get("PJM_API_KEY")
    if pjm_key:
        pjm = gridstatus.PJM(api_key=pjm_key)
        print("  [Grid] gridstatus loaded — PJM real-time LMP enabled")
    else:
        # Try without key — some public endpoints work
        try:
            pjm = gridstatus.PJM(api_key="ANONYMOUS")
            print("  [Grid] gridstatus loaded — PJM public endpoints (no key)")
        except:
            USE_GRIDSTATUS = False
            print("  [Grid] PJM needs API key — using sim prices + real weather")
except ImportError:
    USE_GRIDSTATUS = False
    print("  [Grid] gridstatus not installed — using simulation")


def fetch_pjm_lmp():
    """Fetch latest PJM Hub LMP. Returns $/kWh."""
    global GRID_PRICE_CACHE
    if not USE_GRIDSTATUS:
        return None
    try:
        df = pjm.get_lmp("latest", market="REAL_TIME_5_MIN", locations="hubs")
        if df is not None and len(df) > 0:
            # Average across hub nodes
            lmp_mwh = float(df["LMP"].mean())
            price_kwh = round(lmp_mwh / 1000, 6)
            price_kwh = max(0.01, min(price_kwh, 0.50))

            with GRID_PRICE_LOCK:
                GRID_PRICE_CACHE = {
                    "price": price_kwh,
                    "timestamp": time.time(),
                    "source": "PJM_LMP",
                    "lmp_mwh": lmp_mwh,
                }
            return price_kwh
    except Exception as e:
        print(f"  [Grid] PJM fetch error: {str(e)[:60]}")
    return None


def get_grid_price_sim():
    """Fallback simulation price."""
    hour = datetime.now(timezone.utc).hour
    if hour < 6 or hour > 22:
        base = 0.04
    elif 16 <= hour <= 20:
        base = 0.22
    else:
        base = 0.16
    spike = random.random()
    if spike > 0.92:
        return round(base * random.uniform(2.5, 4.0), 4)
    return round(base * random.uniform(0.8, 1.3), 4)


def get_grid_price():
    """Get grid price — real PJM LMP if available, else sim."""
    with GRID_PRICE_LOCK:
        age = time.time() - GRID_PRICE_CACHE["timestamp"]
        if GRID_PRICE_CACHE["price"] is not None and age < LMP_REFRESH_SECONDS:
            return round(GRID_PRICE_CACHE["price"] * random.uniform(0.95, 1.05), 4)

    price = fetch_pjm_lmp()
    if price is not None:
        return round(price * random.uniform(0.95, 1.05), 4)

    with GRID_PRICE_LOCK:
        GRID_PRICE_CACHE["source"] = "simulated"
    return get_grid_price_sim()


def refresh_grid_price_loop():
    """Background thread to refresh PJM LMP."""
    while True:
        fetch_pjm_lmp()
        time.sleep(LMP_REFRESH_SECONDS)


# ── Solar Irradiance Model ──────────────────────────────────
D63_LAT = 42.30
D63_LNG = -88.50

def solar_altitude(lat, lng, utc_hour, day_of_year):
    """Calculate solar altitude angle in degrees."""
    declination = 23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81)))
    solar_noon_utc = 12 - lng / 15
    hour_angle = 15 * (utc_hour - solar_noon_utc)
    alt = math.asin(
        math.sin(math.radians(lat)) * math.sin(math.radians(declination)) +
        math.cos(math.radians(lat)) * math.cos(math.radians(declination)) *
        math.cos(math.radians(hour_angle))
    )
    return math.degrees(alt)


def solar_output(capacity_mwh, lat=D63_LAT, lng=D63_LNG, is_battery=False):
    """Solar MWh output based on irradiance model."""
    now = datetime.now(timezone.utc)
    utc_hour = now.hour + now.minute / 60
    day_of_year = now.timetuple().tm_yday

    # Batteries can discharge anytime
    if is_battery:
        return round(capacity_mwh * random.uniform(0.05, 0.35), 3)

    alt_deg = solar_altitude(lat, lng, utc_hour, day_of_year)

    if alt_deg <= 0:
        return 0.0

    # Real DNI from Open-Meteo (W/m², 0-1000 typical range)
    weather = get_weather(lat, lng)
    dni = weather.get("dni", 0.0)

    if dni <= 0 and alt_deg <= 2:
        return 0.0

    # Normalize DNI to 0-1 (1000 W/m² = clear sky peak)
    irradiance = min(dni / 1000.0, 1.0)

    # Fallback to sin(altitude) if DNI is 0 but sun is up
    if irradiance < 0.01 and alt_deg > 5:
        irradiance = math.sin(math.radians(alt_deg))
        cloud = cloud_factor(weather["cloud_cover"])
        irradiance *= cloud

    efficiency = 0.85 if alt_deg > 15 else 0.65
    # DNI already includes atmospheric conditions — no cloud double-dip
    mwh = capacity_mwh * irradiance * efficiency * random.uniform(0.2, 0.4)
    return round(max(0.01, mwh), 3)


# ── Sellers & Buyers ────────────────────────────────────────
SELLERS = [
    {"id": "coin-base-1", "district": "McHenry_D63", "type": "commercial",  "label": "Walmart Woodstock",    "capacity_mwh": 4.2,  "lat": 42.31, "lng": -88.44, "is_battery": False},
    {"id": "coin-base-2", "district": "McHenry_D63", "type": "commercial",  "label": "NW Medicine",          "capacity_mwh": 1.9,  "lat": 42.25, "lng": -88.60, "is_battery": False},
    {"id": "coin-base-3", "district": "McHenry_D63", "type": "commercial",  "label": "Jewel-Osco",           "capacity_mwh": 0.16, "lat": 42.32, "lng": -88.45, "is_battery": False},
    {"id": "coin-base-4", "district": "McHenry_D63", "type": "commercial",  "label": "Walmart Huntley",      "capacity_mwh": 3.3,  "lat": 42.23, "lng": -88.43, "is_battery": False},
    {"id": "coin-base-5", "district": "McHenry_D63", "type": "residential", "label": "Woodstock Homes",      "capacity_mwh": 0.8,  "lat": 42.31, "lng": -88.45, "is_battery": False},
    {"id": "coin-base-6", "district": "McHenry_D63", "type": "municipal",   "label": "Marengo Municipal",    "capacity_mwh": 1.2,  "lat": 42.25, "lng": -88.61, "is_battery": False},
    {"id": "farm-marengo-solar", "district": "McHenry_D63", "type": "solar_farm", "label": "Marengo Solar Farm", "capacity_mwh": 6.0, "lat": 42.25, "lng": -88.62, "is_battery": False},
    {"id": "farm-nexamp-harvard", "district": "McHenry_D63", "type": "solar_farm", "label": "Nexamp Harvard",   "capacity_mwh": 3.0, "lat": 42.42, "lng": -88.61, "is_battery": False},
    {"id": "farm-hebron", "district": "McHenry_D63", "type": "solar_farm", "label": "Hebron Solar",            "capacity_mwh": 2.5, "lat": 42.47, "lng": -88.43, "is_battery": False},
    {"id": "batt-marengo", "district": "McHenry_D63", "type": "battery", "label": "Marengo Battery 20MW",      "capacity_mwh": 20.0, "lat": 42.24, "lng": -88.60, "is_battery": True},
    {"id": "batt-mchenry", "district": "McHenry_D63", "type": "battery", "label": "McHenry Battery 20MW",      "capacity_mwh": 20.0, "lat": 42.33, "lng": -88.27, "is_battery": True},
]

BUYERS = [
    {"id": "buyer-neighbor-1", "type": "neighbor",    "label": "Residential Block A",  "max_bid": 0.18},
    {"id": "buyer-neighbor-2", "type": "neighbor",    "label": "Residential Block B",  "max_bid": 0.16},
    {"id": "buyer-school-1",   "type": "school",      "label": "Woodstock North HS",   "max_bid": 0.15},
    {"id": "buyer-school-2",   "type": "school",      "label": "Marengo High School",  "max_bid": 0.14},
    {"id": "buyer-biz-1",      "type": "business",    "label": "Route 47 Strip Mall",  "max_bid": 0.20},
    {"id": "buyer-biz-2",      "type": "business",    "label": "NW Medicine Ops",       "max_bid": 0.22},
    {"id": "buyer-dc-1",       "type": "datacenter",  "label": "Google Aurora Hub",     "max_bid": 0.25},
    {"id": "buyer-dc-2",       "type": "datacenter",  "label": "Equinix Chicago",       "max_bid": 0.23},
    {"id": "buyer-grid-1",     "type": "grid",        "label": "ComEd Buyback",          "max_bid": 0.08},
    {"id": "buyer-muni-1",     "type": "municipal",   "label": "Harvard Fire Dept",      "max_bid": 0.14},
    {"id": "buyer-muni-2",     "type": "municipal",   "label": "Woodstock PD",           "max_bid": 0.15},
]

# ── Market Parameters ───────────────────────────────────────
COMED_TOLL = 0.02
CO2_TONS_PER_MWH = 0.42   # EPA eGRID 2022
ISLAND_THRESHOLD = 0.30

trade_count = 0
rejected_count = 0
total_profit = 0.0
total_mwh_traded = 0.0
island_events = 0


def run_trade():
    global trade_count, rejected_count, total_profit, total_mwh_traded, island_events

    grid_price = get_grid_price()
    islanding = grid_price >= ISLAND_THRESHOLD
    if islanding:
        island_events += 1

    seller = random.choice(SELLERS)
    mwh = solar_output(
        seller["capacity_mwh"],
        seller.get("lat", D63_LAT),
        seller.get("lng", D63_LNG),
        seller.get("is_battery", False),
    )
    if mwh <= 0:
        return

    buyer = random.choice(BUYERS)
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

    with GRID_PRICE_LOCK:
        price_source = GRID_PRICE_CACHE.get("source", "simulated")
        lmp_mwh = GRID_PRICE_CACHE.get("lmp_mwh", 0)

    weather = get_weather(seller.get("lat", D63_LAT), seller.get("lng", D63_LNG))

    data = {
        "station_id": seller["id"],
        "district": seller["district"],
        "seller_type": seller["type"],
        "seller_label": seller["label"],
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
        "data_mode": "live" if price_source == "PJM_LMP" else "sim",
        "weather_source": weather["source"],
        "cloud_cover": weather["cloud_cover"],
        "temperature": weather["temperature"],
        "dni": weather.get("dni", 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "co2_tons": round(mwh * CO2_TONS_PER_MWH, 4),
    }

    msg = json.dumps(data).encode("utf-8")
    future = publisher.publish(topic_path, msg)

    src = "🛰️" if price_source == "PJM_LMP" else "📊"
    icon = "🏝️" if islanding else "⚡" if status != "REJECTED" else "❌"
    print(f"  {icon}{src} {seller['label']:24} -> {buyer['label']:20} | {mwh:6.3f} MWh | Grid: ${grid_price:.4f} | Settled: ${settled:.4f} | ${profit:+.4f} | {status}")

    total = trade_count + rejected_count
    if total > 0 and total % 15 == 0:
        rate = trade_count / total * 100
        with GRID_PRICE_LOCK:
            src_info = GRID_PRICE_CACHE.get("source", "?")
            lmp_info = GRID_PRICE_CACHE.get("lmp_mwh", 0)
        print()
        print(f"  ╔══════════════════════════════════════════════════════════════╗")
        print(f"  ║  D63 LIVE SCOREBOARD — Trade #{total:,}                          ║")
        print(f"  ╠══════════════════════════════════════════════════════════════╣")
        print(f"  ║  Settled: {trade_count:>6}  |  Rejected: {rejected_count:>6}  |  Rate: {rate:>5.1f}%  ║")
        print(f"  ║  MWh traded:  {total_mwh_traded:>9.2f}  |  Profit: ${total_profit:>10.2f}    ║")
        print(f"  ║  Island events: {island_events:>5}                                  ║")
        print(f"  ║  DATA: {src_info:>10}  |  PJM LMP: ${lmp_info:>8.2f}/MWh          ║")
        print(f"  ╚══════════════════════════════════════════════════════════════╝")
        print()


# ── Banner ──────────────────────────────────────────────────
print()
print("  ╔══════════════════════════════════════════════════════════════╗")
print("  ║   TINY-HUB-NETWORK — D63 McHenry County (LIVE DATA)        ║")
print("  ║   ComEd Territory · PJM Interconnection                     ║")
print("  ╠══════════════════════════════════════════════════════════════╣")
print(f"  ║  Sellers: {len(SELLERS):>2}  |  Buyers: {len(BUYERS):>2}                            ║")
print(f"  ║  Grid price:  {'PJM Real-Time LMP' if USE_GRIDSTATUS else 'Simulation':>25}     ║")
print(f"  ║  Solar output: {'Irradiance Model':>25}     ║")
print(f"  ║  ComEd toll: ${COMED_TOLL}/MWh                                  ║")
print(f"  ║  Island threshold: ${ISLAND_THRESHOLD}/MWh                         ║")
print(f"  ║  Pub/Sub topic: {TOPIC_ID:>20}                    ║")
print("  ╚══════════════════════════════════════════════════════════════╝")
print()

# Start grid price refresh
if USE_GRIDSTATUS:
    threading.Thread(target=refresh_grid_price_loop, daemon=True).start()
    p = fetch_pjm_lmp()
    if p:
        print(f"  [Grid] Initial PJM LMP: ${GRID_PRICE_CACHE['lmp_mwh']:.2f}/MWh (${p:.4f}/kWh)")
    else:
        print("  [Grid] Initial PJM fetch failed — using simulation until next refresh")
    print()

# Initial weather check
print_weather_status(D63_LAT, D63_LNG, "D63 Weather")

# ── Main Loop ───────────────────────────────────────────────
while True:
    try:
        run_trade()
        time.sleep(random.uniform(3, 8))
    except KeyboardInterrupt:
        total = trade_count + rejected_count
        rate = (trade_count / total * 100) if total > 0 else 0
        print()
        print("  ╔══════════════════════════════════════════════════════════════╗")
        print("  ║                  D63 LIVE FINAL REPORT                      ║")
        print("  ╠══════════════════════════════════════════════════════════════╣")
        print(f"  ║  Trades settled:    {trade_count:>6}                                ║")
        print(f"  ║  Trades rejected:   {rejected_count:>6}                                ║")
        print(f"  ║  Settlement rate:   {rate:>6.1f}%                               ║")
        print(f"  ║  Total MWh traded:  {total_mwh_traded:>9.2f}                           ║")
        print(f"  ║  Community profit:  ${total_profit:>10.2f}                          ║")
        print(f"  ║  Island events:     {island_events:>6}                                ║")
        print("  ╚══════════════════════════════════════════════════════════════╝")
        break
    except Exception as e:
        print(f"  Error: {e}")
        time.sleep(5)
