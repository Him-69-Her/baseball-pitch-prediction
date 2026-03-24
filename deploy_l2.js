const hre = require("hardhat");
const fs = require("fs");

/**
 * TINY-HUB-NETWORK — L2 Arbitrum Sepolia Deployment
 *
 * Deploys:
 *   1. TinyHubMarketV3 (on-chain idempotency + access control)
 *   2. TinyHubTokenL2   (multi-minter THN token)
 *
 * Then wires the settler wallet as authorized on both contracts.
 *
 * Usage:
 *   # Set env vars first:
 *   export DEPLOYER_PRIVATE_KEY="0x..."
 *   export SETTLER_ADDRESS="0x..."   # Optional — defaults to deployer
 *
 *   # Deploy to Arbitrum Sepolia:
 *   npx hardhat run deploy_l2.js --network arbitrumSepolia
 *
 *   # Or deploy to local Hardhat for testing:
 *   npx hardhat run deploy_l2.js --network localhost
 */
async function main() {
  console.log("");
  console.log("  ╔══════════════════════════════════════════════════════════════╗");
  console.log("  ║     TINY-HUB-NETWORK — L2 Deployment                        ║");
  console.log("  ╠══════════════════════════════════════════════════════════════╣");
  console.log(`  ║  Network:  ${hre.network.name.padEnd(46)} ║`);
  console.log(`  ║  Chain ID: ${(hre.network.config.chainId || "local").toString().padEnd(46)} ║`);
  console.log("  ╚══════════════════════════════════════════════════════════════╝");
  console.log("");

  const [deployer] = await hre.ethers.getSigners();
  console.log(`  Deployer:  ${deployer.address}`);

  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`  Balance:   ${hre.ethers.formatEther(balance)} ETH`);

  if (parseFloat(hre.ethers.formatEther(balance)) < 0.01) {
    console.log("  ⚠️  Low balance — get test ETH from https://faucet.quicknode.com/arbitrum/sepolia");
  }
  console.log("");

  // ── Deploy TinyHubMarketV3 ────────────────────────────────
  console.log("  Deploying TinyHubMarketV3...");
  const MarketV3 = await hre.ethers.getContractFactory("TinyHubMarketV3");
  const market = await MarketV3.deploy();
  await market.waitForDeployment();
  const marketAddress = await market.getAddress();
  console.log(`  ✅ TinyHubMarketV3:  ${marketAddress}`);

  // ── Deploy TinyHubTokenL2 ─────────────────────────────────
  console.log("  Deploying TinyHubTokenL2...");
  const TokenL2 = await hre.ethers.getContractFactory("TinyHubTokenL2");
  const token = await TokenL2.deploy();
  await token.waitForDeployment();
  const tokenAddress = await token.getAddress();
  console.log(`  ✅ TinyHubTokenL2:   ${tokenAddress}`);
  console.log("");

  // ── Wire settler wallet ───────────────────────────────────
  const settlerAddress = process.env.SETTLER_ADDRESS || deployer.address;
  console.log(`  Settler wallet: ${settlerAddress}`);

  if (settlerAddress !== deployer.address) {
    // Authorize the settler on MarketV3
    const txSettler = await market.setSettler(settlerAddress, true);
    await txSettler.wait();
    console.log(`  ✅ MarketV3: settler authorized`);

    // Authorize the settler as minter on TokenL2
    const txMinter = await token.setMinter(settlerAddress, true);
    await txMinter.wait();
    console.log(`  ✅ TokenL2:  minter authorized`);
  } else {
    console.log(`  ✅ Deployer is settler — already authorized`);
  }

  // ── Verify contract state ─────────────────────────────────
  const tokenName = await token.name();
  const tokenSymbol = await token.symbol();
  const fee = await market.PLATFORM_FEE();
  const isSettler = await market.settlers(settlerAddress);
  const isMinter = await token.minters(settlerAddress);

  console.log("");
  console.log(`  Token:     ${tokenName} (${tokenSymbol})`);
  console.log(`  Fee:       ${hre.ethers.formatEther(fee)} ETH`);
  console.log(`  Settler:   ${isSettler ? "✅" : "❌"} authorized on MarketV3`);
  console.log(`  Minter:    ${isMinter ? "✅" : "❌"} authorized on TokenL2`);
  console.log("");

  // ── Save deployment info ──────────────────────────────────
  const deployment = {
    network: hre.network.name,
    chainId: hre.network.config.chainId || "local",
    deployer: deployer.address,
    settler: settlerAddress,
    deployedAt: new Date().toISOString(),
    contracts: {
      TinyHubMarketV3: {
        address: marketAddress,
        platformFee: hre.ethers.formatEther(fee),
        version: "v3",
      },
      TinyHubTokenL2: {
        address: tokenAddress,
        name: tokenName,
        symbol: tokenSymbol,
        version: "L2",
      },
    },
    // Backward compat — settler reads these top-level keys
    TinyHubMarketV2: marketAddress,   // settler looks for this key
    TinyHubToken: tokenAddress,
  };

  const filename = hre.network.name === "hardhat" || hre.network.name === "localhost"
    ? "deployment.json"
    : "deployment_l2.json";

  fs.writeFileSync(filename, JSON.stringify(deployment, null, 2));
  console.log(`  📄 Saved to ${filename}`);
  console.log("");

  // ── Verify on Arbiscan (if on L2) ────────────────────────
  if (hre.network.name === "arbitrumSepolia") {
    console.log("  To verify contracts on Arbiscan:");
    console.log(`    npx hardhat verify --network arbitrumSepolia ${marketAddress}`);
    console.log(`    npx hardhat verify --network arbitrumSepolia ${tokenAddress}`);
    console.log("");
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
