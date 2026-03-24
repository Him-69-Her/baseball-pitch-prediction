#!/bin/bash
# ──────────────────────────────────────────────────────────
# TINY-HUB-NETWORK — GCP Blockchain Infrastructure Setup
#
# Enables:
#   1. Blockchain Node Engine API (for mainnet Arbitrum node)
#   2. BigQuery Arbitrum Analytics dataset link
#   3. Secret Manager entries for deployer/settler keys
#   4. BigQuery views joining on-chain data with trades
#
# Run from your VM:
#   chmod +x setup_gcp_blockchain.sh
#   ./setup_gcp_blockchain.sh
# ──────────────────────────────────────────────────────────

set -e

PROJECT_ID="tiny-hub-network"
REGION="us-central1"
DATASET="tinyhub_datalake"

GREEN="\033[0;32m"
AMBER="\033[0;33m"
NC="\033[0m"

echo ""
echo -e "  ${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "  ${GREEN}║  TINY-HUB — GCP Blockchain Setup                 ║${NC}"
echo -e "  ${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Enable APIs ──────────────────────────────────────────
echo -e "  ${GREEN}[1/5] Enabling APIs...${NC}"

gcloud services enable blockchainnodeengine.googleapis.com \
  --project=$PROJECT_ID 2>/dev/null && \
  echo "    ✅ Blockchain Node Engine API" || \
  echo "    ⚠️  Blockchain Node Engine API (may need billing)"

gcloud services enable bigquery.googleapis.com \
  --project=$PROJECT_ID 2>/dev/null && \
  echo "    ✅ BigQuery API" || \
  echo "    ⚠️  BigQuery API already enabled"

gcloud services enable secretmanager.googleapis.com \
  --project=$PROJECT_ID 2>/dev/null && \
  echo "    ✅ Secret Manager API" || \
  echo "    ⚠️  Secret Manager API already enabled"

echo ""

# ── 2. Store deployer key in Secret Manager ─────────────────
echo -e "  ${GREEN}[2/5] Secret Manager setup...${NC}"

# Check if secrets already exist
if gcloud secrets describe DEPLOYER_PRIVATE_KEY --project=$PROJECT_ID &>/dev/null; then
    echo "    ✅ DEPLOYER_PRIVATE_KEY already exists"
else
    echo -e "    ${AMBER}DEPLOYER_PRIVATE_KEY not found.${NC}"
    echo "    To add it, run:"
    echo '    echo -n "0xYOUR_KEY" | gcloud secrets create DEPLOYER_PRIVATE_KEY --project=tiny-hub-network --data-file=-'
fi

if gcloud secrets describe SETTLER_PRIVATE_KEY --project=$PROJECT_ID &>/dev/null; then
    echo "    ✅ SETTLER_PRIVATE_KEY already exists"
else
    echo -e "    ${AMBER}SETTLER_PRIVATE_KEY not found.${NC}"
    echo "    To add it, run:"
    echo '    echo -n "0xYOUR_KEY" | gcloud secrets create SETTLER_PRIVATE_KEY --project=tiny-hub-network --data-file=-'
fi

echo ""

# ── 3. BigQuery: Arbitrum public dataset access ─────────────
echo -e "  ${GREEN}[3/5] BigQuery Arbitrum dataset verification...${NC}"

# Test that we can query the public Arbitrum dataset
bq query --project_id=$PROJECT_ID --use_legacy_sql=false \
  --max_rows=1 --format=prettyjson \
  'SELECT block_number, block_timestamp
   FROM `bigquery-public-data.goog_blockchain_arbitrum_one_us.blocks`
   ORDER BY block_number DESC LIMIT 1' 2>/dev/null && \
  echo "    ✅ Arbitrum One dataset accessible" || \
  echo "    ⚠️  Arbitrum One dataset not accessible (check billing)"

echo ""

# ── 4. Create BigQuery views for on-chain verification ──────
echo -e "  ${GREEN}[4/5] Creating BigQuery settlement verification views...${NC}"

