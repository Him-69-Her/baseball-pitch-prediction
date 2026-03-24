#!/usr/bin/env python3
"""
TINY-HUB — Tasks #17-#20: Dashboard UX Widgets
================================================
Injects 4 new panels into the existing dashboard:

#17 — Click-a-Building ROI Simulator
      Click any seller on the map → popup shows estimated annual ROI,
      payback period, and savings vs grid.

#18 — Utility Bill Comparison Tool
      Side-by-side panel: "Your bill with ComEd/Ameren" vs "Your bill
      with Tiny-Hub P2P". Shows monthly savings.

#19 — Live Price Spread Chart
      Real-time sparkline showing grid LMP vs P2P clearing price.
      Updates every trade tick via SSE.

#20 — Community Wealth Retained Tickers
      Running counters: $ kept in community, $ diverted from utility,
      local jobs equivalent, CO₂ offset in cars-removed equivalent.

Run from project root:
    python3 fix_task17_20_dashboard.py
    sudo docker compose up -d --build dashboard
"""
from pathlib import Path

DASH = Path("templates/dashboard.html")
if not DASH.exists():
    print("  ❌ templates/dashboard.html not found")
    exit(1)

src = DASH.read_text(encoding="utf-8")
patches = 0

# ══════════════════════════════════════════════════════════════
# PATCH 1: Add CSS for new widgets (before </style>)
# ══════════════════════════════════════════════════════════════

WIDGET_CSS = """
        /* ═══ Tasks #17-#20: Dashboard Widgets ═══ */
        .widget-drawer { position:absolute; bottom:60px; left:14px; right:14px; z-index:500; pointer-events:auto; display:flex; gap:10px; flex-wrap:wrap; }
        .widget-card { background:var(--card); border:1px solid var(--border); border-radius:4px; padding:12px 14px; backdrop-filter:blur(14px); flex:1; min-width:220px; max-width:320px; }
        .widget-title { font-size:0.5rem; letter-spacing:2px; text-transform:uppercase; color:var(--green-dim); margin-bottom:8px; font-weight:700; }
        .widget-toggle { position:absolute; bottom:60px; right:14px; z-index:501; pointer-events:auto; }
        .widget-toggle button { background:var(--card); border:1px solid var(--border); color:var(--green); font-family:'JetBrains Mono',monospace; font-size:0.55rem; padding:6px 12px; cursor:pointer; border-radius:2px; letter-spacing:1px; }
        .widget-toggle button:hover { background:rgba(0,255,157,0.1); }

        /* #17 ROI Popup */
        .roi-popup { font-family:'JetBrains Mono',monospace; font-size:0.65rem; min-width:240px; }
        .roi-popup h3 { font-family:'Outfit',sans-serif; font-size:0.85rem; margin-bottom:6px; color:#111; }
        .roi-row { display:flex; justify-content:space-between; padding:2px 0; }
        .roi-label { color:#888; }
        .roi-val { font-weight:700; }
        .roi-val.green { color:#00a86b; }
        .roi-val.amber { color:#cc8800; }
        .roi-savings { background:#e8fff0; border:1px solid #00a86b; border-radius:4px; padding:6px 8px; margin-top:6px; text-align:center; }
        .roi-savings .big { font-size:1.1rem; font-weight:900; color:#00a86b; }

        /* #18 Bill Comparison */
        .bill-compare { display:flex; gap:8px; }
        .bill-col { flex:1; background:rgba(0,0,0,0.2); border-radius:3px; padding:8px; text-align:center; }
        .bill-col.utility { border-top:2px solid #ff4444; }
        .bill-col.p2p { border-top:2px solid var(--green); }
        .bill-col .bill-header { font-size:0.45rem; letter-spacing:1.5px; color:rgba(255,255,255,0.5); margin-bottom:6px; text-transform:uppercase; }
        .bill-col .bill-amount { font-size:1.1rem; font-weight:900; }
        .bill-col.utility .bill-amount { color:#ff4444; }
        .bill-col.p2p .bill-amount { color:var(--green); }
        .bill-savings-banner { text-align:center; margin-top:6px; padding:4px; background:rgba(0,255,157,0.08); border-radius:3px; }
        .bill-savings-banner .pct { font-size:0.9rem; font-weight:900; color:var(--green); }
        .bill-slider { width:100%; margin-top:8px; accent-color:var(--green); }
        .bill-slider-label { font-size:0.45rem; color:rgba(255,255,255,0.4); text-align:center; }

        /* #19 Price Spread */
        .spread-chart { height:60px; position:relative; overflow:hidden; }
        .spread-canvas { width:100%; height:100%; }
        .spread-legend { display:flex; gap:12px; font-size:0.45rem; margin-top:4px; }
        .spread-legend span { display:flex; align-items:center; gap:3px; }
        .spread-dot { width:6px; height:6px; border-radius:50%; display:inline-block; }
        .spread-dot.grid { background:#ff4444; }
        .spread-dot.p2p { background:var(--green); }
        .spread-now { font-size:0.7rem; font-weight:700; display:flex; justify-content:space-between; margin-bottom:4px; }
        .spread-now .grid-price { color:#ff4444; }
        .spread-now .p2p-price { color:var(--green); }
        .spread-now .spread-val { color:var(--amber); }

        /* #20 Community Tickers */
        .ticker-grid { display:grid; grid-template-columns:1fr 1fr; gap:6px; }
        .ticker-item { text-align:center; padding:4px; }
        .ticker-value { font-size:0.9rem; font-weight:900; color:var(--green); }
        .ticker-label { font-size:0.4rem; letter-spacing:1.5px; color:rgba(255,255,255,0.4); text-transform:uppercase; margin-top:2px; }
        .ticker-value.amber { color:var(--amber); }
        .ticker-value.blue { color:var(--blue); }
        .ticker-value.purple { color:#a855f7; }
"""

