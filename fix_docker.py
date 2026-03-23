#!/usr/bin/env python3
"""
TINY-HUB — Clean Docker Fix
Fixes all container networking and deployment issues:

1. Hardhat Dockerfile: adds TinyHubMarket.json + build/ + uses deploy.js
2. hardhat-start.sh: uses deploy.js (deploys Market + Token)
3. d91_settler.py: uses RPC_URL env var instead of hardcoded localhost
4. bridge.py: same fix
5. chain_api.py: handles both deployment.json formats
6. docker-entrypoint.sh: waits for deployment.json properly

Run from project root:
    python3 fix_docker.py
"""

from pathlib import Path

# ══════════════════════════════════════════════════════════════
# FIX 1: Dockerfile.hardhat — include all needed files
# ══════════════════════════════════════════════════════════════
DHF = Path("Dockerfile.hardhat")
DHF.write_text('''FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY hardhat.config.js ./
COPY contracts/ ./contracts/
COPY deploy.js deploy_v2.js ./
COPY build/ ./build/
COPY TinyHubMarket.json ./TinyHubMarket.json

EXPOSE 8545
VOLUME /shared

COPY hardhat-start.sh .
RUN chmod +x hardhat-start.sh

CMD ["./hardhat-start.sh"]
''', encoding="utf-8")
print("  ✅ Dockerfile.hardhat rebuilt")


# ══════════════════════════════════════════════════════════════
# FIX 2: hardhat-start.sh — use deploy.js (deploys both contracts)
# ══════════════════════════════════════════════════════════════
HSH = Path("hardhat-start.sh")
HSH.write_text('''#!/bin/sh
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
''', encoding="utf-8")
print("  ✅ hardhat-start.sh rebuilt")


# ══════════════════════════════════════════════════════════════
# FIX 3: d91_settler.py — use RPC_URL env var
# ══════════════════════════════════════════════════════════════
SETTLER = Path("d91_settler.py")
if SETTLER.exists():
    src = SETTLER.read_text(encoding="utf-8")
    
    OLD_RPC = 'RPC_URL = "http://127.0.0.1:8545"'
    NEW_RPC = 'RPC_URL = os.environ.get("RPC_URL", "http://127.0.0.1:8545")'
    
    if OLD_RPC in src and "os.environ" not in src.split("RPC_URL")[1][:50]:
        src = src.replace(OLD_RPC, NEW_RPC, 1)
        SETTLER.write_text(src, encoding="utf-8")
        print("  ✅ d91_settler.py: RPC_URL reads from env var")
    else:
        print("  ⏭️  d91_settler.py: already using env var or different format")


# ══════════════════════════════════════════════════════════════
# FIX 4: bridge.py — use RPC_URL env var
# ══════════════════════════════════════════════════════════════
BRIDGE_FILES = ["bridge.py", "d91_bridge.py"]
for bf in BRIDGE_FILES:
    BP = Path(bf)
    if BP.exists():
        src = BP.read_text(encoding="utf-8")
        
        OLD_RPC = 'RPC_URL = "http://127.0.0.1:8545"'
        NEW_RPC = 'RPC_URL = os.environ.get("RPC_URL", "http://127.0.0.1:8545")'
        
        if OLD_RPC in src:
            # Make sure os is imported
            if "import os" not in src:
                src = "import os\n" + src
            src = src.replace(OLD_RPC, NEW_RPC, 1)
            BP.write_text(src, encoding="utf-8")
            print(f"  ✅ {bf}: RPC_URL reads from env var")
        else:
            print(f"  ⏭️  {bf}: already patched or different format")


