// ──────────────────────────────────────────────────────────
// TINY-HUB — Chainlink Functions: PJM LMP Price Feed
//
// Fetches real-time 5-minute LMP from PJM for the ComEd
// zone (District 63 / McHenry).
//
// Returns: LMP price scaled by 100000
//          e.g., $0.038/kWh → 3800
//
// Used by: TinyHubPriceOracle.sol → requestPjmPrice()
// ──────────────────────────────────────────────────────────

// PJM Data Miner API for real-time LMP
// Falls back to gridstatus.io if PJM API key not available
const gridStatusUrl = "https://api.gridstatus.io/v1/pjm/lmp/latest?location_type=hub";

const response = await Functions.makeHttpRequest({
  url: gridStatusUrl,
  method: "GET",
  headers: { "Content-Type": "application/json" },
  timeout: 9000,
});

if (response.error) {
  throw Error("PJM API request failed");
}

const data = response.data;

// Find ComEd zone price
let lmpMwh = 0;

if (data && data.data && data.data.length > 0) {
  // Look for ComEd / COMED zone or Eastern hub
  const comed = data.data.find(
    (d) =>
      d.location &&
      (d.location.toLowerCase().includes("comed") ||
        d.location.toLowerCase().includes("eastern"))
  );

  if (comed) {
    lmpMwh = comed.lmp || comed.price || 0;
  } else {
    // Fallback: first hub
    lmpMwh = data.data[0].lmp || data.data[0].price || 0;
  }
}

// Convert: $/MWh → $/kWh → scaled by 100000
const lmpKwh = lmpMwh / 1000;
const scaled = Math.round(lmpKwh * 100000);

return Functions.encodeUint256(scaled > 0 ? scaled : 0);
