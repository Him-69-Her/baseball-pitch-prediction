"""
TINY-HUB-NETWORK — VNM Regulatory Reporting
Auto-formats settlements into Illinois Commerce Commission (ICC)
compliant reports for Virtual Net Metering (VNM) utility bill credits.

Generates:
  1. Monthly settlement summary (PDF-ready data)
  2. EDI 867 usage data format (utility interchange)
  3. Per-building credit allocation CSV
  4. ICC compliance report

Usage:
    from vnm_reporting import VNMReporter

    reporter = VNMReporter()
    report = reporter.generate_monthly_report("2025-06", trades)
"""

import csv
import json
import io
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict


@dataclass
class BuildingCredit:
    building_id: str
    label: str
    district: str
    role: str            # "seller" or "buyer"
    total_mwh: float
    total_kwh: float
    credit_amount: float  # $ credit on utility bill
    trade_count: int
    co2_tons: float


@dataclass
class MonthlyReport:
    period: str             # "2025-06"
    generated_at: str
    district: str
    total_trades: int
    total_mwh: float
    total_kwh: float
    total_credits: float    # $ total bill credits
    total_co2_tons: float
    seller_credits: list    # list[BuildingCredit]
    buyer_credits: list     # list[BuildingCredit]
    settlement_rate: float  # % of trades settled
    avg_clearing_price: float


# Illinois VNM credit rates ($/kWh)
# These are the avoided cost rates filed with ICC
AMEREN_VNM_RATE = 0.08    # Ameren IL residential VNM credit
COMED_VNM_RATE = 0.07     # ComEd residential VNM credit
AMEREN_RETAIL = 0.12      # Ameren IL avg retail rate
COMED_RETAIL = 0.11       # ComEd avg retail rate