# ══════════════════════════════════════════════════════════════
# FIX 5: chain_api.py — handle both deployment.json formats
# ══════════════════════════════════════════════════════════════
CHAIN = Path("chain_api.py")
CHAIN.write_text('''"""Chain status API — connects to Hardhat node for on-chain stats."""
import os
import json
from flask import jsonify

RPC_URL = os.environ.get("RPC_URL", "http://hardhat:8545")

def register_chain_routes(app):
    @app.route("/api/chain")
    def api_chain():
        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 3}))
            if not w3.is_connected():
                return jsonify({"connected": False, "error": "Cannot reach Hardhat"})

            result = {
                "connected": True,
                "chain_id": w3.eth.chain_id,
                "block": w3.eth.block_number,
            }

            # Find deployment.json — check shared volume first, then local
            dep = None
            for path in ["/shared/deployment.json", "/app/deployment.json", "deployment.json"]:
                if os.path.exists(path):
                    with open(path) as f:
                        dep = json.load(f)
                    break

            if not dep:
                result["error"] = "deployment.json not found"
                return jsonify(result)

            # Handle both formats:
            # deploy.js format:    dep["contracts"]["TinyHubMarket"]["address"]
            # deploy_v2.js format: dep["TinyHubMarketV2"]
            contract_addr = None
            token_addr = None

            if "contracts" in dep:
                # deploy.js format
                if "TinyHubMarket" in dep["contracts"]:
                    contract_addr = dep["contracts"]["TinyHubMarket"]["address"]
                if "TinyHubToken" in dep["contracts"]:
                    token_addr = dep["contracts"]["TinyHubToken"]["address"]
            else:
                # deploy_v2.js format
                contract_addr = dep.get("TinyHubMarketV2")
                token_addr = dep.get("TinyHubToken")

            if contract_addr:
                abi = [{"inputs":[],"name":"tradeCount","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"}]
                try:
                    c = w3.eth.contract(address=contract_addr, abi=abi)
                    result["trade_count"] = c.functions.tradeCount().call()
                    result["contract"] = contract_addr
                except Exception as e:
                    result["contract_error"] = str(e)[:80]

            if token_addr:
                tabi = [
                    {"inputs":[],"name":"totalSupply","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
                    {"inputs":[],"name":"symbol","outputs":[{"type":"string"}],"stateMutability":"view","type":"function"},
                ]
                try:
                    t = w3.eth.contract(address=token_addr, abi=tabi)
                    raw = t.functions.totalSupply().call()
                    result["token_supply"] = float(w3.from_wei(raw, "ether"))
                    result["token_symbol"] = t.functions.symbol().call()
                    result["token"] = token_addr
                except Exception as e:
                    result["token_error"] = str(e)[:80]

            return jsonify(result)
        except Exception as e:
            return jsonify({"connected": False, "error": str(e)[:100]})
''', encoding="utf-8")
print("  ✅ chain_api.py rebuilt (handles both deploy formats)")


# ══════════════════════════════════════════════════════════════
# FIX 6: docker-entrypoint.sh — better deployment.json handling
# ══════════════════════════════════════════════════════════════
DE = Path("docker-entrypoint.sh")
DE.write_text('''#!/bin/sh
# Wait for Hardhat to deploy contracts
echo "  Waiting for deployment.json..."
TRIES=0
while [ ! -f /shared/deployment.json ] && [ $TRIES -lt 120 ]; do
    sleep 2
    TRIES=$((TRIES + 1))
done

if [ -f /shared/deployment.json ]; then
    cp /shared/deployment.json /app/deployment.json
    echo "  ✅ deployment.json loaded from shared volume"
    cat /app/deployment.json
elif [ -f /app/deployment.json ]; then
    echo "  ✅ deployment.json exists locally"
else
    echo "  ⚠️  deployment.json not found after 240s — settler may fail"
fi

exec "$@"
''', encoding="utf-8")
print("  ✅ docker-entrypoint.sh rebuilt (waits up to 240s)")


# ══════════════════════════════════════════════════════════════
# FIX 7: Check TinyHubMarket.json exists
# ══════════════════════════════════════════════════════════════
TMJ = Path("TinyHubMarket.json")
if TMJ.exists():
    print("  ✅ TinyHubMarket.json exists")
else:
    print("  ⚠️  TinyHubMarket.json NOT FOUND — deploy.js will fail!")
    print("     You need this file for full contract deployment.")
    print("     Falling back to deploy_v2.js (MarketV2 only, no token)")


# ══════════════════════════════════════════════════════════════
# FIX 8: .dockerignore — make sure build/ is NOT ignored
# ══════════════════════════════════════════════════════════════
DI = Path(".dockerignore")
if DI.exists():
    di_src = DI.read_text(encoding="utf-8")
    lines = [l for l in di_src.strip().split("\n") if l.strip() not in ("build/", "build")]
    DI.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  ✅ .dockerignore: build/ not excluded")


print()
print("  ══════════════════════════════════════════════════")
print("  ✅ All Docker fixes applied. Now run:")
print()
print("     sudo docker-compose down")
print("     sudo docker-compose up -d --build")
print()
print("  Then verify:")
print("     curl http://localhost:5000/api/chain")
print("  ══════════════════════════════════════════════════")
print()
