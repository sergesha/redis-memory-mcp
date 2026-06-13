#!/bin/bash
# redis-memory-mcp — self-installing start script
# All setup output goes to stderr; only MCP server uses stdout (JSON-RPC)
set -e

REPO="sergesha/redis-memory-mcp"
# Which version to install:
#   - REDIS_MEMORY_MCP_REF set        → use it verbatim (e.g. v0.2.0, or "main" to track dev)
#   - unset                           → latest published release tag (via GitHub API)
#   - API unavailable / offline       → FALLBACK_REF
REF="${REDIS_MEMORY_MCP_REF:-}"
WORK_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/redis-memory-mcp"
REF_FILE="$WORK_DIR/.installed-ref"
mkdir -p "$WORK_DIR"

log() { echo "🧠 redis-memory-mcp: $*" >&2; }

latest_release() {
  # Latest published release tag from GitHub; empty on any failure (network, rate limit, no release).
  curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null \
    | grep -m1 '"tag_name"' \
    | sed -E 's/.*"tag_name"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/'
}

# Resolve which ref to install, in order of preference (no version is ever hardcoded here):
#   1. explicit REDIS_MEMORY_MCP_REF (e.g. v0.2.0, or "main" to track dev)
#   2. latest published release tag (GitHub API)
#   3. the ref already installed here — a transient API failure must not change the version
#   4. "main" as a last resort on a cold, offline first run
if [ -z "$REF" ]; then
  REF="$(latest_release || true)"
  if [ -z "$REF" ] && [ -f "$REF_FILE" ]; then
    REF="$(cat "$REF_FILE")"
    log "Release lookup failed; reusing installed ref."
  fi
  if [ -z "$REF" ]; then
    REF="main"
    log "No release found and nothing installed yet; falling back to 'main'."
  fi
fi
log "Using ref: $REF"

RAW_URL="https://raw.githubusercontent.com/$REPO/$REF"
IMAGE="redis-memory-mcp:$REF"
COMPOSE_FILE="$WORK_DIR/docker-compose.yaml"
SERVER_DIR="$WORK_DIR/server"

# ── 1. (Re)download pinned sources when the installed ref changes ─────────────
INSTALLED_REF="$(cat "$REF_FILE" 2>/dev/null || true)"
if [ "$INSTALLED_REF" != "$REF" ] || [ ! -f "$COMPOSE_FILE" ] || [ ! -d "$SERVER_DIR" ]; then
  log "Downloading sources for $REF..."
  curl -fsSL "$RAW_URL/docker-compose.yaml" -o "$COMPOSE_FILE"
  mkdir -p "$SERVER_DIR"
  for f in memory_mcp.py Dockerfile pyproject.toml; do
    curl -fsSL "$RAW_URL/server/$f" -o "$SERVER_DIR/$f"
  done
  echo "$REF" > "$REF_FILE"
fi

# ── 2. Start Redis + TEI (idempotent) ─────────────────────────────────────────
log "Starting infrastructure..."
docker compose -f "$COMPOSE_FILE" up -d redis embeddings redis-init >/dev/null 2>&1

# ── 3. Wait for Redis ─────────────────────────────────────────────────────────
log "Waiting for Redis..."
until docker exec redis-stack redis-cli ping >/dev/null 2>&1; do sleep 1; done

# ── 4. Build the version-tagged MCP server image if not present ───────────────
# Tagging the image per ref means switching REF rebuilds instead of reusing stale layers.
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  log "Building $IMAGE..."
  docker build -t "$IMAGE" "$SERVER_DIR" >&2
fi

log "Ready ($REF)."

# ── 5. Launch MCP server — only this writes to stdout ─────────────────────────
exec docker run --rm -i \
  -e "REDIS_URL=${REDIS_URL:-redis://host.docker.internal:6379/0}" \
  -e "EMBED_URL=${EMBED_URL:-http://host.docker.internal:8081}" \
  -e "INDEX_NAME=${INDEX_NAME:-idx:memories}" \
  "$IMAGE"