# View: Cross-reference our trades with on-chain Arbitrum txs
bq query --project_id=$PROJECT_ID --use_legacy_sql=false \
  --destination_table="${DATASET}.v_onchain_settlements" \
  --replace --allow_large_results \
  "CREATE OR REPLACE VIEW \`${PROJECT_ID}.${DATASET}.v_onchain_settlements\` AS
  SELECT
    t.trade_id,
    t.station_id,
    t.district,
    t.mwh,
    t.settled_price,
    t.co2_tons,
    t.timestamp AS trade_timestamp,
    arb.block_timestamp AS onchain_timestamp,
    arb.transaction_hash AS tx_hash,
    arb.gas AS gas_used,
    TIMESTAMP_DIFF(arb.block_timestamp, t.timestamp, SECOND) AS settlement_latency_sec
  FROM \`${PROJECT_ID}.${DATASET}.trades\` t
  LEFT JOIN \`bigquery-public-data.goog_blockchain_arbitrum_one_us.transactions\` arb
    ON LOWER(arb.to_address) = LOWER(@market_contract_address)
    AND arb.block_timestamp BETWEEN t.timestamp AND TIMESTAMP_ADD(t.timestamp, INTERVAL 1 HOUR)
  WHERE t.trade_status = 'SETTLED'" 2>/dev/null && \
  echo "    ✅ v_onchain_settlements view created" || \
  echo "    ⚠️  View creation skipped (trades table may not exist yet)"

# View: Daily gas cost tracking
bq query --project_id=$PROJECT_ID --use_legacy_sql=false \
  "CREATE OR REPLACE VIEW \`${PROJECT_ID}.${DATASET}.v_daily_gas_costs\` AS
  SELECT
    DATE(block_timestamp) AS day,
    COUNT(*) AS tx_count,
    SUM(gas) AS total_gas,
    AVG(gas) AS avg_gas_per_tx,
    SUM(CAST(gas_price AS FLOAT64) * gas / 1e18) AS total_eth_spent
  FROM \`bigquery-public-data.goog_blockchain_arbitrum_one_us.transactions\`
  WHERE LOWER(from_address) = LOWER(@settler_address)
    AND block_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  GROUP BY day
  ORDER BY day DESC" 2>/dev/null && \
  echo "    ✅ v_daily_gas_costs view created" || \
  echo "    ⚠️  Gas costs view skipped"

# View: District settlement totals from on-chain events
bq query --project_id=$PROJECT_ID --use_legacy_sql=false \
  "CREATE OR REPLACE VIEW \`${PROJECT_ID}.${DATASET}.v_arbitrum_trade_events\` AS
  SELECT
    block_timestamp,
    transaction_hash,
    -- Decode ResourcePurchased/ResourceBridged events from logs
    topics[OFFSET(0)] AS event_signature,
    topics[OFFSET(1)] AS trade_id_hex,
    data AS event_data
  FROM \`bigquery-public-data.goog_blockchain_arbitrum_one_us.logs\`
  WHERE LOWER(address) = LOWER(@market_contract_address)
    AND block_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
  ORDER BY block_timestamp DESC" 2>/dev/null && \
  echo "    ✅ v_arbitrum_trade_events view created" || \
  echo "    ⚠️  Events view skipped"

echo ""

# ── 5. Print summary + next steps ───────────────────────────
echo -e "  ${GREEN}[5/5] Summary${NC}"
echo ""
echo "  ┌── GCP BLOCKCHAIN INFRASTRUCTURE ──────────────────"
echo "  │"
echo "  │ Blockchain Node Engine API: Enabled"
echo "  │   → For mainnet: spin up dedicated Arbitrum Nitro node"
echo "  │   → For testnet: public RPC is fine"
echo "  │"
echo "  │ BigQuery Arbitrum Dataset:"
echo "  │   → bigquery-public-data.goog_blockchain_arbitrum_one_us"
echo "  │   → Blocks, transactions, logs, traces available"
echo "  │"
echo "  │ BigQuery Views Created:"
echo "  │   → v_onchain_settlements  (trade ↔ on-chain join)"
echo "  │   → v_daily_gas_costs      (settler gas tracking)"
echo "  │   → v_arbitrum_trade_events (decoded contract events)"
echo "  │"
echo "  │ Secret Manager:"
echo "  │   → DEPLOYER_PRIVATE_KEY"
echo "  │   → SETTLER_PRIVATE_KEY"
echo "  │"
echo "  └──────────────────────────────────────────────────"
echo ""
echo "  NEXT STEPS:"
echo "  1. Fund your wallet with Arbitrum Sepolia test ETH"
echo "  2. Store deployer key in Secret Manager (see commands above)"
echo "  3. Deploy contracts: npx hardhat run deploy_l2.js --network arbitrumSepolia"
echo "  4. Start services:  ./start_l2.sh"
echo ""
echo "  FOR MAINNET (later):"
echo "  5. Spin up Arbitrum Nitro node via Blockchain Node Engine"
echo "  6. Update ARBITRUM_RPC in Secret Manager to point to your node"
echo "  7. Redeploy contracts to Arbitrum One"
echo ""
