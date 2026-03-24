// ──────────────────────────────────────────────────────────
// TINY-HUB — Chainlink Functions: MISO LMP Price Feed
//
// This JavaScript runs on the Chainlink DON (decentralized
// oracle network). It fetches the real-time 5-minute LMP
// from MISO for the Ameren zone (District 91 / Peoria).
//
// Returns: LMP price scaled by 100000
//          e.g., $0.045/kWh → 4500
//
// Used by: TinyHubPriceOracle.sol → requestMisoPrice()
// ──────────────────────────────────────────────────────────

// MISO publishes 5-minute LMP data via their public API
// gridstatus.io provides a clean REST wrapper
const url = "https://api.gridstatus.io/v1/miso/lmp/latest?location_type=hub";

const response = await Functions.makeHttpRequest({
  url: url,
  method: "GET",
  headers: { "Content-Type": "application/json" },
  timeout: 9000,
});

if (response.error) {
  throw Error("MISO API request failed");
}

const data = response.data;

// Find the Illinois hub / Ameren zone price
// MISO reports LMP in $/MWh — convert to $/kWh for our scale
let lmpMwh = 0;

if (data && data.data && data.data.length > 0) {
  // Look for Illinois Hub or use the first available hub price
  const ilHub = data.data.find(
    (d) => d.location && d.location.toLowerCase().includes("illinois")
  );

  if (ilHub) {
    lmpMwh = ilHub.lmp || ilHub.price || 0;
  } else {
    // Fallback: use first hub price
    lmpMwh = data.data[0].lmp || data.data[0].price || 0;
  }
}

// Convert: $/MWh → $/kWh → scaled by 100000
// Example: $45/MWh = $0.045/kWh = 4500 (scaled)
const lmpKwh = lmpMwh / 1000; // $/MWh to $/kWh
const scaled = Math.round(lmpKwh * 100000);

// Return as uint256-encoded bytes
return Functions.encodeUint256(scaled > 0 ? scaled : 0);