STYLE_END = "    </style>"
if "widget-drawer" not in src:
    src = src.replace(STYLE_END, WIDGET_CSS + "\n" + STYLE_END, 1)
    patches += 1
    print("  ✅ Patch 1: Widget CSS injected")
else:
    print("  ⏭️  Patch 1: CSS already exists")


# ══════════════════════════════════════════════════════════════
# PATCH 2: Add widget HTML panels (before bridge-bar)
# ══════════════════════════════════════════════════════════════

WIDGET_HTML = """
    <!-- ═══ Tasks #17-#20: Dashboard Widgets ═══ -->
    <div class="widget-drawer" id="widget-drawer" style="display:none;">

        <!-- #18 Utility Bill Comparison -->
        <div class="widget-card">
            <div class="widget-title">⚡ Monthly Bill Comparison</div>
            <div class="bill-compare">
                <div class="bill-col utility">
                    <div class="bill-header">ComEd / Ameren</div>
                    <div class="bill-amount" id="bill-utility">$142</div>
                    <div style="font-size:0.4rem;color:rgba(255,255,255,0.3);margin-top:2px;">Supply + Delivery</div>
                </div>
                <div class="bill-col p2p">
                    <div class="bill-header">Tiny-Hub P2P</div>
                    <div class="bill-amount" id="bill-p2p">$108</div>
                    <div style="font-size:0.4rem;color:rgba(255,255,255,0.3);margin-top:2px;">P2P Supply + Delivery</div>
                </div>
            </div>
            <div class="bill-savings-banner">
                You save <span class="pct" id="bill-savings-pct">24%</span> /month → <span style="color:var(--green);font-weight:700;" id="bill-savings-amt">$34/mo</span>
            </div>
            <input type="range" class="bill-slider" id="bill-kwh-slider" min="200" max="3000" value="1000" step="50">
            <div class="bill-slider-label"><span id="bill-kwh-label">1,000</span> kWh/month usage</div>
        </div>

        <!-- #19 Live Price Spread -->
        <div class="widget-card">
            <div class="widget-title">📊 Live Price Spread</div>
            <div class="spread-now">
                <span>Grid: <span class="grid-price" id="spread-grid">$0.000</span></span>
                <span>Spread: <span class="spread-val" id="spread-diff">$0.000</span></span>
                <span>P2P: <span class="p2p-price" id="spread-p2p">$0.000</span></span>
            </div>
            <div class="spread-chart">
                <canvas class="spread-canvas" id="spread-canvas"></canvas>
            </div>
            <div class="spread-legend">
                <span><span class="spread-dot grid"></span> Grid LMP</span>
                <span><span class="spread-dot p2p"></span> P2P Clearing</span>
            </div>
        </div>

        <!-- #20 Community Wealth Retained -->
        <div class="widget-card">
            <div class="widget-title">🏘️ Community Wealth Retained</div>
            <div class="ticker-grid">
                <div class="ticker-item">
                    <div class="ticker-value" id="tk-retained">$0</div>
                    <div class="ticker-label">$ Kept Local</div>
                </div>
                <div class="ticker-item">
                    <div class="ticker-value amber" id="tk-diverted">$0</div>
                    <div class="ticker-label">$ Saved vs Utility</div>
                </div>
                <div class="ticker-item">
                    <div class="ticker-value blue" id="tk-cars">0</div>
                    <div class="ticker-label">Cars Removed (CO₂)</div>
                </div>
                <div class="ticker-item">
                    <div class="ticker-value purple" id="tk-jobs">0.0</div>
                    <div class="ticker-label">Local Job Equiv.</div>
                </div>
            </div>
        </div>

    </div>
    <div class="widget-toggle" id="widget-toggle">
        <button onclick="toggleWidgets()">📊 ANALYTICS</button>
    </div>
"""

