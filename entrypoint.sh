#!/bin/bash
set -e

# Parse ROUTES JSON and start uvicorn for each port
# Example ROUTES: {"8585": "http://sonarr:8989", "8586": "http://prowlarr:9696"}

if [ -z "$ROUTES" ]; then
    # Single port mode
    echo "Starting single instance on port ${PORT:-8080}"
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
else
    # Multi-port mode: extract ports from ROUTES JSON
    PORTS=$(echo "$ROUTES" | python3 -c "import sys, json; print(' '.join(json.load(sys.stdin).keys()))")
    
    echo "Starting instances on ports: $PORTS"
    
    # Start uvicorn for each port (all sharing same app with route detection)
    PIDS=""
    for PORT in $PORTS; do
        echo "Starting on port $PORT..."
        uvicorn app.main:app --host 0.0.0.0 --port "$PORT" &
        PIDS="$PIDS $!"
    done
    
    # Wait for any process to exit
    wait -n $PIDS
    
    # Kill remaining processes
    kill $PIDS 2>/dev/null || true
fi


