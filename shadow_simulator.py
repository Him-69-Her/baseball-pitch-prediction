#!/usr/bin/env python3
"""
TINY-HUB — D91 Shadow Market Simulator
=======================================
Generates realistic peer-to-peer energy trades using:
  - Real D91 building data (1,289 sellers + 500 buyers with lat/lng + solar capacity)
  - Real-time solar irradiance from Open-Meteo (DNI/GHI for Peoria area)
  - MISO LMP-aware pricing via PricingAgent
  - Proximity-first matching via MatchingEngine

Publishes settled trades to d91-trades Pub/Sub topic every 5 minutes.
Runs as a long-lived process (Cloud Run background worker or local).

Usage:
    python3 shadow_simulator.py              # run continuously (5-min ticks)
    python3 shadow_simulator.py --once       # run a single tick and exit
"""

import json
import math
import os
import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import pubsub_v1

# ── Config ──────────────────────────────────────────────────
DATA_PROJECT = os.environ.get("PUBSUB_PROJECT", "tinyhub-data-dev")
TOPIC_NAME = os.environ.get("PUBSUB_TOPIC", "d91-trades")
TICK_SECONDS = int(os.environ.get("TICK_SECONDS", "300"))  # 5 minutes
BUILDINGS_FILE = os.environ.get("BUILDINGS_FILE", "district91_buildings.json")
DEMO_MODE = "--demo" in sys.argv

# Solar constants
PEAK_DNI = 1000.0        # W/m2 at perfect conditions
PANEL_AREA_SQFT = 17.5   # avg panel ~17.5 sqft
PANEL_WATTS = 400         # 400W per panel
PANEL_EFFICIENCY = 0.20   # 20% efficiency
SQFT_TO_M2 = 0.0929

# Grid tolls (Ameren D91)
AMEREN_TOLL = 0.025       # $/kWh wheeling fee
SUPPLY_RATE = 0.070       # $/kWh baseline supply rate
LINE_LOSS_LOCAL = 0.05    # 5% local distribution loss
CO2_FACTOR = 0.42         # tons CO2 per MWh (IL grid average)
LCOS_DEGRADATION = 15.0   # $/MWh battery degradation cost


def load_buildings(path: str) -> tuple:
    """Load sellers and buyers from the D91 digital twin JSON."""
    with open(path) as f:
        data = json.load(f)
    sellers = [s for s in data.get("sellers", []) if s.get("solar", {}).get("panels", 0) > 0]
    buyers = data.get("commercial_buyers", [])
    print(f"  Loaded {len(sellers)} sellers, {len(buyers)} buyers from {path}")
    return sellers, buyers


def get_current_dni() -> float:
    """Fetch real-time DNI from Open-Meteo for Peoria, IL area. In demo mode, simulates daytime."""
    if DEMO_MODE:
        # Simulate a sunny afternoon for demo purposes
        simulated = random.uniform(550, 850)
        print(f"  Weather (DEMO): DNI={simulated:.0f} W/m2 (simulated daytime)")
        return simulated

    try:
        import urllib.request
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            "latitude=40.65&longitude=-89.50"
            "&current=direct_normal_irradiance,cloud_cover,temperature_2m"
            "&timezone=America/Chicago"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "TinyHub/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        current = data.get("current", {})
        dni = current.get("direct_normal_irradiance", 0.0)
        cloud = current.get("cloud_cover", 50)
        temp = current.get("temperature_2m", 20.0)
        print(f"  Weather: DNI={dni:.0f} W/m2, Cloud={cloud}%, Temp={temp:.1f}C")
        return max(dni, 0.0)
    except Exception as e:
        print(f"  Weather API error: {e}, using simulated DNI")
        # Simulate based on time of day
        hour = datetime.now(timezone.utc).hour - 6  # rough CST
        if hour < 6 or hour > 20:
            return 0.0
        # Bell curve peaking at noon
        solar_noon = 13
        spread = 4
        return max(0, PEAK_DNI * 0.7 * math.exp(-0.5 * ((hour - solar_noon) / spread) ** 2))


