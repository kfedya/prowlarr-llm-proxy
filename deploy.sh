#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER_NAME="prowlarr-llm-proxy"
IMAGE_NAME="prowlarr-llm-proxy"
ENV_FILE="$SCRIPT_DIR/.env"

# Check .env file exists
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: .env file not found at $ENV_FILE"
  echo "Create it with:"
  echo "  OPENAI_API_KEY=sk-proj-your-key"
  echo "  ROUTES={\"8585\": \"http://sonarr:8989\", \"8586\": \"http://prowlarr:9696\"}"
  exit 1
fi

echo "==> Using env file: $ENV_FILE"

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
  --env-file "$ENV_FILE" \
  -p 8585:8585 \
  -p 8586:8586 \
  "$IMAGE_NAME"

echo "==> Done!"
echo ""
docker logs --tail 20 "$CONTAINER_NAME"
