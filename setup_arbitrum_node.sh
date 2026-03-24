#!/bin/bash
# ──────────────────────────────────────────────────────────
# TINY-HUB-NETWORK — Arbitrum Nitro Node on GCP
#
# Provisions a dedicated Arbitrum full node on a GCP VM
# for production mainnet use. Replaces the public RPC.
#
# Run this when you're ready for Arbitrum One (mainnet).
# For Sepolia testnet, the public RPC is fine.
#
# Usage:
#   chmod +x setup_arbitrum_node.sh
#   ./setup_arbitrum_node.sh
#
# After setup, your private RPC endpoint will be:
#   http://<INTERNAL_IP>:8547  (JSON-RPC)
#   ws://<INTERNAL_IP>:8548    (WebSocket)
#
# Store in Secret Manager:
#   gcloud secrets create ARBITRUM_RPC --data-file=- <<< "http://<IP>:8547"
# ──────────────────────────────────────────────────────────

set -e

PROJECT_ID="tiny-hub-network"
ZONE="us-central1-a"
NETWORK="default"
NODE_NAME="tinyhub-arbitrum-node"
MACHINE_TYPE="e2-standard-8"     # 8 vCPU, 32 GB RAM
DISK_SIZE="500"                   # GB — Arbitrum full node needs ~400GB+

GREEN="\033[0;32m"
AMBER="\033[0;33m"
NC="\033[0m"

echo ""
echo -e "  ${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "  ${GREEN}║  TINY-HUB — Arbitrum Nitro Node Provisioning     ║${NC}"
echo -e "  ${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Create firewall rule for Arbitrum P2P ────────────────
echo -e "  ${GREEN}[1/4] Creating firewall rules...${NC}"

gcloud compute firewall-rules create allow-arbitrum-p2p \
  --project=$PROJECT_ID \
  --network=$NETWORK \
  --allow=tcp:8547,tcp:8548,tcp:4011,udp:4011 \
  --source-ranges="10.0.0.0/8" \
  --target-tags=arbitrum-node \
  --description="Arbitrum Nitro RPC + P2P (internal only)" \
  2>/dev/null && echo "    ✅ Firewall rule created" || echo "    ⚠️  Rule may already exist"

echo ""

# ── 2. Create the VM ────────────────────────────────────────
echo -e "  ${GREEN}[2/4] Creating VM: ${NODE_NAME}...${NC}"

gcloud compute instances create $NODE_NAME \
  --project=$PROJECT_ID \
  --zone=$ZONE \
  --machine-type=$MACHINE_TYPE \
  --network=$NETWORK \
  --tags=arbitrum-node \
  --boot-disk-size=${DISK_SIZE}GB \
  --boot-disk-type=pd-ssd \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --scopes=cloud-platform \
  --metadata=startup-script='#!/bin/bash
set -e
apt-get update && apt-get install -y docker.io docker-compose-v2
systemctl enable docker && systemctl start docker

# Create data directory
mkdir -p /data/arbitrum

# Pull and run Arbitrum Nitro node
docker run -d \
  --name nitro \
  --restart=always \
  -v /data/arbitrum:/home/user/.arbitrum \
  -p 8547:8547 \
  -p 8548:8548 \
  -p 4011:4011/tcp \
  -p 4011:4011/udp \
  offchainlabs/nitro-node:latest \
  --parent-chain.connection.url=https://ethereum-rpc.publicnode.com \
  --chain.id=42161 \
  --http.api=net,web3,eth,debug \
  --http.corsdomain=* \
  --http.addr=0.0.0.0 \
  --http.port=8547 \
  --http.vhosts=* \
  --ws.addr=0.0.0.0 \
  --ws.port=8548 \
  --ws.origins=* \
  --execution.caching.archive

echo "Arbitrum Nitro node started. Syncing..."
' 2>/dev/null

echo "    ✅ VM created — Nitro node will start syncing automatically"
echo ""

# ── 3. Get the internal IP ──────────────────────────────────
echo -e "  ${GREEN}[3/4] Getting node IP...${NC}"

sleep 5
INTERNAL_IP=$(gcloud compute instances describe $NODE_NAME \
  --project=$PROJECT_ID \
  --zone=$ZONE \
  --format='get(networkInterfaces[0].networkIP)' 2>/dev/null)

echo "    Internal IP: $INTERNAL_IP"
echo "    RPC:         http://${INTERNAL_IP}:8547"
echo "    WebSocket:   ws://${INTERNAL_IP}:8548"
echo ""

# ── 4. Store RPC URL in Secret Manager ──────────────────────
echo -e "  ${GREEN}[4/4] Storing RPC URL in Secret Manager...${NC}"

echo -n "http://${INTERNAL_IP}:8547" | gcloud secrets create ARBITRUM_MAINNET_RPC \
  --project=$PROJECT_ID \
  --data-file=- 2>/dev/null && \
  echo "    ✅ ARBITRUM_MAINNET_RPC stored" || \
  echo "    ⚠️  Secret may already exist — update with:"
  echo "    echo -n 'http://${INTERNAL_IP}:8547' | gcloud secrets versions add ARBITRUM_MAINNET_RPC --data-file=-"

echo ""
echo "  ┌── ARBITRUM NODE SUMMARY ─────────────────────────"
echo "  │ VM:         $NODE_NAME ($MACHINE_TYPE)"
echo "  │ Zone:       $ZONE"
echo "  │ Disk:       ${DISK_SIZE}GB SSD"
echo "  │ RPC:        http://${INTERNAL_IP}:8547"
echo "  │ WebSocket:  ws://${INTERNAL_IP}:8548"
echo "  │ Status:     Syncing (may take 12-24 hours)"
echo "  │"
echo "  │ Check sync progress:"
echo "  │   gcloud compute ssh $NODE_NAME --zone=$ZONE -- docker logs nitro --tail 20"
echo "  │"
echo "  │ Check block height:"
echo "  │   curl -s http://${INTERNAL_IP}:8547 -X POST -H 'Content-Type: application/json' \\"
echo "  │     -d '{\"jsonrpc\":\"2.0\",\"method\":\"eth_blockNumber\",\"params\":[],\"id\":1}'"
echo "  └──────────────────────────────────────────────────"
echo ""
echo "  Once synced, update hardhat.config.js:"
echo "    arbitrumOne: {"
echo "      url: \"http://${INTERNAL_IP}:8547\","
echo "      chainId: 42161,"
echo "    }"
echo ""
