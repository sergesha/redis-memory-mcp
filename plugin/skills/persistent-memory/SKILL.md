---
name: persistent-memory
description: >
  Manages persistent cross-session memory using redis-memory-mcp.
  Two modes: semantic search (mem_*) for knowledge by meaning,
  key-value (kv_*) for instant lookup. Auto-expiry via TTL + LRU.
  Triggers: task start (search), solution found (save), bug fix (save),
  architecture decision (save), task complete (reflection + save).

allowed_tools:
  - kv_set
  - kv_get
  - kv_delete
  - kv_list
  - mem_save
  - mem_search
  - mem_list
  - mem_delete
---

# Persistent Memory

Cross-session memory for AI agents using `redis-memory-mcp`.  
Requires MCP server `redis-memory-mcp` to be running.

## Tools Reference

### Key-Value Storage (`kv_*`) — instant O(1) lookup

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `kv_set` | `key` (str), `value` (str), `tags` (str, optional), `ttl_days` (int, default 90) | Store named fact. Overwrites if key exists. |
| `kv_get` | `key` (str) | Retrieve by exact key. Refreshes TTL on read. |
| `kv_delete` | `key` (str) | Delete by key. |
| `kv_list` | `tag` (str, optional), `pattern` (str, optional) | List entries. Filter by tag or glob pattern. |

### Semantic Memory (`mem_*`) — vector similarity search

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `mem_save` | `text` (str), `code` (str, optional), `tags` (str, optional), `ttl_days` (int, default 90) | Save with embedding. Found by meaning. |
| `mem_search` | `query` (str), `tags` (str, optional), `top_k` (int, default 5) | Search by meaning. Refreshes TTL on hits. |
| `mem_list` | `limit` (int, default 20), `tag` (str, optional) | Browse by recency. |
| `mem_delete` | `memory_id` (str) | Delete by UUID from search results. |

### TTL & Auto-Expiry

- **Default: 90 days** — unused facts auto-expire
- **TTL resets on read** — popular facts live forever
- **`ttl_days=0`** — permanent, never expires (use for critical config, API keys)
- **`ttl_days=7`** or `30` — short-lived context
- **volatile-lru** — Redis evicts least-recently-used facts with TTL under memory pressure

### When to Use Which

| Need | Tool | Example |
|------|------|---------|
| Exact fact by name | `kv_set` / `kv_get` | `kv_set('prod-db-url', 'postgresql://...', tags='db,prod', ttl_days=0)` |
| Find by meaning | `mem_save` / `mem_search` | `mem_save(text='JWT with 24h expiry, refresh in Redis', tags='auth,jwt')` |
| Config/credentials | `kv_set` with `ttl_days=0` | `kv_set('openai-key', 'sk-...', tags='secrets', ttl_days=0)` |
| Lessons learned | `mem_save` with tags | `mem_save(text='Problem: X. Solution: Y. Insight: Z.', tags='project,lessons')` |
| Bug patterns | `mem_save` with code | `mem_save(text='Race condition in auth', code='async def ...', tags='bugs')` |

## Process Triggers

### 🔍 SEARCH memory (before acting)

**1. Task Start (MANDATORY)**
Before ANY new task — search for similar past work:
```
mem_search(query="[task description]", tags="[project]", top_k=5)
kv_list(pattern="[project]-*")
```
Present findings before starting work.

**2. Problem Encountered**
When hitting a problem/error:
```
mem_search(query="[error or problem description]", tags="[project]")
```

**3. Architecture/Design Decision**
Before making design choices — check past decisions:
```
mem_search(query="[decision topic]", tags="[project],architecture")
```

**4. Configuration Lookup**
When needing a known value:
```
kv_get(key="[project]-db-url")
```

### 💾 SAVE to memory (after learning)

**5. Solution Found**
After solving a non-trivial problem:
```
mem_save(
  text="Problem: [X]. Solution: [Y]. Key insight: [Z]. Future: [when to reuse].",
  tags="[project],[technology],[type]"
)
```

**6. Task Completed (>30 min or complex)**
Reflection: What worked? What didn't? What patterns emerged?
```
mem_save(
  text="Task: [X]. Approach: [Y]. Lesson: [Z]. Would do differently: [W].",
  tags="[project],lessons"
)
```

**7. Bug Fixed**
```
mem_save(
  text="Bug: [desc]. Root cause: [X]. Fix: [Y]. Prevention: [Z].",
  code="[relevant code snippet]",
  tags="[project],bug-fix,[technology]"
)
```

**8. Architecture Decision**
```
mem_save(
  text="Decision: [X]. Rationale: [Y]. Alternatives: [Z]. Context: [W].",
  tags="[project],architecture,[domain]"
)
```

**9. Config/Credentials**
```
kv_set(key="[project]-db-url", value="postgresql://...", tags="[project],db,prod", ttl_days=0)
```

**10. Pattern Recognized**
```
mem_save(
  text="Pattern: [name]. When: [context]. How: [approach]. Why: [benefits].",
  code="[example code]",
  tags="[project],pattern,[technology]"
)
```

## Multi-Project Isolation

**Always include project tag** as first tag in every save and search:
```
tags="myproject,auth,backend"    ← project is first
```

This ensures facts don't mix between projects. Use consistent project identifiers.

## Priority Rules

1. **ALWAYS search before starting** — leverage past work
2. **ALWAYS save solutions** — non-trivial problem → save pattern
3. **ALWAYS reflect after long tasks** — extract lessons
4. **ALWAYS tag with project** — multi-project isolation
5. **ALWAYS use kv_* for named facts** — faster, more reliable than search
6. **Use ttl_days=0 for permanent facts** — API keys, critical config

## Error Handling

If redis-memory-mcp is unavailable:
- Log warning, continue without memory
- Don't block the main workflow
- Inform user that memory features are temporarily disabled
