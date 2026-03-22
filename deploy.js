const hre = require("hardhat");
const fs = require("fs");

async function main() {
  console.log("");
  console.log("  ╔══════════════════════════════════════════════════════════════╗");
  console.log("  ║     TINY-HUB-NETWORK — Deploying All Contracts              ║");
  console.log("  ╠══════════════════════════════════════════════════════════════╣");
  console.log(`  ║  Network: ${hre.network.name.padEnd(47)} ║`);
  console.log("  ╚══════════════════════════════════════════════════════════════╝");
  console.log("");

  const [deployer] = await hre.ethers.getSigners();
  console.log(`  Deployer:  ${deployer.address}`);

  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`  Balance:   ${hre.ethers.formatEther(balance)} ETH`);
  console.log("");

  // ── Deploy TinyHubMarket ──────────────────────────────────
  console.log("  Deploying TinyHubMarket...");
  const marketArtifact = JSON.parse(fs.readFileSync("TinyHubMarket.json", "utf8"));
  const marketFactory = new hre.ethers.ContractFactory(marketArtifact.abi, marketArtifact.bytecode, deployer);
  const market = await marketFactory.deploy();
  await market.waitForDeployment();
  const marketAddress = await market.getAddress();
  console.log(`  ✅ TinyHubMarket:  ${marketAddress}`);

  // ── Deploy TinyHubToken ───────────────────────────────────
  console.log("  Deploying TinyHubToken...");
  const tokenAbi = JSON.parse(fs.readFileSync("build/contracts_TinyHubToken_sol_TinyHubToken.abi", "utf8"));
  const tokenBin = "0x" + fs.readFileSync("build/contracts_TinyHubToken_sol_TinyHubToken.bin", "utf8").trim();
  const tokenFactory = new hre.ethers.ContractFactory(tokenAbi, tokenBin, deployer);
  const token = await tokenFactory.deploy();
  await token.waitForDeployment();
  const tokenAddress = await token.getAddress();
  console.log(`  ✅ TinyHubToken:   ${tokenAddress}`);

  // Verify
  const tokenName = await token.name();
  const tokenSymbol = await token.symbol();
  const bridge = await token.bridge();
  console.log("");
  console.log(`  Token: ${tokenName} (${tokenSymbol})`);
  console.log(`  Bridge (minter): ${bridge}`);

  const fee = await market.PLATFORM_FEE();
  console.log(`  Market fee: ${hre.ethers.formatEther(fee)} ETH`);
  console.log("");

  // Save deployment info
  const deployment = {
    network: hre.network.name,
    chainId: hre.network.config.chainId || "local",
    deployer: deployer.address,
    deployedAt: new Date().toISOString(),
    contracts: {
      TinyHubMarket: {
        address: marketAddress,
        platformFee: hre.ethers.formatEther(fee),
      },
      TinyHubToken: {
        address: tokenAddress,
        name: tokenName,
        symbol: tokenSymbol,
        bridge: bridge,
      },
    },
  };

  fs.writeFileSync("deployment.json", JSON.stringify(deployment, null, 2));
  console.log("  📄 Saved to deployment.json");
  console.log("");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
