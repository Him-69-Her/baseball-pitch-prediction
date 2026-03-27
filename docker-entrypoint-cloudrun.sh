#!/bin/sh
if [ -f /app/deployment.json ]; then
    echo "  ✅ deployment.json found"
else
    echo "  ⚠️  No deployment.json — chain API will be unavailable"
fi
exec "$@"
