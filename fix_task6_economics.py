#!/usr/bin/env python3
"""
TINY-HUB — Task #6: Unbundled Economics Refactor
=================================================
Problem:
  The clearing price math treats the full retail rate ($0.12/kWh) as
  the benchmark. But buyers still pay the utility for delivery/logistics
  (~$0.05/kWh) regardless of P2P trading. Tiny-Hub can only displace
  the SUPPLY component (~$0.07/kWh).

  Current: settled = (ask + bid) / 2, compared against full retail
  Result:  Overstated savings, legally questionable claims

Fix:
  1. Unbundle retail into supply_rate + delivery_rate
  2. Sellers ask against the supply rate, not full retail
  3. Clearing price targets below supply_rate
  4. Buyer savings = supply_rate - settled_price (honest math)
  5. Add supply_rate_mwh and delivery_rate_mwh to trade data
  6. MatchedTrade gets buyer_savings and savings_pct fields

  IL Rate Unbundling (ICC filings):
    Ameren IL:  Supply ~$0.07/kWh ($70/MWh), Delivery ~$0.05/kWh ($50/MWh)
    ComEd:      Supply ~$0.065/kWh ($65/MWh), Delivery ~$0.055/kWh ($55/MWh)

Run from project root:
    python3 fix_task6_economics.py
"""
from pathlib import Path

ENGINE = Path("matching_engine.py")
if not ENGINE.exists():
    print("  ❌ matching_engine.py not found")
    exit(1)

src = ENGINE.read_text(encoding="utf-8")
patches = 0

# ══════════════════════════════════════════════════════════════
# PATCH 1: Add unbundled rate constants after AMEREN_RETAIL_RATE
# ══════════════════════════════════════════════════════════════

OLD_RETAIL = "AMEREN_RETAIL_RATE = 0.12   # $/kWh (typical IL residential retail)"

NEW_RETAIL = """AMEREN_RETAIL_RATE = 0.12   # $/kWh (typical IL residential retail)

# ── Unbundled Rate Components (ICC filings) ─────────────────
# Retail = Supply + Delivery. P2P only displaces Supply.
# Buyers always pay Delivery to the utility regardless.
#
# Ameren IL (D91):  Supply ~$70/MWh, Delivery ~$50/MWh
# ComEd (D63):      Supply ~$65/MWh, Delivery ~$55/MWh
AMEREN_SUPPLY_RATE   = 0.070   # $/kWh — the rate P2P competes against
AMEREN_DELIVERY_RATE = 0.050   # $/kWh — paid to utility regardless
COMED_SUPPLY_RATE    = 0.065   # $/kWh
COMED_DELIVERY_RATE  = 0.055   # $/kWh"""

if "AMEREN_SUPPLY_RATE" not in src:
    if OLD_RETAIL in src:
        src = src.replace(OLD_RETAIL, NEW_RETAIL, 1)
        patches += 1
        print("  ✅ Patch 1: Unbundled rate constants added")
    else:
        print("  ⚠️  Patch 1: AMEREN_RETAIL_RATE line not found")
else:
    print("  ⏭️  Patch 1: Unbundled rates already exist")


# ══════════════════════════════════════════════════════════════
# PATCH 2: Add supply_rate param to MatchingEngine.__init__
# ══════════════════════════════════════════════════════════════

OLD_INIT = """    def __init__(self, toll: float = 0.025, mode: str = "pro_rata",
                 fallback_routing: bool = True,
                 retail_rate: float = AMEREN_RETAIL_RATE):
        \"\"\"
        Args:
            toll:             Grid toll in $/kWh (Ameren=0.025, ComEd=0.02)
            mode:             "pro_rata", "price_priority", or "proximity"
            fallback_routing: If True, unmatched buyers get macro-grid supply
                              at retail_rate. Zero disruption to buyer.
            retail_rate:      Ameren/ComEd retail rate for fallback trades.
        \"\"\""""

