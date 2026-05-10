const hre = require("hardhat");
const fs = require("fs");

async function main() {
  const abi = JSON.parse(fs.readFileSync("./build/contracts_TinyHubMarketV2_sol_TinyHubMarketV2.abi", "utf8"));
  const bin = fs.readFileSync("./build/contracts_TinyHubMarketV2_sol_TinyHubMarketV2.bin", "utf8");

  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying TinyHubMarketV2 with:", deployer.address);

  const factory = new hre.ethers.ContractFactory(abi, bin, deployer);
  const contract = await factory.deploy();
  await contract.waitForDeployment();

  const addr = await contract.getAddress();
  console.log("TinyHubMarketV2 deployed at:", addr);

  // Save to deployment file
  let dep = {};
  if (fs.existsSync("deployment.json")) {
    dep = JSON.parse(fs.readFileSync("deployment.json", "utf8"));
  }
  dep.TinyHubMarketV2 = addr;
  fs.writeFileSync("deployment.json", JSON.stringify(dep, null, 2));
  console.log("Saved to deployment.json");
}

main().catch(console.error);
