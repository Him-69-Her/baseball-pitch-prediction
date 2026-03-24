const hre = require("hardhat");
const fs = require("fs");

/**
 * TINY-HUB-NETWORK — Deploy Chainlink Price Oracle
 *
 * Deploys TinyHubPriceOracle on Arbitrum Sepolia,
 * wired to the Chainlink Functions router.
 *
 * Prerequisites:
 *   1. MarketV3 + TokenL2 already deployed (deployment_l2.json exists)
 *   2. Chainlink Functions subscription created and funded with LINK
 *   3. SUBSCRIPTION_ID env var set
 *
 * Usage:
 *   export DEPLOYER_PRIVATE_KEY=$(gcloud secrets versions access latest --secret=DEPLOYER_PRIVATE_KEY)
 *   export SUBSCRIPTION_ID=<your-sub-id>
 *   npx hardhat run deploy_oracle.js --network arbitrumSepolia
 */

// Chainlink Functions addresses for Arbitrum Sepolia
const CHAINLINK_CONFIG = {
  arbitrumSepolia: {
    router: "0x234a5fb5Bd614a7AA2FfAB244D603abFA0Ac5C5C",
    donId: "fun-arbitrum-sepolia-1",
    linkToken: "0xb1D4538B4571d411F07960EF2838Ce337FE1E80E",
  },
  arbitrumOne: {
    router: "0x97083e831f8f0638855e2a515c90edcf158df238",
    donId: "fun-arbitrum-mainnet-1",
    linkToken: "0xf97f4df75117a78c1A5a0DBb814Af92458539FB4",
  },
};

async function main() {
  const network = hre.network.name;
  const config = CHAINLINK_CONFIG[network];

  if (!config) {
    console.log(`  ❌ No Chainlink config for network: ${network}`);
    console.log(`     Supported: ${Object.keys(CHAINLINK_CONFIG).join(", ")}`);
    process.exit(1);
  }

  const subscriptionId = parseInt(process.env.SUBSCRIPTION_ID || "0");
  if (subscriptionId === 0) {
    console.log("  ❌ Set SUBSCRIPTION_ID env var first");
    console.log("     Create one at: https://functions.chain.link/arbitrum-sepolia");
    process.exit(1);
  }

  // Convert DON ID string to bytes32
  const donIdBytes32 = hre.ethers.encodeBytes32String(config.donId);

  console.log("");
  console.log("  ╔══════════════════════════════════════════════════════════════╗");
  console.log("  ║     TINY-HUB — Chainlink Price Oracle Deploy                ║");
  console.log("  ╠══════════════════════════════════════════════════════════════╣");
  console.log(`  ║  Network:         ${network.padEnd(40)} ║`);
  console.log(`  ║  Router:          ${config.router.slice(0, 20)}...${" ".repeat(17)} ║`);
  console.log(`  ║  DON ID:          ${config.donId.padEnd(40)} ║`);
  console.log(`  ║  Subscription:    ${subscriptionId.toString().padEnd(40)} ║`);
  console.log("  ╚══════════════════════════════════════════════════════════════╝");
  console.log("");

  const [deployer] = await hre.ethers.getSigners();
  console.log(`  Deployer: ${deployer.address}`);
  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`  Balance:  ${hre.ethers.formatEther(balance)} ETH`);
  console.log("");

  // Deploy oracle
  console.log("  Deploying TinyHubPriceOracle...");
  const Oracle = await hre.ethers.getContractFactory("TinyHubPriceOracle");
  const oracle = await Oracle.deploy(
    config.router,
    subscriptionId,
    donIdBytes32
  );
  await oracle.waitForDeployment();
  const oracleAddress = await oracle.getAddress();
  console.log(`  ✅ TinyHubPriceOracle: ${oracleAddress}`);

  // Load and set JavaScript sources
  console.log("");
  console.log("  Loading Chainlink Functions sources...");

  const misoSource = fs.readFileSync("chainlink/miso_lmp_source.js", "utf8");
  const pjmSource = fs.readFileSync("chainlink/pjm_lmp_source.js", "utf8");

  const tx1 = await oracle.setMisoSource(misoSource);
  await tx1.wait();
  console.log("  ✅ MISO source set");

  const tx2 = await oracle.setPjmSource(pjmSource);
  await tx2.wait();
  console.log("  ✅ PJM source set");

  // Update deployment file
  const depFile = network === "localhost" || network === "hardhat"
    ? "deployment.json"
    : "deployment_l2.json";

  let dep = {};
  if (fs.existsSync(depFile)) {
    dep = JSON.parse(fs.readFileSync(depFile, "utf8"));
  }

  dep.TinyHubPriceOracle = oracleAddress;
  if (!dep.contracts) dep.contracts = {};
  dep.contracts.TinyHubPriceOracle = {
    address: oracleAddress,
    router: config.router,
    donId: config.donId,
    subscriptionId: subscriptionId,
    linkToken: config.linkToken,
  };
  dep.chainlink = {
    subscriptionId: subscriptionId,
    donId: config.donId,
    router: config.router,
  };

  fs.writeFileSync(depFile, JSON.stringify(dep, null, 2));
  console.log(`  📄 Updated ${depFile}`);

  console.log("");
  console.log("  ┌── NEXT STEPS ────────────────────────────────────────");
  console.log("  │");
  console.log("  │ 1. Add oracle as consumer to your Chainlink subscription:");
  console.log("  │    Go to: https://functions.chain.link/arbitrum-sepolia");
  console.log(`  │    Add consumer: ${oracleAddress}`);
  console.log("  │");
  console.log("  │ 2. Test a price request:");
  console.log("  │    npx hardhat run chainlink/test_oracle.js --network arbitrumSepolia");
  console.log("  │");
  console.log("  │ 3. Verify on Arbiscan:");
  console.log(`  │    npx hardhat verify --network arbitrumSepolia ${oracleAddress} \\`);
  console.log(`  │      "${config.router}" ${subscriptionId} "${donIdBytes32}"`);
  console.log("  └──────────────────────────────────────────────────────");
  console.log("");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
