#!/bin/bash
# redis-memory-mcp — self-installing start script
# Usage in mcp.json:
#   "command": "bash",
#   "args": ["-c", "curl -fsSL https://raw.githubusercontent.com/sergesha/redis-memory-mcp/main/start.sh | bash"]
#
# On first run: clones repo, builds images, starts Redis + TEI, launches MCP server (stdio)
# On subsequent runs: skips already-running containers and built images (idempotent)

set -e

REPO_URL="https://github.com/sergesha/redis-memory-mcp"
RAW_URL="https://raw.githubusercontent.com/sergesha/redis-memory-mcp/main"
WORK_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/redis-memory-mcp"

# ── 1. Download docker-compose.yaml if missing or stale (1 day) ───────────────
mkdir -p "$WORK_DIR"
COMPOSE_FILE="$WORK_DIR/docker-compose.yaml"
if [ ! -f "$COMPOSE_FILE" ] || [ "$(find "$COMPOSE_FILE" -mtime +1 2>/dev/null)" ]; then
  curl -fsSL "$RAW_URL/docker-compose.yaml" -o "$COMPOSE_FILE" >&2
fi

# ── 2. Download server/ source if missing (needed to build image) ─────────────
SERVER_DIR="$WORK_DIR/server"
if [ ! -d "$SERVER_DIR" ]; then
  mkdir -p "$SERVER_DIR"
  for f in memory_mcp.py Dockerfile pyproject.toml; do
    curl -fsSL "$RAW_URL/server/$f" -o "$SERVER_DIR/$f" >&2
  done
fi

# ── 3. Start Redis + TEI (idempotent) ─────────────────────────────────────────
docker compose -f "$COMPOSE_FILE" up -d redis embeddings redis-init 2>/dev/null

# ── 4. Wait for Redis ─────────────────────────────────────────────────────────
until docker exec redis-stack redis-cli ping &>/dev/null 2>&1; do sleep 1; done

# ── 5. Build MCP server image if not present ──────────────────────────────────
if ! docker image inspect redis-memory-mcp &>/dev/null 2>&1; then
  docker build -t redis-memory-mcp "$SERVER_DIR" >&2
fi

# ── 6. Launch MCP server (stdio) ──────────────────────────────────────────────
exec docker run --rm -i \
  -e "REDIS_URL=${REDIS_URL:-redis://host.docker.internal:6379/0}" \
  -e "EMBED_URL=${EMBED_URL:-http://host.docker.internal:8081}" \
  -e "INDEX_NAME=${INDEX_NAME:-idx:memories}" \
  redis-memory-mcp

