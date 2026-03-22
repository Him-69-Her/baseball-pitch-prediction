#!/usr/bin/env python3
"""Fix curtailment patch for matching-engine-based settlement."""
from pathlib import Path

TARGET = Path("d91_marketplace_live.py")
src = TARGET.read_text(encoding="utf-8")

OLD = """    for mt in matched_trades:
        status = "ISLAND_SETTLED" if islanding else "SETTLED"
        trade_count += 1
        total_profit += mt.net_profit
        total_mwh_traded += mt.mwh"""

NEW = """    for mt in matched_trades:
        # Automated curtailment — skip solar sellers if clearing price too low
        is_solar = mt.seller_type not in ("battery",)
        if is_solar and mt.settled_price < CURTAIL_FLOOR:
            curtailed_count += 1
            status = "CURTAILED"
            # Publish curtailment event but don't count as settled
        else:
            status = "ISLAND_SETTLED" if islanding else "SETTLED"
            trade_count += 1
            total_profit += mt.net_profit
            total_mwh_traded += mt.mwh"""

if OLD not in src:
    print("  ❌ Block not found")
    exit(1)

src = src.replace(OLD, NEW, 1)
TARGET.write_text(src, encoding="utf-8")
print("  ✅ Curtailment check added to matching engine settlement loop")
