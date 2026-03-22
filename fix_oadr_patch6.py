#!/usr/bin/env python3
"""Fix patch 6 — add OADR curtailment to the matching engine loop."""
from pathlib import Path

MKT = Path("d91_marketplace_live.py")
src = MKT.read_text(encoding="utf-8")

OLD = """    for mt in matched_trades:
        # Automated curtailment — skip solar sellers if clearing price too low
        is_solar = mt.seller_type not in ("battery",)
        if is_solar and mt.settled_price < CURTAIL_FLOOR:
            curtailed_count += 1
            status = "CURTAILED"
            # Publish curtailment event but don't count as settled
        else:
            status = "ISLAND_SETTLED" if islanding else "SETTLED"
            trade_count += 1"""

NEW = """    for mt in matched_trades:
        # Automated curtailment — skip solar sellers if:
        #   1. Clearing price below floor, OR
        #   2. Active OpenADR DR event requires curtailment
        is_solar = mt.seller_type not in ("battery",)
        with _oadr_lock:
            oadr_pct = _oadr_curtail_pct
        oadr_curtailed = is_solar and oadr_pct > 0 and random.random() < oadr_pct
        price_curtailed = is_solar and mt.settled_price < CURTAIL_FLOOR
        if oadr_curtailed or price_curtailed:
            curtailed_count += 1
            status = "CURTAILED"
            # Publish curtailment event but don't count as settled
        else:
            status = "ISLAND_SETTLED" if islanding else "SETTLED"
            trade_count += 1"""

if OLD not in src:
    print("  ❌ Block not found")
    exit(1)

src = src.replace(OLD, NEW, 1)
MKT.write_text(src, encoding="utf-8")
print("  ✅ Patch 6 fixed: OADR curtailment wired into matching engine loop")
