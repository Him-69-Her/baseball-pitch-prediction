#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# TINY-HUB — Deploy Batch Settler as Cloud Functions Gen 2
#
# Two functions:
#   1. ingest-trade:  Pub/Sub push → buffers trade
#   2. flush-batch:   Cloud Scheduler → settles on chain
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project tiny-hub-network
# ═══════════════════════════════════════════════════════════════

set -e

PROJECT_ID="tiny-hub-network"
REGION="us-central1"
RUNTIME="python311"

echo ""
echo "  ╔═══════════════════════════════════════════════════════════╗"
echo "  ║  Deploy Batch Settler — Cloud Functions Gen 2            ║"
echo "  ╚═══════════════════════════════════════════════════════════╝"
echo ""

# ── Function 1: Trade Ingestion (Pub/Sub trigger) ───────────
echo "  [1/3] Deploying trade ingestion function..."
gcloud functions deploy ingest-trade \
    --gen2 \
    --region=$REGION \
    --runtime=$RUNTIME \
    --source=. \
    --entry-point=cf_ingest_trade \
    --trigger-topic=district91-energy \
    --memory=512MB \
    --timeout=60s \
    --min-instances=0 \
    --max-instances=5 \
    --set-env-vars="GCP_PROJECT=$PROJECT_ID,RPC_URL=http://hardhat:8545" \
    --project=$PROJECT_ID

echo "  ✅ ingest-trade deployed"

# Also subscribe to D63 topic
gcloud functions deploy ingest-trade-d63 \
    --gen2 \
    --region=$REGION \
    --runtime=$RUNTIME \
    --source=. \
    --entry-point=cf_ingest_trade \
    --trigger-topic=energy-pulse \
    --memory=512MB \
    --timeout=60s \
    --min-instances=0 \
    --max-instances=5 \
    --set-env-vars="GCP_PROJECT=$PROJECT_ID,RPC_URL=http://hardhat:8545" \
    --project=$PROJECT_ID

echo "  ✅ ingest-trade-d63 deployed"

# ── Function 2: Batch Flush (HTTP + Scheduler) ──────────────
echo ""
echo "  [2/3] Deploying batch flush function..."
gcloud functions deploy flush-batch \
    --gen2 \
    --region=$REGION \
    --runtime=$RUNTIME \
    --source=. \
    --entry-point=cf_flush_batch \
    --trigger-http \
    --allow-unauthenticated \
    --memory=1GB \
    --timeout=300s \
    --min-instances=0 \
    --max-instances=1 \
    --set-env-vars="GCP_PROJECT=$PROJECT_ID,RPC_URL=http://hardhat:8545,BATCH_INTERVAL_SEC=3600" \
    --project=$PROJECT_ID

FLUSH_URL=$(gcloud functions describe flush-batch --gen2 --region=$REGION --format="value(serviceConfig.uri)" --project=$PROJECT_ID)
echo "  ✅ flush-batch deployed at $FLUSH_URL"

# ── Cloud Scheduler Job ─────────────────────────────────────
echo ""
echo "  [3/3] Creating hourly scheduler job..."
gcloud scheduler jobs create http batch-settler-hourly \
    --schedule="0 * * * *" \
    --uri="$FLUSH_URL" \
    --http-method=POST \
    --location=$REGION \
    --project=$PROJECT_ID \
    2>/dev/null || \
gcloud scheduler jobs update http batch-settler-hourly \
    --schedule="0 * * * *" \
    --uri="$FLUSH_URL" \
    --http-method=POST \
    --location=$REGION \
    --project=$PROJECT_ID

echo "  ✅ Scheduler: every hour on the hour"

echo ""
echo "  ╔═══════════════════════════════════════════════════════════╗"
echo "  ║  ✅ Cloud Functions Gen 2 Deployed                       ║"
echo "  ╠═══════════════════════════════════════════════════════════╣"
echo "  ║  ingest-trade:     Pub/Sub → buffer trades               ║"
echo "  ║  ingest-trade-d63: Pub/Sub → buffer trades               ║"
echo "  ║  flush-batch:      HTTP → settle on chain                ║"
echo "  ║  Scheduler:        Every hour → flush-batch              ║"
echo "  ╚═══════════════════════════════════════════════════════════╝"
echo ""
