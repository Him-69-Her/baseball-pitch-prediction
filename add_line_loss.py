#!/usr/bin/env python3
"""
TINY-HUB — Add I²R line loss to matching_engine.py
Run from project root: python3 add_line_loss.py
"""

from pathlib import Path

TARGET = Path("matching_engine.py")
if not TARGET.exists():
    print(f"  ❌ {TARGET} not found.")
    exit(1)

source = TARGET.read_text(encoding="utf-8")

# ── Patch 1: Add LINE_LOSS_PCT constant ─────────────────────
ANCHOR = 'AMEREN_SELLER_TOWN  = "District-wide"'
INSERTION = '\n\n# Local I²R distribution line loss (~5% typical for low-voltage networks)\n# Buyer pays for delivered MWh; seller earns on generated MWh.\nLINE_LOSS_PCT = 0.05'

if ANCHOR not in source:
    print("  ❌ Patch 1 failed — AMEREN_SELLER_TOWN not found.")
    exit(1)

source = source.replace(ANCHOR, ANCHOR + INSERTION, 1)
print("  ✅ Patch 1: LINE_LOSS_PCT = 0.05 added")

# ── Patch 2: price_priority — use delivered_mwh for buyer ───
OLD2 = "            fill_mwh = min(s.remaining_mwh, b.remaining_mwh)\n            settled  = round((s.ask_price + b.bid_price) / 2, 4)\n            profit   = round((settled - self.toll) * fill_mwh, 4)\n            dist     = self._distance(s, b)\n\n            trades.append(MatchedTrade(\n                seller_id=s.station_id, seller_label=s.label,\n                seller_town=s.town, seller_type=s.seller_type,\n                buyer_id=b.buyer_id, buyer_label=b.label,\n                buyer_town=b.town, buyer_type=b.buyer_type,\n                mwh=fill_mwh, ask_price=s.ask_price,\n                bid_price=b.bid_price, settled_price=settled,\n                net_profit=profit, grid_price=grid_price,\n                match_type=\"price_priority\", distance_km=dist,\n            ))\n\n            s.remaining_mwh -= fill_mwh\n            b.remaining_mwh -= fill_mwh"

NEW2 = "            generated_mwh = min(s.remaining_mwh, b.remaining_mwh)\n            delivered_mwh = round(generated_mwh * (1 - LINE_LOSS_PCT), 4)\n            settled  = round((s.ask_price + b.bid_price) / 2, 4)\n            profit   = round((settled - self.toll) * generated_mwh, 4)\n            dist     = self._distance(s, b)\n\n            trades.append(MatchedTrade(\n                seller_id=s.station_id, seller_label=s.label,\n                seller_town=s.town, seller_type=s.seller_type,\n                buyer_id=b.buyer_id, buyer_label=b.label,\n                buyer_town=b.town, buyer_type=b.buyer_type,\n                mwh=delivered_mwh, ask_price=s.ask_price,\n                bid_price=b.bid_price, settled_price=settled,\n                net_profit=profit, grid_price=grid_price,\n                match_type=\"price_priority\", distance_km=dist,\n            ))\n\n            s.remaining_mwh -= generated_mwh\n            b.remaining_mwh -= delivered_mwh"

if OLD2 not in source:
    print("  ❌ Patch 2 failed — price_priority fill block not found.")
    exit(1)

source = source.replace(OLD2, NEW2, 1)
print("  ✅ Patch 2: I²R loss applied in price_priority")

# ── Patch 3: pro_rata — use delivered_mwh for buyer ─────────
OLD3 = "                fill_mwh = round(min(share * demand, s.remaining_mwh), 4)\n                if fill_mwh < 1e-4:\n                    continue\n\n                settled = round((s.ask_price + b.bid_price) / 2, 4)\n                profit  = round((settled - self.toll) * fill_mwh, 4)\n                dist    = self._distance(s, b)\n\n                trades.append(MatchedTrade(\n                    seller_id=s.station_id, seller_label=s.label,\n                    seller_town=s.town, seller_type=s.seller_type,\n                    buyer_id=b.buyer_id, buyer_label=b.label,\n                    buyer_town=b.town, buyer_type=b.buyer_type,\n                    mwh=fill_mwh, ask_price=s.ask_price,\n                    bid_price=b.bid_price, settled_price=settled,\n                    net_profit=profit, grid_price=grid_price,\n                    match_type=\"pro_rata\", distance_km=dist,\n                ))\n\n                s.remaining_mwh -= fill_mwh\n                b.remaining_mwh -= fill_mwh"

NEW3 = "                generated_mwh = round(min(share * demand, s.remaining_mwh), 4)\n                if generated_mwh < 1e-4:\n                    continue\n\n                delivered_mwh = round(generated_mwh * (1 - LINE_LOSS_PCT), 4)\n                settled = round((s.ask_price + b.bid_price) / 2, 4)\n                profit  = round((settled - self.toll) * generated_mwh, 4)\n                dist    = self._distance(s, b)\n\n                trades.append(MatchedTrade(\n                    seller_id=s.station_id, seller_label=s.label,\n                    seller_town=s.town, seller_type=s.seller_type,\n                    buyer_id=b.buyer_id, buyer_label=b.label,\n                    buyer_town=b.town, buyer_type=b.buyer_type,\n                    mwh=delivered_mwh, ask_price=s.ask_price,\n                    bid_price=b.bid_price, settled_price=settled,\n                    net_profit=profit, grid_price=grid_price,\n                    match_type=\"pro_rata\", distance_km=dist,\n                ))\n\n                s.remaining_mwh -= generated_mwh\n                b.remaining_mwh -= delivered_mwh"

if OLD3 not in source:
    print("  ❌ Patch 3 failed — pro_rata fill block not found.")
    exit(1)

source = source.replace(OLD3, NEW3, 1)
print("  ✅ Patch 3: I²R loss applied in pro_rata")

TARGET.write_text(source, encoding="utf-8")
print()
print("  ✅ matching_engine.py patched with I²R line loss (5%).")
print("     Buyers now pay for delivered MWh only.")
print()
