#!/bin/bash
set -e

# Configuration
CONTAINER_NAME="prowlarr-llm-proxy"
IMAGE_NAME="prowlarr-llm-proxy"
UPSTREAM_URL="${UPSTREAM_URL:-http://192.168.10.199:8989}"
PORT="${PORT:-8585}"

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
  -e UPSTREAM_URL="$UPSTREAM_URL" \
  -p "$PORT":8080 \
  "$IMAGE_NAME"

echo "==> Done! Container is running on port $PORT"
docker ps | grep "$CONTAINER_NAME"

