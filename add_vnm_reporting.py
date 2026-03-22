#!/usr/bin/env python3
"""
TINY-HUB — Wire vnm_reporting.py into app.py

Adds:
  GET  /api/vnm/report?period=2025-06&district=IL_D91
  GET  /api/vnm/csv?period=2025-06&district=IL_D91
  GET  /api/vnm/edi?period=2025-06&district=IL_D91

Run from project root:
    python3 add_vnm_reporting.py
"""

from pathlib import Path

VNM = Path("vnm_reporting.py")
if not VNM.exists():
    print("  ❌ vnm_reporting.py not found. Copy it first.")
    exit(1)

APP = Path("app.py")
if not APP.exists():
    print("  ❌ app.py not found.")
    exit(1)

src = APP.read_text(encoding="utf-8")

# Patch 1: Add import
if "vnm_reporting" not in src:
    ANCHOR = "from fraud_detection import get_detector"
    NEW_IMPORT = "from fraud_detection import get_detector\nfrom vnm_reporting import VNMReporter"

    if ANCHOR in src:
        src = src.replace(ANCHOR, NEW_IMPORT, 1)
        print("  ✅ Patch 1: vnm_reporting import added")
    else:
        # Fallback anchor
        ANCHOR2 = "from smart_meter import get_meter_client"
        if ANCHOR2 in src:
            src = src.replace(ANCHOR2, ANCHOR2 + "\nfrom vnm_reporting import VNMReporter", 1)
            print("  ✅ Patch 1: vnm_reporting import added (alt)")
        else:
            print("  ❌ Patch 1 failed")
            exit(1)
else:
    print("  ⏭️  Patch 1: vnm_reporting already imported")

# Patch 2: Add API routes
ANCHOR_MAIN = 'if __name__ == "__main__":'

VNM_ROUTES = '''
# ── VNM Regulatory Reporting API ─────────────────────────────
_vnm_reporter = VNMReporter()

@app.route("/api/vnm/report")
def api_vnm_report():
    """Generate ICC-compliant VNM settlement report."""
    period = request.args.get("period", datetime.utcnow().strftime("%Y-%m"))
    district = request.args.get("district", "IL_D91")

    # Collect trades from buffer
    trades_source = list(d91_trades) if "D91" in district else list(d63_trades)
    report = _vnm_reporter.generate_monthly_report(period, trades_source, district)
    return jsonify(_vnm_reporter.to_summary_dict(report))


@app.route("/api/vnm/csv")
def api_vnm_csv():
    """Download VNM credit allocations as CSV."""
    period = request.args.get("period", datetime.utcnow().strftime("%Y-%m"))
    district = request.args.get("district", "IL_D91")

    trades_source = list(d91_trades) if "D91" in district else list(d63_trades)
    report = _vnm_reporter.generate_monthly_report(period, trades_source, district)
    csv_data = _vnm_reporter.to_csv(report)

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=vnm_{district}_{period}.csv"}
    )


@app.route("/api/vnm/edi")
def api_vnm_edi():
    """Download EDI 867 format for utility interchange."""
    period = request.args.get("period", datetime.utcnow().strftime("%Y-%m"))
    district = request.args.get("district", "IL_D91")

    trades_source = list(d91_trades) if "D91" in district else list(d63_trades)
    report = _vnm_reporter.generate_monthly_report(period, trades_source, district)
    edi_data = _vnm_reporter.to_edi_867(report)

    return Response(
        edi_data,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment;filename=vnm_edi867_{district}_{period}.txt"}
    )


'''

if "/api/vnm/" in src:
    print("  ⏭️  Patch 2: VNM routes already exist")
elif ANCHOR_MAIN in src:
    src = src.replace(ANCHOR_MAIN, VNM_ROUTES + ANCHOR_MAIN, 1)
    print("  ✅ Patch 2: VNM reporting API routes added")
else:
    print("  ❌ Patch 2 failed")

APP.write_text(src, encoding="utf-8")

print()
print("  ✅ VNM regulatory reporting wired in.")
print()
print("  Endpoints:")
print("    GET /api/vnm/report?period=2025-06&district=IL_D91  — JSON report")
print("    GET /api/vnm/csv?period=2025-06&district=IL_D91     — CSV download")
print("    GET /api/vnm/edi?period=2025-06&district=IL_D91     — EDI 867 format")
print()
print("  ICC compliance: VNM credit rates")
print("    Ameren IL: $0.08/kWh | ComEd: $0.07/kWh")
print()
print("  Rebuild: sudo docker-compose up -d --build")
print()
