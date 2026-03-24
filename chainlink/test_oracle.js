const hre = require("hardhat");
const fs = require("fs");

/**
 * Test the TinyHubPriceOracle by requesting a MISO LMP price
 *
 * Usage:
 *   export DEPLOYER_PRIVATE_KEY=$(gcloud secrets versions access latest --secret=DEPLOYER_PRIVATE_KEY)
 *   npx hardhat run chainlink/test_oracle.js --network arbitrumSepolia
 */
async function main() {
  const depFile = hre.network.name === "localhost" ? "deployment.json" : "deployment_l2.json";
  const dep = JSON.parse(fs.readFileSync(depFile, "utf8"));
  const oracleAddress = dep.TinyHubPriceOracle;

  if (!oracleAddress) {
    console.log("  ❌ TinyHubPriceOracle not found in deployment file");
    console.log("     Run deploy_oracle.js first");
    process.exit(1);
  }

  console.log(`  Oracle: ${oracleAddress}`);

  const oracle = await hre.ethers.getContractAt("TinyHubPriceOracle", oracleAddress);

  // Check current prices
  const [d91Price, d91Time] = await oracle.getPrice("IL_D91");
  const [d63Price, d63Time] = await oracle.getPrice("McHenry_D63");

  console.log("");
  console.log("  Current oracle prices:");
  console.log(`    IL_D91:      ${d91Price.toString()} (${d91Price > 0 ? "$" + (Number(d91Price) / 100000).toFixed(5) + "/kWh" : "not set"})`);
  console.log(`    McHenry_D63: ${d63Price.toString()} (${d63Price > 0 ? "$" + (Number(d63Price) / 100000).toFixed(5) + "/kWh" : "not set"})`);
  console.log("");

  // Request MISO price
  console.log("  Requesting MISO LMP (IL_D91)...");
  try {
    const tx = await oracle.requestMisoPrice();
    const receipt = await tx.wait();
    console.log(`  ✅ Request sent — tx: ${receipt.hash}`);
    console.log("     Waiting for Chainlink DON to fulfill (~30-60 seconds)...");

    // Poll for the result
    for (let i = 0; i < 12; i++) {
      await new Promise((r) => setTimeout(r, 10000)); // Wait 10s
      const [price, time] = await oracle.getPrice("IL_D91");
      if (price > 0n && time > d91Time) {
        console.log(`  ✅ MISO LMP received: ${price.toString()} = $${(Number(price) / 100000).toFixed(5)}/kWh`);

        // Test price verification
        const [valid, oracleP] = await oracle.verifyPrice("IL_D91", price);
        console.log(`  ✅ Verify (same price):    valid=${valid}`);

        // Test with a wildly different price
        const [valid2, oracleP2] = await oracle.verifyPrice("IL_D91", price * 3n);
        console.log(`  ✅ Verify (3x price):      valid=${valid2} (should be false)`);

        return;
      }
      console.log(`     ... polling (${(i + 1) * 10}s)`);
    }
    console.log("  ⚠️  No response after 2 minutes — check subscription funding");
  } catch (e) {
    console.log(`  ❌ Error: ${e.message}`);
    if (e.message.includes("insufficient")) {
      console.log("     Fund your Chainlink subscription with more LINK");
    }
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
