# prowlarr-llm-proxy

Transparent proxy with request/response logging. Sits between Prowlarr and Sonarr/Radarr.

```
Prowlarr → Proxy (8585) → Sonarr (8989)
```

## Docker (Unraid)

### Build

```bash
docker build -t prowlarr-llm-proxy .
```

### Run

```bash
docker run -d \
  --name prowlarr-llm-proxy \
  --restart unless-stopped \
  -e UPSTREAM_URL=http://192.168.10.199:8989 \
  -p 8585:8080 \
  prowlarr-llm-proxy
```

Then in Prowlarr settings, set Sonarr URL to `http://your-nas-ip:8585`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | Port to listen on inside container |
| `UPSTREAM_URL` | `http://localhost:8989` | Sonarr/Radarr URL to proxy to |
| `PROXY_TIMEOUT` | `60` | Request timeout in seconds |

### Health Checks

- `GET /health` - Overall health
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe

## Local Development

```bash
poetry install
UPSTREAM_URL=http://sonarr:8989 poetry run uvicorn app.main:app --reload --port 8080
```