def calc_solar_output_mwh(seller: dict, dni: float) -> float:
    """Calculate current solar output for a building based on DNI."""
    solar = seller.get("solar", {})
    panels = solar.get("panels", 0)
    if panels == 0 or dni <= 0:
        return 0.0

    # Scale output by current DNI vs peak
    irradiance_factor = min(dni / PEAK_DNI, 1.0)

    # kW capacity = panels * panel_watts / 1000
    capacity_kw = panels * PANEL_WATTS / 1000.0

    # Current output in kW (scaled by irradiance)
    current_kw = capacity_kw * irradiance_factor * PANEL_EFFICIENCY

    # Convert to MWh for 5-minute interval
    mwh = current_kw * (TICK_SECONDS / 3600.0) / 1000.0

    # Add small random variance (+/- 8%) for realism
    mwh *= random.uniform(0.92, 1.08)

    return round(mwh, 6)


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Distance between two points in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def run_tick(sellers, buyers, publisher, topic_path) -> int:
    """Run one matching tick. Returns number of trades published."""
    dni = get_current_dni()

    if dni < 10:
        print("  DNI too low (nighttime/overcast), no trades this tick")
        return 0

    # Calculate solar output for each seller
    active_sellers = []
    for s in sellers:
        mwh = calc_solar_output_mwh(s, dni)
        if mwh > 0.0001:  # min threshold
            active_sellers.append({
                "id": s["osm_id"],
                "label": s.get("label", ""),
                "town": s.get("town", ""),
                "lat": s["lat"],
                "lng": s["lng"],
                "mwh": mwh,
                "panels": s.get("solar", {}).get("panels", 0),
            })

    if not active_sellers:
        print("  No active sellers this tick")
        return 0

    # Randomly select buyers with demand this tick (simulate consumption patterns)
    # More buyers active during day, fewer at night
    hour = datetime.now(timezone.utc).hour - 6  # rough CST
    demand_factor = 0.3 + 0.5 * math.sin(max(0, min(1, (hour - 6) / 12)) * math.pi)
    active_buyer_count = max(5, int(len(buyers) * demand_factor * random.uniform(0.6, 1.0)))
    active_buyers = random.sample(buyers, min(active_buyer_count, len(buyers)))

    # Proximity matching: for each buyer, find nearest seller with capacity
    trades = []
    seller_remaining = {s["id"]: s["mwh"] for s in active_sellers}
    seller_lookup = {s["id"]: s for s in active_sellers}

    random.shuffle(active_buyers)

    for buyer in active_buyers:
        blat = buyer.get("lat", 0)
        blng = buyer.get("lng", 0)
        if blat == 0 or blng == 0:
            continue

        # Demand: random fraction of their solar capacity equivalent
        buyer_solar = buyer.get("solar", {})
        buyer_demand_mwh = random.uniform(0.001, 0.05)  # 1-50 kWh per 5-min tick

        # Find nearest seller with remaining capacity
        best_seller = None
        best_dist = float("inf")
        for sid, remaining in seller_remaining.items():
            if remaining < 0.0001:
                continue
            s = seller_lookup[sid]
            dist = haversine_km(blat, blng, s["lat"], s["lng"])
            if dist < best_dist:
                best_dist = dist
                best_seller = sid

        if best_seller is None or best_dist > 50:  # max 50km
            continue

        s = seller_lookup[best_seller]
        trade_mwh = min(buyer_demand_mwh, seller_remaining[best_seller])
        seller_remaining[best_seller] -= trade_mwh

        # Pricing
        distance_km = round(best_dist, 2)
        line_loss = LINE_LOSS_LOCAL * (distance_km / 5.0)  # scale loss by distance
        line_loss = min(line_loss, 0.15)  # cap at 15%
        effective_mwh = trade_mwh * (1 - line_loss)

        # Price: supply rate +/- spread based on distance
        proximity_discount = max(0, 0.02 * (1 - distance_km / 50))  # closer = cheaper
        trade_price = SUPPLY_RATE - proximity_discount + random.uniform(-0.005, 0.005)
        trade_price = max(0.04, min(trade_price, 0.10))  # clamp

        gross_revenue = effective_mwh * trade_price * 1000  # $/MWh to $/kWh conversion
        toll_cost = effective_mwh * AMEREN_TOLL * 1000
        net_profit = gross_revenue - toll_cost

        co2_saved = effective_mwh * CO2_FACTOR

        trade = {
            "trade_id": f"SIM-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "district": "D91",
            "seller_id": str(s["id"]),
            "seller_label": s["label"],
            "seller_town": s["town"],
            "seller_lat": s["lat"],
            "seller_lng": s["lng"],
            "buyer_id": str(buyer.get("osm_id", "")),
            "buyer_label": buyer.get("label", ""),
            "buyer_town": buyer.get("town", ""),
            "buyer_lat": blat,
            "buyer_lng": blng,
            "mwh": round(trade_mwh, 6),
            "effective_mwh": round(effective_mwh, 6),
            "distance_km": distance_km,
            "line_loss_pct": round(line_loss * 100, 2),
            "price_per_kwh": round(trade_price, 4),
            "gross_revenue": round(gross_revenue, 4),
            "toll_cost": round(toll_cost, 4),
            "net_profit": round(net_profit, 4),
            "grid_price": round(SUPPLY_RATE + AMEREN_TOLL, 4),
            "settled_price": round(trade_price, 4),
            "co2_tons": round(co2_saved, 6),
            "trade_status": "SETTLED",
            "settlement": "OPTIMISTIC",
            "matching_mode": "proximity-first",
            "dni_wm2": round(dni, 1),
            "source": "shadow_simulator",
        }
        trades.append(trade)

    # Publish trades
    published = 0
    for trade in trades:
        try:
            data = json.dumps(trade).encode("utf-8")
            future = publisher.publish(topic_path, data)
            future.result(timeout=10)
            published += 1
        except Exception as e:
            print(f"  Publish error: {e}")

    total_mwh = sum(t["mwh"] for t in trades)
    total_profit = sum(t["net_profit"] for t in trades)
    total_co2 = sum(t["co2_tons"] for t in trades)
    print(f"  Tick complete: {published} trades | {total_mwh:.4f} MWh | ${total_profit:.2f} profit | {total_co2:.4f}t CO2")

    return published


