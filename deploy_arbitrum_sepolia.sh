#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# TINY-HUB — Task #10: Deploy to Arbitrum Sepolia L2 Testnet
#
# Deploys TinyHubMarket + TinyHubToken to Arbitrum Sepolia.
# Saves deployment addresses to deployment-l2.json.
#
# Prerequisites:
#   1. Deployer wallet with Arbitrum Sepolia ETH
#      Faucet: https://faucet.quicknode.com/arbitrum/sepolia
#   2. Private key stored in Secret Manager:
#      echo -n "0xYOUR_PRIVATE_KEY" | gcloud secrets create DEPLOYER_PRIVATE_KEY \
#          --project=tiny-hub-network --data-file=- --replication-policy=automatic
#   3. npm packages installed (npm ci)
#
# Run from project root:
#   chmod +x deploy_arbitrum_sepolia.sh
#   ./deploy_arbitrum_sepolia.sh
# ═══════════════════════════════════════════════════════════════

set -e

PROJECT_ID="tiny-hub-network"

echo ""
echo "  ╔═══════════════════════════════════════════════════════════╗"
echo "  ║  TINY-HUB — Deploy to Arbitrum Sepolia (L2 Testnet)     ║"
echo "  ╠═══════════════════════════════════════════════════════════╣"
echo "  ║  Chain ID: 421614                                        ║"
echo "  ║  RPC: https://sepolia-rollup.arbitrum.io/rpc             ║"
echo "  ╚═══════════════════════════════════════════════════════════╝"
echo ""

# ── Pull deployer key from Secret Manager ───────────────────
echo "  [1/3] Loading deployer private key from Secret Manager..."
export DEPLOYER_PRIVATE_KEY=$(gcloud secrets versions access latest \
    --secret=DEPLOYER_PRIVATE_KEY \
    --project=$PROJECT_ID 2>/dev/null)

if [ -z "$DEPLOYER_PRIVATE_KEY" ]; then
    echo "  ❌ DEPLOYER_PRIVATE_KEY not found in Secret Manager."
    echo "  Store it:"
    echo '    echo -n "0xYOUR_KEY" | gcloud secrets create DEPLOYER_PRIVATE_KEY \'
    echo "        --project=$PROJECT_ID --data-file=- --replication-policy=automatic"
    exit 1
fi
echo "  ✅ Deployer key loaded"

# ── Optional: Use Blockchain Node Engine RPC if available ───
export ARBITRUM_SEPOLIA_RPC=${ARBITRUM_SEPOLIA_RPC:-"https://sepolia-rollup.arbitrum.io/rpc"}
echo "  RPC: $ARBITRUM_SEPOLIA_RPC"

# ── Compile contracts ───────────────────────────────────────
echo ""
echo "  [2/3] Compiling contracts..."
npx hardhat compile

# ── Deploy ──────────────────────────────────────────────────
echo ""
echo "  [3/3] Deploying to Arbitrum Sepolia..."
npx hardhat run deploy.js --network arbitrumSepolia

# ── Save L2 deployment separately ───────────────────────────
if [ -f deployment.json ]; then
    cp deployment.json deployment-l2.json
    echo ""
    echo "  ✅ L2 deployment saved to deployment-l2.json"
    cat deployment-l2.json

    # Store in Secret Manager for other services
    gcloud secrets create l2-deployment \
        --project=$PROJECT_ID \
        --data-file=deployment-l2.json \
        --replication-policy=automatic 2>/dev/null || \
    gcloud secrets versions add l2-deployment \
        --project=$PROJECT_ID \
        --data-file=deployment-l2.json

    echo "  ✅ Deployment addresses stored in Secret Manager (l2-deployment)"
fi

echo ""
echo "  ╔═══════════════════════════════════════════════════════════╗"
echo "  ║  ✅ TASK #10 COMPLETE — Contracts on Arbitrum Sepolia    ║"
echo "  ╠═══════════════════════════════════════════════════════════╣"
echo "  ║  Verify on Arbiscan:                                     ║"
echo "  ║  https://sepolia.arbiscan.io                             ║"
echo "  ╚═══════════════════════════════════════════════════════════╝"
echo ""
