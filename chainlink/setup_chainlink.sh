#!/bin/bash
# ──────────────────────────────────────────────────────────
# TINY-HUB — Chainlink Functions Setup
#
# Steps:
#   1. Install @chainlink/contracts npm package
#   2. Compile contracts
#   3. Guide you through subscription creation
#   4. Deploy the price oracle
#
# Prerequisites:
#   - Contracts already deployed (deployment_l2.json exists)
#   - 25 LINK on Arbitrum Sepolia (already have from faucet)
#   - DEPLOYER_PRIVATE_KEY in Secret Manager
#
# Usage:
#   chmod +x chainlink/setup_chainlink.sh
#   ./chainlink/setup_chainlink.sh
# ──────────────────────────────────────────────────────────

set -e

GREEN="\033[0;32m"
AMBER="\033[0;33m"
RED="\033[0;31m"
NC="\033[0m"

cd ~/tiny-hub

echo ""
echo -e "  ${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "  ${GREEN}║  TINY-HUB — Chainlink Functions Setup            ║${NC}"
echo -e "  ${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Install Chainlink contracts ──────────────────────────
echo -e "  ${GREEN}[1/4] Installing @chainlink/contracts...${NC}"
npm install @chainlink/contracts --save
echo ""

# ── 2. Compile ──────────────────────────────────────────────
echo -e "  ${GREEN}[2/4] Compiling contracts...${NC}"
npx hardhat compile --force
echo ""

# ── 3. Subscription setup ──────────────────────────────────
echo -e "  ${GREEN}[3/4] Chainlink Functions subscription setup${NC}"
echo ""
echo "  You need to create a Chainlink Functions subscription"
echo "  and fund it with LINK. Do this in the Chainlink UI:"
echo ""
echo -e "  ${AMBER}1. Go to: https://functions.chain.link/arbitrum-sepolia${NC}"
echo -e "  ${AMBER}2. Connect your wallet (0xA6a7...20C6)${NC}"
echo -e "  ${AMBER}3. Click 'Create Subscription'${NC}"
echo -e "  ${AMBER}4. Fund it with 5-10 LINK from your wallet${NC}"
echo -e "  ${AMBER}5. Copy the Subscription ID (a number like 123)${NC}"
echo ""
read -p "  Enter your Subscription ID: " SUB_ID

if [ -z "$SUB_ID" ]; then
    echo -e "  ${RED}❌ No subscription ID provided${NC}"
    exit 1
fi

echo ""
echo "  Subscription ID: $SUB_ID"
echo ""

# ── 4. Deploy oracle ───────────────────────────────────────
echo -e "  ${GREEN}[4/4] Deploying TinyHubPriceOracle...${NC}"

export DEPLOYER_PRIVATE_KEY=$(gcloud secrets versions access latest --secret=DEPLOYER_PRIVATE_KEY)
export SUBSCRIPTION_ID=$SUB_ID

npx hardhat run deploy_oracle.js --network arbitrumSepolia

echo ""
echo "  ┌── FINAL STEP ─────────────────────────────────────"
echo "  │"
echo "  │ Add the oracle contract as a consumer:"
echo "  │"
echo "  │ 1. Go to: https://functions.chain.link/arbitrum-sepolia"
echo "  │ 2. Click your subscription ($SUB_ID)"
echo "  │ 3. Click 'Add Consumer'"
echo "  │ 4. Paste the oracle address from above"
echo "  │ 5. Confirm the transaction"
echo "  │"
echo "  │ Then test:"
echo "  │   npx hardhat run chainlink/test_oracle.js --network arbitrumSepolia"
echo "  └──────────────────────────────────────────────────"
echo ""