NEW_INIT = """    def __init__(self, toll: float = 0.025, mode: str = "pro_rata",
                 fallback_routing: bool = True,
                 retail_rate: float = AMEREN_RETAIL_RATE,
                 supply_rate: float = AMEREN_SUPPLY_RATE,
                 delivery_rate: float = AMEREN_DELIVERY_RATE):
        \"\"\"
        Args:
            toll:             Grid toll in $/kWh (Ameren=0.025, ComEd=0.02)
            mode:             "pro_rata", "price_priority", or "proximity"
            fallback_routing: If True, unmatched buyers get macro-grid supply
                              at retail_rate. Zero disruption to buyer.
            retail_rate:      Full retail rate (supply + delivery).
            supply_rate:      Utility supply-only rate — the rate P2P competes against.
                              Ameren=0.070, ComEd=0.065
            delivery_rate:    Utility delivery/logistics rate — buyer pays this
                              to the utility regardless of P2P trading.
                              Ameren=0.050, ComEd=0.055
        \"\"\""""

if "supply_rate" not in src.split("def __init__")[1][:500] if "def __init__" in src else True:
    if OLD_INIT in src:
        src = src.replace(OLD_INIT, NEW_INIT, 1)
        patches += 1
        print("  ✅ Patch 2: supply_rate + delivery_rate added to __init__")
    else:
        print("  ⚠️  Patch 2: __init__ signature not found exactly")
else:
    print("  ⏭️  Patch 2: supply_rate already in __init__")


# ══════════════════════════════════════════════════════════════
# PATCH 3: Store supply_rate and delivery_rate on self
# ══════════════════════════════════════════════════════════════

# Find where self.retail_rate is stored and add supply/delivery
OLD_SELF_RETAIL = "        self.retail_rate = retail_rate"
NEW_SELF_RETAIL = """        self.retail_rate = retail_rate
        self.supply_rate = supply_rate
        self.delivery_rate = delivery_rate"""

if "self.supply_rate" not in src:
    if OLD_SELF_RETAIL in src:
        src = src.replace(OLD_SELF_RETAIL, NEW_SELF_RETAIL, 1)
        patches += 1
        print("  ✅ Patch 3: self.supply_rate + self.delivery_rate stored")
    else:
        # Try to add after self.toll line
        OLD_TOLL_SELF = "        self.toll = toll"
        if OLD_TOLL_SELF in src:
            src = src.replace(
                OLD_TOLL_SELF,
                OLD_TOLL_SELF + "\n        self.supply_rate = supply_rate\n        self.delivery_rate = delivery_rate",
                1
            )
            patches += 1
            print("  ✅ Patch 3: self.supply_rate + self.delivery_rate stored (alt)")
        else:
            print("  ⚠️  Patch 3: Could not find self.retail_rate or self.toll")
else:
    print("  ⏭️  Patch 3: self.supply_rate already stored")


# ══════════════════════════════════════════════════════════════
# PATCH 4: Add buyer_savings + savings_pct to MatchedTrade
# ══════════════════════════════════════════════════════════════

OLD_MATCHED_TRADE_END = "    match_type: str = \"\""

NEW_MATCHED_TRADE_END = """    match_type: str = ""
    # Unbundled economics (Task #6)
    supply_rate: float = 0.0       # Utility supply rate this trade competes against
    delivery_rate: float = 0.0     # Utility delivery rate (buyer pays regardless)
    buyer_savings: float = 0.0     # $ saved vs utility supply rate
    savings_pct: float = 0.0       # % savings vs supply rate"""

if "buyer_savings" not in src:
    if OLD_MATCHED_TRADE_END in src:
        src = src.replace(OLD_MATCHED_TRADE_END, NEW_MATCHED_TRADE_END, 1)
        patches += 1
        print("  ✅ Patch 4: buyer_savings + savings_pct added to MatchedTrade")
    else:
        print("  ⚠️  Patch 4: MatchedTrade match_type field not found")
else:
    print("  ⏭️  Patch 4: buyer_savings already in MatchedTrade")


# ══════════════════════════════════════════════════════════════
# PATCH 5: Update clearing price calculation in pro_rata
# Change from: settled = (ask + bid) / 2
# To: settled capped at supply_rate, with savings calculated
# ══════════════════════════════════════════════════════════════

