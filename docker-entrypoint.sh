#!/bin/sh
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
