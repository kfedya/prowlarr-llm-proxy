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

# OpenAI settings
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini}"
LLM_ENABLED="${LLM_ENABLED:-true}"

# Build ROUTES JSON
ROUTES="{\"${PORT_TO_SONARR}\": \"${SONARR_URL}\", \"${PORT_TO_PROWLARR}\": \"${PROWLARR_URL}\"}"

echo "==> Configuration:"
echo "    Port $PORT_TO_SONARR -> $SONARR_URL"
echo "    Port $PORT_TO_PROWLARR -> $PROWLARR_URL"
echo "    LLM Enabled: $LLM_ENABLED"
echo "    Model: $OPENAI_MODEL"

if [ -z "$OPENAI_API_KEY" ]; then
  echo "    WARNING: OPENAI_API_KEY not set! LLM will be disabled."
fi

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
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e OPENAI_MODEL="$OPENAI_MODEL" \
  -e LLM_ENABLED="$LLM_ENABLED" \
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
docker logs --tail 20 "$CONTAINER_NAME"