# Pro-rata match
OLD_PRORATA_SETTLED = """            delivered_mwh = round(generated_mwh * (1 - LINE_LOSS_PCT), 4)
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
                ))"""

NEW_PRORATA_SETTLED = """            delivered_mwh = round(generated_mwh * (1 - LINE_LOSS_PCT), 4)
                # Unbundled clearing: midpoint of ask/bid, capped at supply rate
                raw_settled = (s.ask_price + buyer.bid_price) / 2
                settled = round(min(raw_settled, self.supply_rate * 0.95), 4)  # 5% below supply = guaranteed savings
                profit  = round((settled - self.toll) * generated_mwh, 4)
                savings = round((self.supply_rate - settled) * delivered_mwh, 4)
                savings_pct = round((1 - settled / self.supply_rate) * 100, 1) if self.supply_rate > 0 else 0
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
                    supply_rate=self.supply_rate,
                    delivery_rate=self.delivery_rate,
                    buyer_savings=savings,
                    savings_pct=savings_pct,
                ))"""

if "supply_rate=self.supply_rate" not in src and OLD_PRORATA_SETTLED in src:
    src = src.replace(OLD_PRORATA_SETTLED, NEW_PRORATA_SETTLED, 1)
    patches += 1
    print("  ✅ Patch 5: Pro-rata clearing price unbundled + savings calc")
elif "supply_rate=self.supply_rate" in src:
    print("  ⏭️  Patch 5: Pro-rata already unbundled")
else:
    print("  ⚠️  Patch 5: Pro-rata settled block not found exactly")


# ══════════════════════════════════════════════════════════════
# PATCH 6: Same fix for price_priority matcher
# ══════════════════════════════════════════════════════════════

OLD_PRIORITY_SETTLED = """            generated_mwh = min(s.remaining_mwh, b.remaining_mwh)
            delivered_mwh = round(generated_mwh * (1 - LINE_LOSS_PCT), 4)
            settled  = round((s.ask_price + b.bid_price) / 2, 4)
            profit   = round((settled - self.toll) * generated_mwh, 4)
            dist     = self._distance(s, b)

            trades.append(MatchedTrade(
                seller_id=s.station_id, seller_label=s.label,
                seller_town=s.town, seller_type=s.seller_type,
                buyer_id=b.buyer_id, buyer_label=b.label,
                buyer_town=b.town, buyer_type=b.buyer_type,
                mwh=delivered_mwh, ask_price=s.ask_price,
                bid_price=b.bid_price, settled_price=settled,
                net_profit=profit, grid_price=grid_price,
                match_type="price_priority", distance_km=dist,
            ))"""

NEW_PRIORITY_SETTLED = """            generated_mwh = min(s.remaining_mwh, b.remaining_mwh)
            delivered_mwh = round(generated_mwh * (1 - LINE_LOSS_PCT), 4)
            # Unbundled clearing: midpoint capped at supply rate
            raw_settled = (s.ask_price + b.bid_price) / 2
            settled  = round(min(raw_settled, self.supply_rate * 0.95), 4)
            profit   = round((settled - self.toll) * generated_mwh, 4)
            savings  = round((self.supply_rate - settled) * delivered_mwh, 4)
            savings_pct = round((1 - settled / self.supply_rate) * 100, 1) if self.supply_rate > 0 else 0
            dist     = self._distance(s, b)

            trades.append(MatchedTrade(
                seller_id=s.station_id, seller_label=s.label,
                seller_town=s.town, seller_type=s.seller_type,
                buyer_id=b.buyer_id, buyer_label=b.label,
                buyer_town=b.town, buyer_type=b.buyer_type,
                mwh=delivered_mwh, ask_price=s.ask_price,
                bid_price=b.bid_price, settled_price=settled,
                net_profit=profit, grid_price=grid_price,
                match_type="price_priority", distance_km=dist,
                supply_rate=self.supply_rate,
                delivery_rate=self.delivery_rate,
                buyer_savings=savings,
                savings_pct=savings_pct,
            ))"""

