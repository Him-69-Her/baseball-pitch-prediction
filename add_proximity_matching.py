#!/usr/bin/env python3
"""
TINY-HUB — Add proximity-first matching mode to matching_engine.py

Sellers are grouped into distance tiers from each buyer:
  Tier 0: < 5 km   (same neighborhood)
  Tier 1: < 15 km  (same town / adjacent)
  Tier 2: < 50 km  (same county)
  Tier 3: 50+ km   (district-wide)

Surplus is allocated tier-by-tier (closest first).
Within each tier, surplus is split pro-rata by seller MWh capacity.
Falls through to the next tier only if demand remains unfilled.

Minimizes transmission loss and keeps energy local.

Run from project root:
    python3 add_proximity_matching.py
"""

from pathlib import Path

TARGET = Path("matching_engine.py")

if not TARGET.exists():
    print(f"  ❌ {TARGET} not found. Run from your project root.")
    exit(1)

source = TARGET.read_text(encoding="utf-8")

# ── Patch 1: Add PROXIMITY_TIERS constant after LINE_LOSS_PCT ──
ANCHOR = "LINE_LOSS_PCT = 0.05"

INSERTION = """

# Distance tiers for proximity-first matching (km)
# Closest sellers fill demand first; pro-rata within each tier.
PROXIMITY_TIERS = [5.0, 15.0, 50.0, float('inf')]
PROXIMITY_TIER_LABELS = ["<5km", "<15km", "<50km", "50km+"]"""

if ANCHOR not in source:
    print("  ❌ Patch 1 failed — LINE_LOSS_PCT not found.")
    exit(1)

source = source.replace(ANCHOR, ANCHOR + INSERTION, 1)
print("  ✅ Patch 1: PROXIMITY_TIERS constant added")


# ── Patch 2: Update __init__ docstring to include "proximity" mode ──
OLD_DOC = '''            mode:             "pro_rata" or "price_priority"'''
NEW_DOC = '''            mode:             "pro_rata", "price_priority", or "proximity"'''

if OLD_DOC not in source:
    print("  ⚠️  Patch 2: docstring not found — skipping (non-critical)")
else:
    source = source.replace(OLD_DOC, NEW_DOC, 1)
    print("  ✅ Patch 2: __init__ docstring updated with 'proximity' mode")


# ── Patch 3: Update match() dispatch to include proximity ──
OLD_DISPATCH = """    def match(self, grid_price: float = 0.0) -> list[MatchedTrade]:
        if self.mode == "pro_rata":
            trades = self._match_pro_rata(grid_price)
        else:
            trades = self._match_price_priority(grid_price)"""

NEW_DISPATCH = """    def match(self, grid_price: float = 0.0) -> list[MatchedTrade]:
        if self.mode == "proximity":
            trades = self._match_proximity(grid_price)
        elif self.mode == "pro_rata":
            trades = self._match_pro_rata(grid_price)
        else:
            trades = self._match_price_priority(grid_price)"""

if OLD_DISPATCH not in source:
    print("  ❌ Patch 3 failed — match() dispatch not found.")
    exit(1)

source = source.replace(OLD_DISPATCH, NEW_DISPATCH, 1)
print("  ✅ Patch 3: match() dispatch updated with proximity branch")


# ── Patch 4: Add _match_proximity() method before _match_price_priority() ──
OLD_PRICE_PRIORITY = """    def _match_price_priority(self, grid_price: float) -> list[MatchedTrade]:"""

