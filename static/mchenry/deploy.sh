#!/usr/bin/env bash
# =============================================================
# TINY-HUB · McHenry County Demo · Deploy
# Supports three deploy modes: gcs (default), firebase, cloudrun.
# Run with: ./deploy.sh <mode> [args]
# =============================================================
set -euo pipefail

MODE="${1:-gcs}"
PROJECT_ID="${PROJECT_ID:-tinyhub-platform-dev}"
BUCKET="${BUCKET:-tinyhub-mchenry-demo}"
REGION="${REGION:-us-central1}"
SUBDOMAIN="${SUBDOMAIN:-mchenry.tinyhub.energy}"
ORG="${ORG:-tinyhub.energy}"

DIR="$(cd "$(dirname "$0")" && pwd)"
echo "▸ Tiny-Hub deploy · mode=$MODE · project=$PROJECT_ID"

# Sanity check
required=(index.html live-map.html analytics-console.html solver.html final-report.html glossary.html)
for f in "${required[@]}"; do
  [[ -f "$DIR/$f" ]] || { echo "✗ missing: $f"; exit 1; }
done
[[ -d "$DIR/assets" ]] || { echo "✗ missing assets/ directory"; exit 1; }
echo "✓ all required files present"

case "$MODE" in
  # -------------------------------------------------------------
  # 1. GCS static site (recommended for static demo + custom domain)
  # -------------------------------------------------------------
  gcs)
    echo "▸ Deploying to gs://$BUCKET (project: $PROJECT_ID)"
    gcloud config set project "$PROJECT_ID"

    # Create bucket if it doesn't exist
    if ! gsutil ls -b "gs://$BUCKET" &>/dev/null; then
      echo "  · creating bucket $BUCKET"
      gsutil mb -l "$REGION" -p "$PROJECT_ID" "gs://$BUCKET"
      gsutil iam ch allUsers:objectViewer "gs://$BUCKET"
      gsutil web set -m index.html -e index.html "gs://$BUCKET"
    fi

    # Sync, with cache headers per file type
    echo "  · syncing files"
    gsutil -m -h "Cache-Control:public,max-age=300" \
      rsync -r -d -x "deploy\.sh|README\.md|\.git" "$DIR" "gs://$BUCKET"

    # Long-cache for assets
    gsutil -m -h "Cache-Control:public,max-age=86400" \
      cp -r "$DIR/assets" "gs://$BUCKET/assets" || true

    echo "✓ Deployed."
    echo ""
    echo "  Direct URL:    https://storage.googleapis.com/$BUCKET/index.html"
    echo ""
    echo "  Custom domain: requires Cloud Load Balancer. Quick setup:"
    echo "    gcloud compute backend-buckets create tinyhub-mchenry-bb --gcs-bucket-name=$BUCKET"
    echo "    gcloud compute url-maps create tinyhub-mchenry-lb --default-backend-bucket=tinyhub-mchenry-bb"
    echo "    # then attach SSL cert + global forwarding rule for $SUBDOMAIN"
    ;;

  # -------------------------------------------------------------
  # 2. Firebase Hosting (lowest friction, free tier covers demo)
  # -------------------------------------------------------------
  firebase)
    echo "▸ Deploying to Firebase Hosting (project: $PROJECT_ID)"
    cat > "$DIR/firebase.json" <<'JSON'
{
  "hosting": {
    "public": ".",
    "ignore": ["firebase.json", "**/.*", "**/node_modules/**", "deploy.sh", "README.md"],
    "rewrites": [{ "source": "/", "destination": "/index.html" }],
    "headers": [
      { "source": "/assets/**", "headers": [{ "key": "Cache-Control", "value": "public, max-age=86400" }] },
      { "source": "/**.html",   "headers": [{ "key": "Cache-Control", "value": "public, max-age=300" }] }
    ]
  }
}
JSON
    firebase use "$PROJECT_ID" --add 2>/dev/null || true
    firebase deploy --only hosting --project "$PROJECT_ID"
    echo ""
    echo "✓ Deployed. Connect $SUBDOMAIN in the Firebase Console under Hosting → Add custom domain."
    ;;

  # -------------------------------------------------------------
  # 3. Cloud Run + nginx (if everything must live behind your auth perimeter)
  # -------------------------------------------------------------
  cloudrun)
    echo "▸ Deploying to Cloud Run (project: $PROJECT_ID)"
    cat > "$DIR/Dockerfile" <<'DOCKER'
FROM nginx:alpine
COPY . /usr/share/nginx/html
RUN rm -f /usr/share/nginx/html/Dockerfile /usr/share/nginx/html/deploy.sh
COPY <<'NGINX' /etc/nginx/conf.d/default.conf
server {
  listen       8080;
  server_name  _;
  root         /usr/share/nginx/html;
  index        index.html;
  location ~* \.(css|js|jsx|svg|woff2?)$ { expires 1d; add_header Cache-Control "public, max-age=86400"; }
  location ~* \.html$ { expires 5m; add_header Cache-Control "public, max-age=300"; }
}
NGINX
DOCKER
    gcloud run deploy tinyhub-mchenry-demo \
      --source "$DIR" \
      --region "$REGION" \
      --project "$PROJECT_ID" \
      --allow-unauthenticated \
      --port 8080 \
      --cpu 0.5 --memory 256Mi --max-instances 5
    echo ""
    echo "✓ Deployed. Map $SUBDOMAIN with: gcloud run domain-mappings create --service tinyhub-mchenry-demo --domain $SUBDOMAIN --region $REGION"
    ;;

  *)
    echo "Unknown mode: $MODE"
    echo "Usage: ./deploy.sh [gcs|firebase|cloudrun]"
    exit 2
    ;;
esac