def main():
    print("=" * 60)
    print("  TINY-HUB D91 SHADOW MARKET SIMULATOR")
    print(f"  Project: {DATA_PROJECT}")
    print(f"  Topic: {TOPIC_NAME}")
    print(f"  Tick interval: {TICK_SECONDS}s")
    print("=" * 60)

    once = "--once" in sys.argv

    # Load buildings
    sellers, buyers = load_buildings(BUILDINGS_FILE)

    # Init Pub/Sub publisher
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(DATA_PROJECT, TOPIC_NAME)

    # Verify topic exists
    try:
        publisher.get_topic(request={"topic": topic_path})
        print(f"  Topic verified: {topic_path}")
    except Exception as e:
        print(f"  ERROR: Cannot access topic {topic_path}: {e}")
        sys.exit(1)

    if once:
        print("\n  Running single tick...")
        run_tick(sellers, buyers, publisher, topic_path)
        print("  Done.")
        return

    # Continuous mode
    print(f"\n  Starting continuous simulation (every {TICK_SECONDS}s)...")
    tick_count = 0
    while True:
        tick_count += 1
        print(f"\n--- Tick #{tick_count} @ {datetime.now(timezone.utc).isoformat()}Z ---")
        try:
            run_tick(sellers, buyers, publisher, topic_path)
        except Exception as e:
            print(f"  Tick error: {e}")
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
