#!/bin/bash
set -e

# Configuration
CONTAINER_NAME="prowlarr-llm-proxy"
IMAGE_NAME="prowlarr-llm-proxy"

# Multi-port routing (edit these!)
SONARR_URL="${SONARR_URL:-http://192.168.10.199:8989}"
PROWLARR_URL="${PROWLARR_URL:-http://192.168.10.199:9696}"
PORT_TO_SONARR="${PORT_TO_SONARR:-8585}"
PORT_TO_PROWLARR="${PORT_TO_PROWLARR:-8586}"

# Build ROUTES JSON
ROUTES="{\"${PORT_TO_SONARR}\": \"${SONARR_URL}\", \"${PORT_TO_PROWLARR}\": \"${PROWLARR_URL}\"}"

echo "==> Configuration:"
echo "    Port $PORT_TO_SONARR -> $SONARR_URL"
echo "    Port $PORT_TO_PROWLARR -> $PROWLARR_URL"

echo "==> Pulling latest changes..."
git pull

echo "==> Building Docker image..."
docker build -t "$IMAGE_NAME" .

echo "==> Stopping and removing old container..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "==> Starting new container..."
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -e ROUTES="$ROUTES" \
  -e PORT="$PORT_TO_SONARR" \
  -p "$PORT_TO_SONARR":8585 \
  -p "$PORT_TO_PROWLARR":8586 \
  "$IMAGE_NAME"

echo "==> Done!"
echo ""
echo "Configure in Prowlarr:"
echo "  Sonarr Server: http://YOUR_NAS_IP:$PORT_TO_SONARR"
echo ""
echo "Configure in Sonarr:"  
echo "  Prowlarr indexer URL: http://YOUR_NAS_IP:$PORT_TO_PROWLARR"
echo ""
docker ps | grep "$CONTAINER_NAME"
