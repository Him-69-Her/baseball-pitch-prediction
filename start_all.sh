#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  TINY-HUB NETWORK — Start All Services
#  Usage: ./start_all.sh
#         ./start_all.sh stop     (kill everything)
#         ./start_all.sh status   (check what's running)
# ═══════════════════════════════════════════════════════════════

set -e
cd ~/tiny-hub
source venv/bin/activate

RED='\033[0;31m'
GREEN='\033[0;32m'
AMBER='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "  ${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "  ${CYAN}║     TINY-HUB NETWORK — Service Manager                  ║${NC}"
echo -e "  ${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Stop all ────────────────────────────────────────────────
stop_all() {
    echo -e "  ${AMBER}Stopping all services...${NC}"
    for s in hardhat d91-market d63-market settler bridge dashboard inverter; do
        if screen -list | grep -q "$s"; then
            screen -S "$s" -X quit 2>/dev/null && echo -e "  ${RED}■${NC} $s stopped" || true
        fi
    done
    echo -e "  ${GREEN}✅ All stopped${NC}"
    echo ""
}

# ── Status ──────────────────────────────────────────────────
status() {
    echo -e "  ${CYAN}Service Status:${NC}"
    echo ""
    for s in hardhat d91-market d63-market settler bridge dashboard inverter; do
        if screen -list | grep -q "$s"; then
            echo -e "  ${GREEN}●${NC} $s — running"
        else
            echo -e "  ${RED}●${NC} $s — stopped"
        fi
    done
    echo ""
    echo -e "  ${CYAN}Dashboard:${NC} http://35.209.110.230:5000"
    echo -e "  ${CYAN}Inverter API:${NC} http://35.209.110.230:5001"
    echo ""
}

# ── Handle commands ─────────────────────────────────────────
if [ "$1" = "stop" ]; then
    stop_all
    exit 0
fi

if [ "$1" = "status" ]; then
    status
    exit 0
fi

# ── Start all ───────────────────────────────────────────────
echo -e "  ${AMBER}Killing any existing sessions...${NC}"
stop_all 2>/dev/null || true

echo -e "  ${GREEN}[1/7] Starting Hardhat blockchain...${NC}"
screen -dmS hardhat bash -c "cd ~/tiny-hub && source venv/bin/activate && npx hardhat node 2>&1"
sleep 4

echo -e "  ${GREEN}[2/7] Deploying smart contracts...${NC}"
npx hardhat run deploy_v2.js --network localhost 2>&1 | tail -5
echo ""

echo -e "  ${GREEN}[3/7] Starting D91 marketplace (Peoria/Ameren)...${NC}"
screen -dmS d91-market bash -c "cd ~/tiny-hub && source venv/bin/activate && python3 -u d91_marketplace_live.py 2>&1"
sleep 1

echo -e "  ${GREEN}[4/7] Starting D63 marketplace (McHenry/ComEd)...${NC}"
screen -dmS d63-market bash -c "cd ~/tiny-hub && source venv/bin/activate && python3 -u d63_marketplace_live.py 2>&1"
sleep 1

echo -e "  ${GREEN}[5/7] Starting on-chain settler...${NC}"
screen -dmS settler bash -c "cd ~/tiny-hub && source venv/bin/activate && python3 -u d91_settler.py 2>&1"
sleep 1

echo -e "  ${GREEN}[6/7] Starting cross-district bridge...${NC}"
screen -dmS bridge bash -c "cd ~/tiny-hub && source venv/bin/activate && python3 -u d91_bridge.py 2>&1"
sleep 1

echo -e "  ${GREEN}[7/7] Starting dashboard + inverter API...${NC}"
screen -dmS dashboard bash -c "cd ~/tiny-hub && source venv/bin/activate && python3 -u app.py 2>&1"
screen -dmS inverter bash -c "cd ~/tiny-hub && source venv/bin/activate && python3 -u inverter_api.py 2>&1"
sleep 2

echo ""
echo -e "  ${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "  ${CYAN}║     ALL SERVICES RUNNING                                ║${NC}"
echo -e "  ${CYAN}╠═══════════════════════════════════════════════════════════╣${NC}"
echo -e "  ${CYAN}║${NC}  ${GREEN}●${NC} hardhat      Chain 31337                            ${CYAN}║${NC}"
echo -e "  ${CYAN}║${NC}  ${GREEN}●${NC} d91-market   Peoria / Ameren / MISO                 ${CYAN}║${NC}"
echo -e "  ${CYAN}║${NC}  ${GREEN}●${NC} d63-market   McHenry / ComEd / PJM                  ${CYAN}║${NC}"
echo -e "  ${CYAN}║${NC}  ${GREEN}●${NC} settler      Pub/Sub → MarketV2                     ${CYAN}║${NC}"
echo -e "  ${CYAN}║${NC}  ${GREEN}●${NC} bridge       D63 ↔ D91 cross-district               ${CYAN}║${NC}"
echo -e "  ${CYAN}║${NC}  ${GREEN}●${NC} dashboard    http://35.209.110.230:5000              ${CYAN}║${NC}"
echo -e "  ${CYAN}║${NC}  ${GREEN}●${NC} inverter     http://35.209.110.230:5001              ${CYAN}║${NC}"
echo -e "  ${CYAN}╠═══════════════════════════════════════════════════════════╣${NC}"
echo -e "  ${CYAN}║${NC}  ${AMBER}Commands:${NC}                                              ${CYAN}║${NC}"
echo -e "  ${CYAN}║${NC}    ./start_all.sh status  — check services              ${CYAN}║${NC}"
echo -e "  ${CYAN}║${NC}    ./start_all.sh stop    — kill everything             ${CYAN}║${NC}"
echo -e "  ${CYAN}║${NC}    screen -r dashboard    — peek at logs (Ctrl+A D)     ${CYAN}║${NC}"
echo -e "  ${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
