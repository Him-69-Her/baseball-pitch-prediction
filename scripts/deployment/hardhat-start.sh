#!/bin/sh
set -e

echo "  ╔═══════════════════════════════════════════════════════════╗"
echo "  ║  TINY-HUB — Hardhat Blockchain Node (Chain 31337)        ║"
echo "  ╚═══════════════════════════════════════════════════════════╝"

# Start Hardhat node in background
npx hardhat node --hostname 0.0.0.0 &
HARDHAT_PID=$!

# Wait for RPC to be ready
echo "  Waiting for RPC..."
TRIES=0
while ! node -e "fetch('http://localhost:8545',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',method:'eth_blockNumber',params:[],id:1})}).then(r=>r.json()).then(d=>{if(d.result)process.exit(0);else process.exit(1)}).catch(()=>process.exit(1))" 2>/dev/null && [ $TRIES -lt 30 ]; do
    sleep 1
    TRIES=$((TRIES + 1))
done

echo "  ✅ Hardhat node ready"

# Deploy contracts (deploy.js deploys Market + Token)
echo "  Deploying smart contracts..."
if [ -f deploy.js ] && [ -f TinyHubMarket.json ]; then
    npx hardhat run deploy.js --network localhost || echo "  ⚠️  deploy.js failed, trying deploy_v2.js..."
fi

# Fallback to deploy_v2.js if deploy.js didn't create deployment.json
if [ ! -f deployment.json ] && [ -f deploy_v2.js ]; then
    echo "  Trying deploy_v2.js..."
    npx hardhat run deploy_v2.js --network localhost || echo "  ❌ deploy_v2.js also failed"
fi

# Copy deployment.json to shared volume
if [ -f deployment.json ]; then
    cp deployment.json /shared/deployment.json
    echo "  ✅ deployment.json → /shared/"
    cat deployment.json
else
    echo "  ❌ No deployment.json created"
fi

# Keep node running
wait $HARDHAT_PID
