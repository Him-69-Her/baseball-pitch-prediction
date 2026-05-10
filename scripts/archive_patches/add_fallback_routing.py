#!/usr/bin/env python3
"""
TINY-HUB — Add automated fallback routing to matching_engine.py

When no P2P seller can fill a buyer's demand, the engine automatically
generates a synthetic "macro-grid" trade at Ameren retail rate ($0.12/kWh).
Zero disruption to the buyer — they always get electrons.

Run from project root:
    python3 add_fallback_routing.py
"""

from pathlib import Path

TARGET = Path("matching_engine.py")

if not TARGET.exists():
    print(f"  ❌ {TARGET} not found. Run from your project root.")
    exit(1)

source = TARGET.read_text(encoding="utf-8")

# ── Patch 1: Add AMEREN_RETAIL_RATE constant after imports ──
OLD_DATACLASS = "from dataclasses import dataclass, field"
NEW_DATACLASS = """from dataclasses import dataclass, field

# Ameren IL retail rate — fallback price when no P2P seller available
AMEREN_RETAIL_RATE = 0.12   # $/kWh (typical IL residential retail)
AMEREN_SELLER_ID   = "ameren-macro-grid"
AMEREN_SELLER_LABEL = "Ameren IL Macro-Grid"
AMEREN_SELLER_TOWN  = "District-wide\""""

if OLD_DATACLASS not in source:
    print("  ❌ Patch 1 failed — dataclass import not found.")
    exit(1)

source = source.replace(OLD_DATACLASS, NEW_DATACLASS, 1)
print("  ✅ Patch 1: AMEREN_RETAIL_RATE constant added")

# ── Patch 2: Add fallback_routing flag to __init__ ──────────
OLD_INIT = """    def __init__(self, toll: float = 0.025, mode: str = "pro_rata"):
        \"\"\"
        Args:
            toll:  Grid toll in $/kWh (Ameren=0.025, ComEd=0.02)
            mode:  "pro_rata"       — surplus MWh split across all qualifying sellers
                   "price_priority" — cheapest seller fills buyer first (greedy)
        \"\"\"
        self.toll = toll
        self.mode = mode
        self._sell_orders: list[SellOrder] = []
        self._buy_orders:  list[BuyOrder]  = []"""

NEW_INIT = """    def __init__(self, toll: float = 0.025, mode: str = "pro_rata",
                 fallback_routing: bool = True,
                 retail_rate: float = AMEREN_RETAIL_RATE):
        \"\"\"
        Args:
            toll:             Grid toll in $/kWh (Ameren=0.025, ComEd=0.02)
            mode:             "pro_rata" or "price_priority"
            fallback_routing: If True, unmatched buyers get macro-grid supply
                              at retail_rate. Zero disruption to buyer.
            retail_rate:      Ameren/ComEd retail rate for fallback trades.
        \"\"\"
        self.toll = toll
        self.mode = mode
        self.fallback_routing = fallback_routing
        self.retail_rate = retail_rate
        self._sell_orders: list[SellOrder] = []
        self._buy_orders:  list[BuyOrder]  = []"""

if OLD_INIT not in source:
    print("  ❌ Patch 2 failed — __init__ signature not found.")
    exit(1)

source = source.replace(OLD_INIT, NEW_INIT, 1)
print("  ✅ Patch 2: fallback_routing flag added to __init__")

# ── Patch 3: Add fallback logic after match() call ──────────
OLD_MATCH_METHOD = """    def match(self, grid_price: float = 0.0) -> list[MatchedTrade]:
        if self.mode == "pro_rata":
            return self._match_pro_rata(grid_price)
        return self._match_price_priority(grid_price)"""

NEW_MATCH_METHOD = """    def match(self, grid_price: float = 0.0) -> list[MatchedTrade]:
        if self.mode == "pro_rata":
            trades = self._match_pro_rata(grid_price)
        else:
            trades = self._match_price_priority(grid_price)

        if self.fallback_routing:
            trades += self._fallback_unmatched(grid_price)

        return trades

    def _fallback_unmatched(self, grid_price: float) -> list[MatchedTrade]:
        \"\"\"
        For any buyer still holding unmet demand after P2P matching,
        synthesize a macro-grid trade at Ameren retail rate.
        The buyer pays retail; the 'seller' is Ameren's macro-grid.
        Logged with trade_status FALLBACK so dashboard can distinguish.
        \"\"\"
        fallback_trades: list[MatchedTrade] = []

        for b in self._buy_orders:
            if b.remaining_mwh < 1e-4:
                continue  # fully matched by P2P

            fill_mwh = round(b.remaining_mwh, 4)
            # Buyer pays retail; no seller profit — cost is passed through
            profit = round((self.retail_rate - self.toll) * fill_mwh, 4)

            fallback_trades.append(MatchedTrade(
                seller_id=AMEREN_SELLER_ID,
                seller_label=AMEREN_SELLER_LABEL,
                seller_town=AMEREN_SELLER_TOWN,
                seller_type="macro_grid",
                buyer_id=b.buyer_id,
                buyer_label=b.label,
                buyer_town=b.town,
                buyer_type=b.buyer_type,
                mwh=fill_mwh,
                ask_price=self.retail_rate,
                bid_price=self.retail_rate,
                settled_price=self.retail_rate,
                net_profit=profit,
                grid_price=grid_price,
                match_type="fallback",
                distance_km=None,
            ))

            b.remaining_mwh = 0.0  # mark as filled

        return fallback_trades"""

if OLD_MATCH_METHOD not in source:
    print("  ❌ Patch 3 failed — match() method not found.")
    exit(1)

source = source.replace(OLD_MATCH_METHOD, NEW_MATCH_METHOD, 1)
print("  ✅ Patch 3: _fallback_unmatched() added to match()")

# ── Write result ────────────────────────────────────────────
TARGET.write_text(source, encoding="utf-8")
print()
print("  ✅ matching_engine.py patched with fallback routing.")
print("     Restart d91_marketplace_live.py to apply.")
print("     Fallback trades will show [fallback] in logs and FALLBACK status in Pub/Sub.")
print()