class VNMReporter:
    """
    Generates ICC-compliant Virtual Net Metering reports.
    """

    def __init__(self, ameren_rate: float = AMEREN_VNM_RATE,
                 comed_rate: float = COMED_VNM_RATE):
        self.ameren_rate = ameren_rate
        self.comed_rate = comed_rate

    def _credit_rate(self, district: str) -> float:
        """Get VNM credit rate for a district."""
        if "D91" in district or "ameren" in district.lower():
            return self.ameren_rate
        return self.comed_rate

    def generate_monthly_report(self, period: str, trades: list,
                                 district: str = "IL_D91") -> MonthlyReport:
        """
        Generate a monthly VNM settlement report.

        Args:
            period:   Month string like "2025-06"
            trades:   List of trade dicts from Pub/Sub / BigQuery
            district: "IL_D91" or "McHenry_D63"

        Returns:
            MonthlyReport with per-building credit allocations
        """
        credit_rate = self._credit_rate(district)

        # Aggregate by building
        seller_agg = defaultdict(lambda: {
            "label": "", "mwh": 0.0, "trades": 0, "co2": 0.0
        })
        buyer_agg = defaultdict(lambda: {
            "label": "", "mwh": 0.0, "trades": 0, "co2": 0.0
        })

        settled_count = 0
        total_count = 0
        prices = []

        for t in trades:
            total_count += 1
            status = t.get("trade_status", "")
            if status not in ("SETTLED", "ISLAND_SETTLED"):
                continue

            settled_count += 1
            mwh = t.get("mwh", 0)
            co2 = t.get("co2_tons", mwh * 0.42)
            price = t.get("settled_price", 0)
            prices.append(price)

            sid = t.get("station_id", "unknown")
            seller_agg[sid]["label"] = t.get("seller_label", sid)
            seller_agg[sid]["mwh"] += mwh
            seller_agg[sid]["trades"] += 1
            seller_agg[sid]["co2"] += co2

            bid = t.get("buyer_id", "unknown")
            buyer_agg[bid]["label"] = t.get("buyer_label", bid)
            buyer_agg[bid]["mwh"] += mwh
            buyer_agg[bid]["trades"] += 1
            buyer_agg[bid]["co2"] += co2

        # Build credit allocations
        seller_credits = []
        for sid, data in sorted(seller_agg.items(), key=lambda x: -x[1]["mwh"]):
            kwh = data["mwh"] * 1000
            seller_credits.append(BuildingCredit(
                building_id=sid, label=data["label"], district=district,
                role="seller", total_mwh=round(data["mwh"], 4),
                total_kwh=round(kwh, 1),
                credit_amount=round(kwh * credit_rate, 2),
                trade_count=data["trades"],
                co2_tons=round(data["co2"], 3),
            ))

        buyer_credits = []
        for bid, data in sorted(buyer_agg.items(), key=lambda x: -x[1]["mwh"]):
            kwh = data["mwh"] * 1000
            buyer_credits.append(BuildingCredit(
                building_id=bid, label=data["label"], district=district,
                role="buyer", total_mwh=round(data["mwh"], 4),
                total_kwh=round(kwh, 1),
                credit_amount=round(kwh * credit_rate, 2),
                trade_count=data["trades"],
                co2_tons=round(data["co2"], 3),
            ))

        total_mwh = sum(c.total_mwh for c in seller_credits)

        return MonthlyReport(
            period=period,
            generated_at=datetime.now(timezone.utc).isoformat(),
            district=district,
            total_trades=settled_count,
            total_mwh=round(total_mwh, 2),
            total_kwh=round(total_mwh * 1000, 1),
            total_credits=round(sum(c.credit_amount for c in seller_credits), 2),
            total_co2_tons=round(sum(c.co2_tons for c in seller_credits), 2),
            seller_credits=seller_credits,
            buyer_credits=buyer_credits,
            settlement_rate=round(settled_count / max(total_count, 1) * 100, 1),
            avg_clearing_price=round(sum(prices) / max(len(prices), 1), 4),
        )

    def to_csv(self, report: MonthlyReport) -> str:
        """Export credit allocations as CSV for ICC filing."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "Period", "District", "Building_ID", "Label", "Role",
            "MWh", "kWh", "Credit_USD", "Trades", "CO2_Tons"
        ])

        for c in report.seller_credits + report.buyer_credits:
            writer.writerow([
                report.period, report.district, c.building_id,
                c.label, c.role, c.total_mwh, c.total_kwh,
                c.credit_amount, c.trade_count, c.co2_tons,
            ])

        return output.getvalue()

    def to_edi_867(self, report: MonthlyReport) -> str:
        """
        Generate EDI 867 (Product Transfer and Resale) format.
        Simplified version for Illinois utility interchange.
        """
        lines = []
        ts = datetime.now(timezone.utc).strftime("%y%m%d")
        time_str = datetime.now(timezone.utc).strftime("%H%M")

        # ISA header
        lines.append(f"ISA*00*          *00*          *ZZ*TINYHUB        *ZZ*AMERENUTIL      *{ts}*{time_str}*U*00401*000000001*0*P*>~")
        lines.append("GS*PT*TINYHUB*AMERENUTIL*" + ts + "*" + time_str + "*1*X*004010~")
        lines.append("ST*867*0001~")
        lines.append(f"BPT*52*{report.period.replace('-','')}*{ts}~")

        for i, c in enumerate(report.seller_credits, 1):
            lines.append(f"PTD*{c.building_id}*KH*{c.total_kwh:.1f}*{c.credit_amount:.2f}~")
            lines.append(f"N1*SL*{c.label[:35]}~")

        lines.append(f"CTT*{len(report.seller_credits)}~")
        lines.append("SE*" + str(len(lines) - 1) + "*0001~")
        lines.append("GE*1*1~")
        lines.append("IEA*1*000000001~")

        return "\n".join(lines)

    def to_summary_dict(self, report: MonthlyReport) -> dict:
        """Convert report to JSON-friendly dict for API responses."""
        return {
            "period": report.period,
            "generated_at": report.generated_at,
            "district": report.district,
            "total_trades": report.total_trades,
            "total_mwh": report.total_mwh,
            "total_kwh": report.total_kwh,
            "total_credits_usd": report.total_credits,
            "total_co2_tons": report.total_co2_tons,
            "settlement_rate_pct": report.settlement_rate,
            "avg_clearing_price": report.avg_clearing_price,
            "top_sellers": [
                {"id": c.building_id, "label": c.label, "mwh": c.total_mwh,
                 "credit": c.credit_amount, "co2": c.co2_tons}
                for c in report.seller_credits[:10]
            ],
            "top_buyers": [
                {"id": c.building_id, "label": c.label, "mwh": c.total_mwh,
                 "credit": c.credit_amount, "co2": c.co2_tons}
                for c in report.buyer_credits[:10]
            ],
        }
