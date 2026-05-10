#!/usr/bin/env python3
"""
TINY-HUB — Wire matching_engine.py into d91_marketplace_live.py
Run from project root: python3 add_order_matching.py
"""

from pathlib import Path

TARGET = Path("d91_marketplace_live.py")

if not TARGET.exists():
    print(f"  ❌ {TARGET} not found. Run from your project root.")
    exit(1)

source = TARGET.read_text(encoding="utf-8")

# ── Patch 1: Add import ─────────────────────────────────────
OLD_IMPORT = "from weather_feed import get_weather, cloud_factor, print_weather_status"
NEW_IMPORT = "from weather_feed import get_weather, cloud_factor, print_weather_status\nfrom matching_engine import MatchingEngine"

if OLD_IMPORT not in source:
    print("  ❌ Patch 1 failed — import line not found.")
    exit(1)

source = source.replace(OLD_IMPORT, NEW_IMPORT, 1)
print("  ✅ Patch 1: import added")

# ── Patch 2: Add engine init after AMEREN_TOLL ──────────────
OLD_TOLL = "AMEREN_TOLL = 0.025"
NEW_TOLL = """AMEREN_TOLL = 0.025

# ── Deterministic order matching engine ─────────────────────
_engine = MatchingEngine(toll=AMEREN_TOLL, mode="pro_rata")"""

if OLD_TOLL not in source:
    print("  ❌ Patch 2 failed — AMEREN_TOLL not found.")
    exit(1)

source = source.replace(OLD_TOLL, NEW_TOLL, 1)
print("  ✅ Patch 2: engine initialised")

# ── Patch 3: Replace matching block using line numbers ───────
lines = source.splitlines(keepends=True)

start_line = None
end_line = None

for i, line in enumerate(lines):
    if "seller = random.choice(SELLERS)" in line and start_line is None:
        start_line = i
    if start_line is not None and "profit = 0.0" in line:
        prev = lines[i-1].strip()
        if "rejected_count" in prev or "settled = 0.0" in prev:
            end_line = i
            break

if start_line is None or end_line is None:
    print(f"  ❌ Patch 3 failed — could not locate block (start={start_line}, end={end_line})")
    exit(1)

print(f"  Found matching block: lines {start_line+1}–{end_line+1}")

NEW_MATCH = """    # ── Deterministic order matching ───────────────────────
    for seller in SELLERS:
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
"""

new_lines = lines[:start_line] + [NEW_MATCH] + lines[end_line+1:]
source = "".join(new_lines)
print("  ✅ Patch 3: run_trade() replaced with deterministic order matching")

TARGET.write_text(source, encoding="utf-8")
print()
print("  ✅ d91_marketplace_live.py patched successfully.")
print("     Restart the marketplace to apply.")
print()
