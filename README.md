# redis-memory-mcp

> Persistent cross-session memory for AI agents — semantic search + KV store with auto-expiry

Long-term self-managing memory for LLM agents (Cursor, Claude Code, etc.) via [MCP](https://modelcontextprotocol.io).

## Features

- **Semantic search** (`mem_*`) — save facts with vector embeddings, find by meaning
- **Key-value store** (`kv_*`) — instant O(1) lookup for named facts
- **Auto-expiry** — TTL resets on every read; unused facts expire, popular ones live forever
- **Multi-project** — tag-based isolation between projects
- **Self-contained** — Docker stack: Redis Stack + HuggingFace TEI embeddings + MCP server

## Quick Start

```bash
# 1. Clone
git clone https://github.com/yourname/redis-memory-mcp
cd redis-memory-mcp

# 2. Start infrastructure
docker compose up -d

# 3. Add to your AI tool's MCP config
```

### Cursor (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "redis-memory-mcp": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "REDIS_URL=redis://host.docker.internal:6379/0",
        "-e", "EMBED_URL=http://host.docker.internal:8081",
        "-e", "INDEX_NAME=idx:memories",
        "redis-memory-mcp"
      ]
    }
  }
}
```

### Claude Code

Works automatically via `.mcp.json` in the repo root when using as a Claude plugin.

## Tools (8 total)

### Key-Value Storage — instant lookup

| Tool | Description |
|------|-------------|
| `kv_set(key, value, tags?, ttl_days?)` | Store a named fact |
| `kv_get(key)` | Retrieve by exact key (refreshes TTL) |
| `kv_delete(key)` | Delete by key |
| `kv_list(tag?, pattern?)` | List entries with filtering |

### Semantic Memory — vector search

| Tool | Description |
|------|-------------|
| `mem_save(text, code?, tags?, ttl_days?)` | Save fact with embedding |
| `mem_search(query, tags?, top_k?)` | Find by meaning (refreshes TTL on hits) |
| `mem_list(limit?, tag?)` | Browse by recency |
| `mem_delete(memory_id)` | Delete by ID |

## TTL & Auto-Expiry

| TTL | Use case |
|-----|----------|
| `ttl_days=90` (default) | Normal facts — expire if unused for 90 days |
| `ttl_days=0` | Permanent — API keys, critical config |
| `ttl_days=7` | Short-lived context |

- TTL **resets on every read** — frequently accessed facts never expire
- Redis `volatile-lru` evicts least-recently-used facts under memory pressure
- Only facts with TTL can be evicted; permanent facts (`ttl_days=0`) are safe

## Architecture

```
┌─────────────────┐     ┌────────────────────┐     ┌───────────────────┐
│  Cursor / Claude │────▶│  redis-memory-mcp  │────▶│   Redis Stack     │
│  (MCP client)    │ MCP │  (Python, stdio)   │     │   + RediSearch    │
└─────────────────┘     └────────┬───────────┘     │   + HNSW index    │
                                 │                  └───────────────────┘
                                 ▼
                        ┌────────────────────┐
                        │  HuggingFace TEI   │
                        │  (embeddings, CPU) │
                        └────────────────────┘
```

- **Redis Stack** — RediSearch module with HNSW vector index (768 dim, cosine)
- **TEI** — `paraphrase-multilingual-mpnet-base-v2` (multilingual, runs on CPU)
- **MCP server** — Python FastMCP over stdio

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `EMBED_URL` | `http://localhost:8081` | TEI embeddings endpoint |
| `INDEX_NAME` | `idx:memories` | Redis search index name |
| `DEFAULT_TTL` | `7776000` (90 days) | Default TTL in seconds |

## Redis UI

RedisInsight is included at **http://localhost:8001** — browse keys, run queries, analyze memory usage.

## Plugin Structure

```
redis-memory-mcp/
├── .claude-plugin/marketplace.json   # Marketplace registry
├── .claude/settings.json             # Auto-load config
├── redis-memory-mcp/                 # Claude plugin
│   ├── .claude-plugin/
│   │   ├── plugin.json               # Plugin metadata
│   │   └── mcp.json                  # MCP server docs
│   ├── .mcp.json                     # Runtime MCP config
│   ├── hooks/project-init.json       # Session start hook
│   └── skills/persistent-memory/
│       └── SKILL.md                  # Memory management skill
├── server/                           # MCP server source
│   ├── memory_mcp.py
│   ├── Dockerfile
│   └── pyproject.toml
├── docker-compose.yaml               # Full stack
└── README.md
```

## License

MIT
