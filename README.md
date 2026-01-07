# prowlarr-llm-proxy

Transparent proxy between Sonarr/Radarr and Prowlarr with request/response logging.

## Docker (Unraid)

### Build

```bash
docker build -t prowlarr-llm-proxy .
```

### Run

```bash
docker run -d \
  --name prowlarr-llm-proxy \
  -e PROWLARR_URL=http://192.168.1.100:9696 \
  -p 8080:8080 \
  prowlarr-llm-proxy
```

Then point Sonarr/Radarr indexer to `http://your-nas-ip:8080`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | Port to listen on |
| `PROWLARR_URL` | `http://localhost:9696` | Prowlarr URL to proxy to |
| `PROXY_TIMEOUT` | `60` | Request timeout in seconds |

### Health Checks

- `GET /health` - Overall health
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe

## Local Development

```bash
poetry install
poetry run uvicorn app.main:app --reload --port 8080
```
