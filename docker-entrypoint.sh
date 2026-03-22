#!/bin/sh
# Wait for Hardhat to deploy contracts and write deployment.json to shared volume
echo "  Waiting for deployment.json from Hardhat..."
TRIES=0
while [ ! -f /shared/deployment.json ] && [ $TRIES -lt 60 ]; do
    sleep 1
    TRIES=$((TRIES + 1))
done

if [ -f /shared/deployment.json ]; then
    cp /shared/deployment.json /app/deployment.json
    echo "  ✅ deployment.json loaded"
else
    echo "  ⚠️  deployment.json not found after 60s — proceeding anyway"
fi

# Run the actual command
exec "$@"
