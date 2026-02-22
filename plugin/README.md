# redis-memory-mcp

> Persistent cross-session memory for AI agents

## Tools

**Key-Value** (instant O(1) lookup):
- `kv_set` / `kv_get` / `kv_delete` / `kv_list`

**Semantic** (vector similarity search):
- `mem_save` / `mem_search` / `mem_list` / `mem_delete`

## Auto-Expiry

- Default TTL: 90 days, resets on every read
- `ttl_days=0` for permanent facts
- volatile-lru eviction under memory pressure

## Setup

```bash
docker compose up -d
```

See [persistent-memory skill](./skills/persistent-memory/SKILL.md) for usage patterns.