NEW_PROXIMITY_METHOD = """    def _match_proximity(self, grid_price: float) -> list[MatchedTrade]:
        \"\"\"
        Proximity-first: group sellers by distance tier from each buyer,
        fill closest tier first, pro-rata within each tier.

        Tier boundaries (km): """ + str([5.0, 15.0, 50.0]) + """ + [inf]
        Sellers without lat/lng go into the last tier.
        Buyers without lat/lng fall back to pro_rata matching.
        \"\"\"
        buyers  = sorted(self._buy_orders,  key=lambda b: b.bid_price, reverse=True)
        sellers = list(self._sell_orders)  # mutable copy for remaining_mwh tracking

        trades: list[MatchedTrade] = []

        for b in buyers:
            if b.remaining_mwh < 1e-4:
                continue

            # If buyer has no location, fall back to pro-rata across all qualifying sellers
            if b.lat is None or b.lng is None:
                qualifying = [s for s in sellers if s.ask_price <= b.bid_price and s.remaining_mwh > 1e-4]
                trades += self._pro_rata_fill(b, qualifying, grid_price)
                continue

            # Group qualifying sellers into distance tiers
            tiers: list[list] = [[] for _ in PROXIMITY_TIERS]

            for s in sellers:
                if s.ask_price > b.bid_price or s.remaining_mwh < 1e-4:
                    continue

                if s.lat is None or s.lng is None:
                    tiers[-1].append((s, None))  # no location → last tier
                    continue

                dist = _haversine_km(s.lat, s.lng, b.lat, b.lng)
                placed = False
                for ti, threshold in enumerate(PROXIMITY_TIERS):
                    if dist < threshold:
                        tiers[ti].append((s, dist))
                        placed = True
                        break
                if not placed:
                    tiers[-1].append((s, dist))

            # Fill tier by tier, closest first
            for ti, tier_sellers in enumerate(tiers):
                if b.remaining_mwh < 1e-4:
                    break
                if not tier_sellers:
                    continue

                # Within tier: pro-rata by available MWh
                total_avail = sum(s.remaining_mwh for s, _ in tier_sellers)
                demand = b.remaining_mwh

                for s, dist in tier_sellers:
                    if b.remaining_mwh < 1e-4:
                        break

                    share = s.remaining_mwh / total_avail
                    generated_mwh = round(min(share * demand, s.remaining_mwh), 4)
                    if generated_mwh < 1e-4:
                        continue

                    delivered_mwh = round(generated_mwh * (1 - LINE_LOSS_PCT), 4)
                    settled = round((s.ask_price + b.bid_price) / 2, 4)
                    profit  = round((settled - self.toll) * generated_mwh, 4)

                    tier_label = PROXIMITY_TIER_LABELS[ti] if ti < len(PROXIMITY_TIER_LABELS) else "far"

                    trades.append(MatchedTrade(
                        seller_id=s.station_id, seller_label=s.label,
                        seller_town=s.town, seller_type=s.seller_type,
                        buyer_id=b.buyer_id, buyer_label=b.label,
                        buyer_town=b.town, buyer_type=b.buyer_type,
                        mwh=delivered_mwh, ask_price=s.ask_price,
                        bid_price=b.bid_price, settled_price=settled,
                        net_profit=profit, grid_price=grid_price,
                        match_type=f"proximity_{tier_label}",
                        distance_km=round(dist, 2) if dist is not None else None,
                    ))

                    s.remaining_mwh -= generated_mwh
                    b.remaining_mwh -= delivered_mwh

        return trades

    def _pro_rata_fill(self, buyer: BuyOrder, sellers: list,
                       grid_price: float) -> list[MatchedTrade]:
        \"\"\"Helper: pro-rata fill a single buyer from a list of sellers.\"\"\"
        if not sellers or buyer.remaining_mwh < 1e-4:
            return []

        total_avail = sum(s.remaining_mwh for s in sellers)
        if total_avail < 1e-4:
            return []

        demand = buyer.remaining_mwh
        trades: list[MatchedTrade] = []

        for s in sellers:
            if buyer.remaining_mwh < 1e-4:
                break

            share = s.remaining_mwh / total_avail
            generated_mwh = round(min(share * demand, s.remaining_mwh), 4)
            if generated_mwh < 1e-4:
                continue

            delivered_mwh = round(generated_mwh * (1 - LINE_LOSS_PCT), 4)
            settled = round((s.ask_price + buyer.bid_price) / 2, 4)
            profit  = round((settled - self.toll) * generated_mwh, 4)
            dist    = self._distance(s, buyer)

            trades.append(MatchedTrade(
                seller_id=s.station_id, seller_label=s.label,
                seller_town=s.town, seller_type=s.seller_type,
                buyer_id=buyer.buyer_id, buyer_label=buyer.label,
                buyer_town=buyer.town, buyer_type=buyer.buyer_type,
                mwh=delivered_mwh, ask_price=s.ask_price,
                bid_price=buyer.bid_price, settled_price=settled,
                net_profit=profit, grid_price=grid_price,
                match_type="pro_rata", distance_km=dist,
            ))

            s.remaining_mwh -= generated_mwh
            buyer.remaining_mwh -= delivered_mwh

        return trades

    """ + OLD_PRICE_PRIORITY

if OLD_PRICE_PRIORITY not in source:
    print("  ❌ Patch 4 failed — _match_price_priority() not found.")
    exit(1)

source = source.replace(OLD_PRICE_PRIORITY, NEW_PROXIMITY_METHOD, 1)
print("  ✅ Patch 4: _match_proximity() method added")


# ── Write ────────────────────────────────────────────────────
TARGET.write_text(source, encoding="utf-8")
print()
print("  ✅ matching_engine.py patched with proximity-first mode.")
print()
print("  Usage:")
print("    _engine = MatchingEngine(toll=AMEREN_TOLL, mode='proximity')")
print()
print("  Distance tiers: <5km → <15km → <50km → 50km+")
print("  Within each tier: pro-rata by seller MWh capacity")
print("  match_type field: 'proximity_<5km', 'proximity_<15km', etc.")
print()
