#!/usr/bin/env python3
"""Hide residential/EV markers below zoom level 14 in dashboard.html."""
from pathlib import Path

DASH = Path("templates/dashboard.html")
src = DASH.read_text(encoding="utf-8")

# After residential markers are added, store them in a layer group
# and toggle visibility on zoom
OLD_RESIDENTIAL = """            // Plot sellers
            data.sellers.forEach(s => {
                const isEV = s.ev === true;
                const c = isEV ? EV_COLOR : (tierColor[s.ti] || '#ffb800');
                const r = isEV ? 5 : (tierRadius[s.ti] || 4);
                const evLabel = isEV ? '<br>⚡ EV Battery — Seller + Buyer' : '';
                const m = L.circleMarker([s.la, s.ln], {
                    radius: r,
                    color: isEV ? '#00ffff' : c,
                    fillColor: c,
                    fillOpacity: isEV ? 0.9 : 0.6,
                    weight: isEV ? 2 : 1,
                })
                    .addTo(mapD91)
                    .bindPopup(`<div style="font-family:'JetBrains Mono',monospace;font-size:11px"><b>${s.n}</b><br>${s.t}<br>${s.sq.toLocaleString()} sqft · ${s.mwh.toLocaleString()} MWh/yr<br>${s.ti} · ${s.cat}${evLabel}</div>`);
                // Index by partial name for flash matching
                d91SellerIndex[s.n.substring(0, 10)] = { la: s.la, ln: s.ln };"""

NEW_RESIDENTIAL = """            // Residential layer group — hidden until zoom 14
            const residentialLayer = L.layerGroup().addTo(mapD91);
            const RESIDENTIAL_ZOOM = 14;

            // Plot sellers
            data.sellers.forEach(s => {
                const isResidential = s.cat === 'residential';
                const isEV = s.ev === true;
                const c = isEV ? EV_COLOR : (tierColor[s.ti] || '#ffb800');
                const r = isEV ? 5 : (tierRadius[s.ti] || 4);
                const evLabel = isEV ? '<br>⚡ EV Battery — Seller + Buyer' : '';
                const marker = L.circleMarker([s.la, s.ln], {
                    radius: r,
                    color: isEV ? '#00ffff' : c,
                    fillColor: c,
                    fillOpacity: isEV ? 0.9 : 0.6,
                    weight: isEV ? 2 : 1,
                })
                    .bindPopup(`<div style="font-family:'JetBrains Mono',monospace;font-size:11px"><b>${s.n}</b><br>${s.t}<br>${s.sq.toLocaleString()} sqft · ${s.mwh.toLocaleString()} MWh/yr<br>${s.ti} · ${s.cat}${evLabel}</div>`);

                if (isResidential) {
                    residentialLayer.addLayer(marker);
                } else {
                    marker.addTo(mapD91);
                }
                // Index by partial name for flash matching
                d91SellerIndex[s.n.substring(0, 10)] = { la: s.la, ln: s.ln };"""

if OLD_RESIDENTIAL not in src:
    print("  ❌ Marker block not found")
    exit(1)

src = src.replace(OLD_RESIDENTIAL, NEW_RESIDENTIAL, 1)

# Add zoom listener to show/hide residential layer
OLD_ZOOM_END = """            $('d91-seller-count').textContent = data.sellers.length.toLocaleString();
            $('d91-buyer-count').textContent = data.buyers.length.toLocaleString();
            $('d91-loading').classList.add('hidden');"""

NEW_ZOOM_END = """            $('d91-seller-count').textContent = data.sellers.length.toLocaleString();
            $('d91-buyer-count').textContent = data.buyers.length.toLocaleString();
            $('d91-loading').classList.add('hidden');

            // Show/hide residential layer based on zoom
            function updateResidentialVisibility() {
                const z = mapD91.getZoom();
                if (z >= RESIDENTIAL_ZOOM) {
                    if (!mapD91.hasLayer(residentialLayer)) mapD91.addLayer(residentialLayer);
                } else {
                    if (mapD91.hasLayer(residentialLayer)) mapD91.removeLayer(residentialLayer);
                }
            }
            mapD91.on('zoomend', updateResidentialVisibility);
            updateResidentialVisibility(); // Apply on load"""

if OLD_ZOOM_END not in src:
    print("  ❌ Zoom end block not found")
    exit(1)

src = src.replace(OLD_ZOOM_END, NEW_ZOOM_END, 1)
DASH.write_text(src, encoding="utf-8")
print("  ✅ Residential/EV markers now hidden below zoom level 14")
print("     Zoom in to a neighborhood to see the cyan EV dots appear")