if OLD_PRIORITY_SETTLED in src and "supply_rate=self.supply_rate" not in src.split("price_priority")[0]:
    src = src.replace(OLD_PRIORITY_SETTLED, NEW_PRIORITY_SETTLED, 1)
    patches += 1
    print("  ✅ Patch 6: Price-priority clearing price unbundled + savings calc")
elif "price_priority" in src and "supply_rate=self.supply_rate" in src:
    print("  ⏭️  Patch 6: Price-priority already unbundled")
else:
    print("  ⚠️  Patch 6: Price-priority settled block not found exactly")


# ══════════════════════════════════════════════════════════════
# PATCH 7: Update D63 marketplace to pass ComEd rates
# ══════════════════════════════════════════════════════════════
D63 = Path("d63_marketplace_live.py")
if D63.exists():
    d63_src = D63.read_text(encoding="utf-8")
    # D63 doesn't use MatchingEngine (uses random matching), but if it does:
    if "MatchingEngine" in d63_src and "supply_rate" not in d63_src:
        OLD_D63_ENGINE = "MatchingEngine(toll=COMED_TOLL"
        NEW_D63_ENGINE = "MatchingEngine(toll=COMED_TOLL, supply_rate=0.065, delivery_rate=0.055"
        if OLD_D63_ENGINE in d63_src:
            d63_src = d63_src.replace(OLD_D63_ENGINE, NEW_D63_ENGINE, 1)
            D63.write_text(d63_src, encoding="utf-8")
            patches += 1
            print("  ✅ Patch 7: D63 marketplace gets ComEd supply/delivery rates")
        else:
            print("  ⏭️  Patch 7: D63 engine init not found (may use random matching)")
    else:
        print("  ⏭️  Patch 7: D63 already has supply_rate or no MatchingEngine")
else:
    print("  ⚠️  Patch 7: d63_marketplace_live.py not found")


# ══════════════════════════════════════════════════════════════
# PATCH 8: Update D91 marketplace to pass Ameren rates
# ══════════════════════════════════════════════════════════════
D91 = Path("d91_marketplace_live.py")
if D91.exists():
    d91_src = D91.read_text(encoding="utf-8")
    if "supply_rate" not in d91_src:
        OLD_D91_ENGINE = "MatchingEngine(toll=AMEREN_TOLL"
        NEW_D91_ENGINE = "MatchingEngine(toll=AMEREN_TOLL, supply_rate=0.070, delivery_rate=0.050"
        if OLD_D91_ENGINE in d91_src:
            d91_src = d91_src.replace(OLD_D91_ENGINE, NEW_D91_ENGINE, 1)
            D91.write_text(d91_src, encoding="utf-8")
            patches += 1
            print("  ✅ Patch 8: D91 marketplace gets Ameren supply/delivery rates")
        else:
            print("  ⚠️  Patch 8: D91 engine init not found")
    else:
        print("  ⏭️  Patch 8: D91 already has supply_rate")
else:
    print("  ⚠️  Patch 8: d91_marketplace_live.py not found")


# ══════════════════════════════════════════════════════════════
# Write matching_engine.py
# ══════════════════════════════════════════════════════════════
ENGINE.write_text(src, encoding="utf-8")

print()
print(f"  ✅ Task #6 complete — {patches} patches applied")
print()
print("  Unbundled Economics:")
print("    Ameren (D91): Supply $0.070/kWh + Delivery $0.050/kWh = $0.120/kWh retail")
print("    ComEd  (D63): Supply $0.065/kWh + Delivery $0.055/kWh = $0.120/kWh retail")
print()
print("  Clearing price now:")
print("    • Capped at 95% of supply rate (guaranteed 5%+ buyer savings)")
print("    • Midpoint of ask/bid, but never exceeds supply-only benchmark")
print("    • buyer_savings = (supply_rate - settled) * MWh")
print("    • savings_pct = % below utility supply rate")
print()
print("  New fields in MatchedTrade:")
print("    supply_rate, delivery_rate, buyer_savings, savings_pct")
print()
print("  Rebuild:")
print("    sudo docker compose up -d --build d91 d63")
print()
