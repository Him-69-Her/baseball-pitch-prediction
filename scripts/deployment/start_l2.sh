#!/bin/bash
# ──────────────────────────────────────────────────────────
# TINY-HUB-NETWORK — Start All Services (L2 Mode)
#
# Usage:
#   ./start_l2.sh          Start all in L2 mode (Arbitrum Sepolia)
#   ./start_l2.sh local    Start all in local mode (Hardhat)
#   ./start_l2.sh stop     Stop all services
#   ./start_l2.sh status   Show running services
# ──────────────────────────────────────────────────────────

GREEN="\033[0;32m"
AMBER="\033[0;33m"
RED="\033[0;31m"
NC="\033[0m"

MODE="${1:-l2}"
cd ~/tiny-hub || exit 1
source venv/bin/activate 2>/dev/null

stop_all() {
    echo -e "  ${AMBER}Stopping all services...${NC}"
    for s in hardhat d91-market d63-market settler bridge dashboard inverter; do
        screen -S "$s" -X quit 2>/dev/null
    done
    echo -e "  ${GREEN}All stopped.${NC}"
}

status() {
    echo ""
    echo -e "  ${GREEN}TINY-HUB SERVICES${NC}"
    echo "  ────────────────────────────────"
    screen -ls 2>/dev/null | grep -E "hardhat|d91|d63|settler|bridge|dashboard|inverter" || echo "  No services running"
    echo ""
}

if [ "$MODE" = "stop" ]; then
    stop_all
    exit 0
fi

if [ "$MODE" = "status" ]; then
    status
    exit 0
fi

# ── Determine network mode ──────────────────────────────────
if [ "$MODE" = "local" ]; then
    export NETWORK=local
    echo -e "  ${GREEN}Starting in LOCAL mode (Hardhat)${NC}"
else
    export NETWORK=l2
    echo -e "  ${GREEN}Starting in L2 mode (Arbitrum Sepolia)${NC}"
fi

echo -e "  ${AMBER}Killing existing sessions...${NC}"
stop_all 2>/dev/null || true

if [ "$NETWORK" = "local" ]; then
    # ── Local mode: start Hardhat + deploy ──────────────────
    echo -e "  ${GREEN}[1/7] Starting Hardhat blockchain...${NC}"
    screen -dmS hardhat bash -c "cd ~/tiny-hub && source venv/bin/activate && npx hardhat node 2>&1"
    sleep 4

    echo -e "  ${GREEN}[2/7] Deploying contracts (local)...${NC}"
    npx hardhat run deploy_l2.js --network localhost 2>&1 | tail -5
    echo ""
else
    # ── L2 mode: no Hardhat needed ──────────────────────────
    echo -e "  ${GREEN}[1/7] Skipping Hardhat (L2 mode)${NC}"
    echo -e "  ${GREEN}[2/7] Using deployment_l2.json${NC}"

    if [ ! -f deployment_l2.json ]; then
        echo -e "  ${RED}❌ deployment_l2.json not found — run deploy_l2.js first${NC}"
        exit 1
    fi
    cat deployment_l2.json | python3 -m json.tool | head -10
    echo ""
fi

echo -e "  ${GREEN}[3/7] Starting D91 marketplace (Peoria/Ameren)...${NC}"
screen -dmS d91-market bash -c "cd ~/tiny-hub && source venv/bin/activate && NETWORK=$NETWORK python3 -u d91_marketplace_live.py 2>&1"
sleep 1

echo -e "  ${GREEN}[4/7] Starting D63 marketplace (McHenry/ComEd)...${NC}"
screen -dmS d63-market bash -c "cd ~/tiny-hub && source venv/bin/activate && NETWORK=$NETWORK python3 -u d63_marketplace_live.py 2>&1"
sleep 1

echo -e "  ${GREEN}[5/7] Starting on-chain settler...${NC}"
screen -dmS settler bash -c "cd ~/tiny-hub && source venv/bin/activate && NETWORK=$NETWORK python3 -u d91_settler_l2.py 2>&1"
sleep 1

echo -e "  ${GREEN}[6/7] Starting cross-district bridge...${NC}"
screen -dmS bridge bash -c "cd ~/tiny-hub && source venv/bin/activate && NETWORK=$NETWORK python3 -u d91_bridge_l2.py 2>&1"
sleep 1

echo -e "  ${GREEN}[7/7] Starting dashboard + inverter API...${NC}"
screen -dmS dashboard bash -c "cd ~/tiny-hub && source venv/bin/activate && python3 -u app.py 2>&1"
screen -dmS inverter bash -c "cd ~/tiny-hub && source venv/bin/activate && python3 -u inverter_api.py 2>&1"
sleep 1

echo ""
echo -e "  ${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "  ${GREEN}║  ALL SERVICES RUNNING                            ║${NC}"
echo -e "  ${GREEN}║  Mode: $(printf '%-41s' "$NETWORK") ║${NC}"
echo -e "  ${GREEN}╠══════════════════════════════════════════════════╣${NC}"
echo -e "  ${GREEN}║  Dashboard:  ${NC}http://35.209.110.230:5000          ${GREEN}║${NC}"
echo -e "  ${GREEN}║  Inverter:   ${NC}http://35.209.110.230:5001          ${GREEN}║${NC}"
if [ "$NETWORK" = "l2" ]; then
echo -e "  ${GREEN}║  Explorer:   ${NC}https://sepolia.arbiscan.io          ${GREEN}║${NC}"
fi
echo -e "  ${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
