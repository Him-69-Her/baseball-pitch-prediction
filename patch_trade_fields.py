#!/usr/bin/env python3
"""Add grid_price and settled_price fields to simulator output for dashboard compatibility."""
from pathlib import Path

f = Path("shadow_simulator.py")
src = f.read_text()
orig = src

# Add the missing fields right after "net_profit" in the trade dict
src = src.replace(
    '"net_profit": round(net_profit, 4),',
    '"net_profit": round(net_profit, 4),\n            "grid_price": round(SUPPLY_RATE + AMEREN_TOLL, 4),\n            "settled_price": round(trade_price, 4),'
)

assert src != orig, "No changes applied"
f.write_text(src)
print("[OK] Added grid_price and settled_price to trade output")
