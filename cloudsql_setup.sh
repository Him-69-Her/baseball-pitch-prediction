#!/bin/bash
# ══════════════════════════════════════════════════════════════
# TINY-HUB-NETWORK — Cloud SQL + PostGIS Setup
# Creates a PostgreSQL 15 instance with PostGIS on GCP
# Run from the VM or any machine with gcloud configured
# ══════════════════════════════════════════════════════════════

set -e

PROJECT_ID="tiny-hub-network"
INSTANCE_NAME="tinyhub-postgres"
REGION="us-central1"
TIER="db-f1-micro"          # Cheapest tier — upgrade later
DB_NAME="tinyhub"
DB_USER="tinyhub_app"
DB_PASS="$(openssl rand -base64 18)"  # Random password

echo ""
echo "  ╔═══════════════════════════════════════════════════════════════════╗"
echo "  ║   TINY-HUB-NETWORK — Cloud SQL + PostGIS Setup                  ║"
echo "  ╠═══════════════════════════════════════════════════════════════════╣"
echo "  ║  Instance:  $INSTANCE_NAME"
echo "  ║  Region:    $REGION"
echo "  ║  Tier:      $TIER"
echo "  ║  Database:  $DB_NAME"
echo "  ║  User:      $DB_USER"
echo "  ╚═══════════════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Create Cloud SQL instance ────────────────────────────
echo "  [1/6] Creating Cloud SQL PostgreSQL 15 instance..."
gcloud sql instances create $INSTANCE_NAME \
    --project=$PROJECT_ID \
    --database-version=POSTGRES_15 \
    --tier=$TIER \
    --region=$REGION \
    --storage-type=SSD \
    --storage-size=10GB \
    --storage-auto-increase \
    --availability-type=zonal \
    --no-assign-ip \
    --network=default \
    --enable-google-private-path \
    --database-flags=cloudsql.iam_authentication=on

echo "  ✅ Instance created"

# ── 2. Set up private IP connectivity ───────────────────────
echo ""
echo "  [2/6] Getting instance connection info..."
INSTANCE_IP=$(gcloud sql instances describe $INSTANCE_NAME \
    --project=$PROJECT_ID \
    --format="value(ipAddresses[0].ipAddress)")
echo "  Instance IP: $INSTANCE_IP"

# ── 3. Create database ─────────────────────────────────────
echo ""
echo "  [3/6] Creating database: $DB_NAME"
gcloud sql databases create $DB_NAME \
    --instance=$INSTANCE_NAME \
    --project=$PROJECT_ID

echo "  ✅ Database created"

# ── 4. Create user ──────────────────────────────────────────
echo ""
echo "  [4/6] Creating user: $DB_USER"
gcloud sql users create $DB_USER \
    --instance=$INSTANCE_NAME \
    --project=$PROJECT_ID \
    --password=$DB_PASS

echo "  ✅ User created"

# ── 5. Enable PostGIS ───────────────────────────────────────
echo ""
echo "  [5/6] Enabling PostGIS extension..."
gcloud sql connect $INSTANCE_NAME --database=$DB_NAME --user=$DB_USER --project=$PROJECT_ID << EOF
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
SELECT PostGIS_Version();
EOF

echo "  ✅ PostGIS enabled"

# ── 6. Store credentials in Secret Manager ──────────────────
echo ""
echo "  [6/6] Storing credentials in Secret Manager..."

CONN_STRING="postgresql://$DB_USER:$DB_PASS@$INSTANCE_IP:5432/$DB_NAME"

# Store connection string
echo -n "$CONN_STRING" | gcloud secrets create tinyhub-db-url \
    --project=$PROJECT_ID \
    --data-file=- \
    --replication-policy=automatic 2>/dev/null || \
echo -n "$CONN_STRING" | gcloud secrets versions add tinyhub-db-url \
    --project=$PROJECT_ID \
    --data-file=-

echo "  ✅ Credentials stored in Secret Manager"

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "  ╔═══════════════════════════════════════════════════════════════════╗"
echo "  ║   SETUP COMPLETE                                                 ║"
echo "  ╠═══════════════════════════════════════════════════════════════════╣"
echo "  ║  Instance:   $INSTANCE_NAME"
echo "  ║  IP:         $INSTANCE_IP"
echo "  ║  Database:   $DB_NAME"
echo "  ║  User:       $DB_USER"
echo "  ║  Password:   $DB_PASS"
echo "  ║  Connection: $CONN_STRING"
echo "  ║  Secret:     tinyhub-db-url"
echo "  ╠═══════════════════════════════════════════════════════════════════╣"
echo "  ║  SAVE THE PASSWORD — it will not be shown again.                 ║"
echo "  ║  Next: python3 cloudsql_schema.py                                ║"
echo "  ║  Then: python3 cloudsql_migrate.py                               ║"
echo "  ╚═══════════════════════════════════════════════════════════════════╝"
echo ""

# Write env file for convenience
cat > .db_env << ENVEOF
export TINYHUB_DB_URL="$CONN_STRING"
export TINYHUB_DB_HOST="$INSTANCE_IP"
export TINYHUB_DB_NAME="$DB_NAME"
export TINYHUB_DB_USER="$DB_USER"
export TINYHUB_DB_PASS="$DB_PASS"
ENVEOF

echo "  Wrote .db_env — source it before running schema/migrate scripts:"
echo "    source .db_env"
echo ""