BRIDGE_BAR = '    <div class="bridge-bar">'
if "widget-drawer" not in src:
    src = src.replace(BRIDGE_BAR, WIDGET_HTML + "\n" + BRIDGE_BAR, 1)
    patches += 1
    print("  ✅ Patch 2: Widget HTML panels injected")
else:
    print("  ⏭️  Patch 2: Widget HTML already exists")


# ══════════════════════════════════════════════════════════════
# PATCH 3: Add widget JavaScript (before closing </script>)
# ══════════════════════════════════════════════════════════════

WIDGET_JS = """
    // ═══ TASKS #17-#20: DASHBOARD WIDGETS ═══

    // ── Widget Toggle ──
    let widgetsVisible = false;
    function toggleWidgets() {
        widgetsVisible = !widgetsVisible;
        document.getElementById('widget-drawer').style.display = widgetsVisible ? 'flex' : 'none';
    }

    // ── #17: ROI Popup (injected into map marker popups) ──
    function roiPopupContent(building) {
        const sqft = building.sq || 5000;
        const mwhYear = building.mwh || (sqft * 0.015 / 1000);  // rough estimate
        const annualKwh = mwhYear * 1000;

        // Economics (unbundled — Task #6)
        const supplyRate = currentView === 'd63' ? 0.065 : 0.070;  // $/kWh
        const deliveryRate = currentView === 'd63' ? 0.055 : 0.050;
        const retailRate = supplyRate + deliveryRate;
        const p2pRate = supplyRate * 0.80;  // ~20% below supply
        const tollRate = currentView === 'd63' ? 0.020 : 0.025;

        // Seller ROI
        const annualRevenue = annualKwh * (p2pRate - tollRate);
        const installCost = sqft * 0.15;  // rough $/sqft for solar
        const paybackYears = installCost > 0 ? (installCost / annualRevenue) : 0;
        const co2Tons = mwhYear * 0.42;

        // Buyer savings
        const buyerSavingsKwh = supplyRate - p2pRate;
        const buyerSavingsYear = annualKwh * buyerSavingsKwh;

        return `<div class="roi-popup">
            <h3>${building.n || 'Building'}</h3>
            <div class="roi-row"><span class="roi-label">Rooftop</span><span class="roi-val">${sqft.toLocaleString()} sqft</span></div>
            <div class="roi-row"><span class="roi-label">Est. Solar</span><span class="roi-val">${annualKwh.toLocaleString()} kWh/yr</span></div>
            <div class="roi-row"><span class="roi-label">Grid Rate</span><span class="roi-val">$${retailRate.toFixed(3)}/kWh</span></div>
            <div class="roi-row"><span class="roi-label">P2P Rate</span><span class="roi-val green">$${p2pRate.toFixed(3)}/kWh</span></div>
            <hr style="border-color:#eee;margin:4px 0;">
            <div class="roi-row"><span class="roi-label">Seller Revenue</span><span class="roi-val green">$${annualRevenue.toFixed(0)}/yr</span></div>
            <div class="roi-row"><span class="roi-label">Buyer Savings</span><span class="roi-val green">$${buyerSavingsYear.toFixed(0)}/yr</span></div>
            <div class="roi-row"><span class="roi-label">Payback</span><span class="roi-val amber">${paybackYears.toFixed(1)} yrs</span></div>
            <div class="roi-row"><span class="roi-label">CO₂ Offset</span><span class="roi-val green">${co2Tons.toFixed(1)} t/yr</span></div>
            <div class="roi-savings">
                <div class="big">${((1 - p2pRate/supplyRate) * 100).toFixed(0)}% cheaper than grid supply</div>
            </div>
        </div>`;
    }

    // Override the default popup to include ROI
    const _origBindPopup = L.CircleMarker.prototype.bindPopup;
    L.CircleMarker.prototype.bindPopup = function(content, options) {
        // If it's a seller popup (has sqft info), enhance it
        if (typeof content === 'string' && content.includes('MWh/yr')) {
            const self = this;
            return _origBindPopup.call(this, function() {
                // Extract building data from the original popup
                const match = content.match(/sqft.*?([\\d,.]+)\\s*MWh/);
                const sqMatch = content.match(/([\\d,]+)\\s*sqft/);
                const nameMatch = content.match(/<b>([^<]+)<\\/b>/);
                const building = {
                    n: nameMatch ? nameMatch[1] : 'Building',
                    sq: sqMatch ? parseInt(sqMatch[1].replace(/,/g, '')) : 5000,
                    mwh: match ? parseFloat(match[1].replace(/,/g, '')) : 1,
                };
                return roiPopupContent(building);
            }, options);
        }
        return _origBindPopup.call(this, content, options);
    };

    // ── #18: Bill Comparison Slider ──
    const billSlider = document.getElementById('bill-kwh-slider');
    if (billSlider) {
        billSlider.addEventListener('input', function() {
            updateBillComparison(parseInt(this.value));
        });
    }

    function updateBillComparison(kwhMonth) {
        const isD63 = currentView === 'd63';
        const supplyRate = isD63 ? 0.065 : 0.070;
        const deliveryRate = isD63 ? 0.055 : 0.050;
        const retailRate = supplyRate + deliveryRate;
        const p2pSupplyRate = supplyRate * 0.80;  // 20% savings on supply
        const p2pTotal = (p2pSupplyRate + deliveryRate);  // still pay delivery

        const utilityBill = kwhMonth * retailRate;
        const p2pBill = kwhMonth * p2pTotal;
        const savings = utilityBill - p2pBill;
        const savingsPct = (savings / utilityBill * 100);

        const el = id => document.getElementById(id);
        el('bill-utility').textContent = '$' + utilityBill.toFixed(0);
        el('bill-p2p').textContent = '$' + p2pBill.toFixed(0);
        el('bill-savings-pct').textContent = savingsPct.toFixed(0) + '%';
        el('bill-savings-amt').textContent = '$' + savings.toFixed(0) + '/mo';
        el('bill-kwh-label').textContent = kwhMonth.toLocaleString();
    }
    // Init with default
    updateBillComparison(1000);

    // ── #19: Price Spread Chart ──
    const spreadData = { grid: [], p2p: [] };
    const MAX_SPREAD_POINTS = 60;
    let spreadCtx = null;

    function initSpreadChart() {
        const canvas = document.getElementById('spread-canvas');
        if (!canvas) return;
        spreadCtx = canvas.getContext('2d');
        canvas.width = canvas.offsetWidth * 2;
        canvas.height = canvas.offsetHeight * 2;
        spreadCtx.scale(2, 2);
    }

    function updateSpreadChart(gridPrice, p2pPrice) {
        spreadData.grid.push(gridPrice);
        spreadData.p2p.push(p2pPrice);
        if (spreadData.grid.length > MAX_SPREAD_POINTS) {
            spreadData.grid.shift();
            spreadData.p2p.shift();
        }

        // Update text
        const el = id => document.getElementById(id);
        el('spread-grid').textContent = '$' + gridPrice.toFixed(4);
        el('spread-p2p').textContent = '$' + p2pPrice.toFixed(4);
        el('spread-diff').textContent = '$' + (gridPrice - p2pPrice).toFixed(4);

        // Draw
        if (!spreadCtx) initSpreadChart();
        if (!spreadCtx) return;

        const canvas = document.getElementById('spread-canvas');
        const w = canvas.offsetWidth;
        const h = canvas.offsetHeight;

        spreadCtx.clearRect(0, 0, w, h);

        const allVals = [...spreadData.grid, ...spreadData.p2p];
        const minV = Math.min(...allVals) * 0.95;
        const maxV = Math.max(...allVals) * 1.05;
        const range = maxV - minV || 0.01;

        function drawLine(data, color) {
            spreadCtx.beginPath();
            spreadCtx.strokeStyle = color;
            spreadCtx.lineWidth = 1.5;
            data.forEach((v, i) => {
                const x = (i / (MAX_SPREAD_POINTS - 1)) * w;
                const y = h - ((v - minV) / range) * h;
                if (i === 0) spreadCtx.moveTo(x, y);
                else spreadCtx.lineTo(x, y);
            });
            spreadCtx.stroke();
        }

        // Fill spread area
        if (spreadData.grid.length > 1) {
            spreadCtx.beginPath();
            spreadCtx.fillStyle = 'rgba(0,255,157,0.06)';
            spreadData.grid.forEach((v, i) => {
                const x = (i / (MAX_SPREAD_POINTS - 1)) * w;
                const y = h - ((v - minV) / range) * h;
                if (i === 0) spreadCtx.moveTo(x, y);
                else spreadCtx.lineTo(x, y);
            });
            for (let i = spreadData.p2p.length - 1; i >= 0; i--) {
                const x = (i / (MAX_SPREAD_POINTS - 1)) * w;
                const y = h - ((spreadData.p2p[i] - minV) / range) * h;
                spreadCtx.lineTo(x, y);
            }
            spreadCtx.closePath();
            spreadCtx.fill();
        }

        drawLine(spreadData.grid, '#ff4444');
        drawLine(spreadData.p2p, '#00ff9d');
    }

    // ── #20: Community Wealth Tickers ──
    let communityStats = { retained: 0, diverted: 0, co2: 0 };

    function updateCommunityTickers(profit, mwh, co2) {
        communityStats.retained += profit;
        communityStats.diverted += profit * 0.85;  // 85% stays local
        communityStats.co2 += co2;

        const el = id => document.getElementById(id);
        el('tk-retained').textContent = '$' + communityStats.retained.toFixed(0);
        el('tk-diverted').textContent = '$' + communityStats.diverted.toFixed(0);
        // 1 car ≈ 4.6 tons CO₂/year
        el('tk-cars').textContent = (communityStats.co2 / 4.6).toFixed(0);
        // $50k revenue ≈ 1 local energy job
        el('tk-jobs').textContent = (communityStats.retained / 50000).toFixed(1);
    }

    // ── Hook into existing trade processor ──
    const _origProcessTrade = typeof processTrade === 'function' ? processTrade : null;
    function processTradeEnhanced(t) {
        // Call original
        if (_origProcessTrade) _origProcessTrade(t);

        // Update widgets
        const gridPrice = parseFloat(t.grid_price || t.gridPrice || 0);
        const settledPrice = parseFloat(t.settled_price || t.settledPrice || 0);
        const mwh = parseFloat(t.mwh || 0);
        const profit = parseFloat(t.net_profit || t.profit || 0);
        const co2 = parseFloat(t.co2_tons || mwh * 0.42);

        if (gridPrice > 0 && settledPrice > 0) {
            updateSpreadChart(gridPrice, settledPrice);
        }

        if (profit > 0) {
            updateCommunityTickers(profit, mwh, co2);
        }
    }

    // Replace processTrade globally if it exists
    if (typeof processTrade !== 'undefined') {
        const _original = processTrade;
        processTrade = function(t) {
            _original(t);
            // Widget updates
            const gridPrice = parseFloat(t.grid_price || t.gridPrice || 0);
            const settledPrice = parseFloat(t.settled_price || t.settledPrice || 0);
            const mwh = parseFloat(t.mwh || 0);
            const profit = parseFloat(t.net_profit || t.profit || 0);
            const co2 = parseFloat(t.co2_tons || mwh * 0.42);
            if (gridPrice > 0 && settledPrice > 0) updateSpreadChart(gridPrice, settledPrice);
            if (profit > 0) updateCommunityTickers(profit, mwh, co2);
        };
    }

    // Init spread chart on load
    setTimeout(initSpreadChart, 1000);
"""

CLOSING_SCRIPT = "    </script>\n</body>"
if "widget-drawer" not in src.split("<script>")[-1]:
    src = src.replace(CLOSING_SCRIPT, WIDGET_JS + "\n" + CLOSING_SCRIPT, 1)
    patches += 1
    print("  ✅ Patch 3: Widget JavaScript injected")
else:
    print("  ⏭️  Patch 3: Widget JS already exists")


# ══════════════════════════════════════════════════════════════
# Write
# ══════════════════════════════════════════════════════════════
DASH.write_text(src, encoding="utf-8")

print()
print(f"  ✅ Tasks #17-#20 complete — {patches} patches applied")
print()
print("  New widgets:")
print("    #17 — ROI Simulator: Click any seller → popup shows payback, revenue, savings")
print("    #18 — Bill Comparison: Slider for kWh usage, side-by-side utility vs P2P cost")
print("    #19 — Price Spread: Real-time sparkline of grid LMP vs P2P clearing price")
print("    #20 — Community Tickers: $ retained, $ saved, cars removed, jobs created")
print()
print("  Toggle: Click '📊 ANALYTICS' button on dashboard to show/hide")
print()
print("  Rebuild:")
print("    sudo docker compose up -d --build dashboard")
print()
