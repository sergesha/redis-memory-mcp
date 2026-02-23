"""
Redis Memory MCP — Server
Two tool sets:
  kv_*  — simple key/value store (instant, no embeddings)
  mem_* — semantic memory (vector search via TEI + Redis HNSW)

TTL strategy (volatile-lru):
  - Every key has a TTL (default 90 days)
  - TTL is refreshed on every read → popular facts never expire
  - Unused facts expire after TTL → Redis evicts them under memory pressure
"""

import re, struct, time, uuid, os
from datetime import datetime, timezone

import httpx
import redis.asyncio as aio_redis
from mcp.server.fastmcp import FastMCP

REDIS_URL    = os.getenv("REDIS_URL",    "redis://localhost:6379/0")
EMBED_URL    = os.getenv("EMBED_URL",    "http://localhost:8081")
INDEX        = os.getenv("INDEX_NAME",   "idx:memories")
MEM_PREFIX   = "mem:"
KV_PREFIX    = "kv:"
TOP_K        = int(os.getenv("TOP_K",   "5"))
DEFAULT_TTL  = int(os.getenv("DEFAULT_TTL", str(90 * 24 * 3600)))  # 90 days

mcp = FastMCP("Redis Memory")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _encode(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)

async def _embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{EMBED_URL}/embed", json={"inputs": text})
        r.raise_for_status()
        return r.json()[0]

def _redis():
    return aio_redis.from_url(REDIS_URL, decode_responses=False)

async def _ensure_index(r):
    try:
        await r.execute_command("FT.INFO", INDEX)
    except Exception:
        await r.execute_command(
            "FT.CREATE", INDEX, "ON", "HASH", "PREFIX", "1", MEM_PREFIX, "SCHEMA",
            "text",      "TEXT",
            "label",     "TEXT",
            "code",      "TEXT",
            "tags",      "TAG",    "SEPARATOR", ",",
            "vector",    "VECTOR", "HNSW", "6", "TYPE", "FLOAT32", "DIM", "768", "DISTANCE_METRIC", "COSINE",
            "timestamp", "NUMERIC",
        )

def _decode(v) -> str:
    return v.decode() if isinstance(v, bytes) else str(v)

def _fmt_ts(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "?"

def _fmt_ttl(seconds: int) -> str:
    if seconds < 0:
        return "no TTL"
    days = seconds // 86400
    if days > 0:
        return f"{days}d"
    hours = seconds // 3600
    return f"{hours}h"

def _sanitize_tag(tag: str) -> str:
    """Strip tag to safe chars only (letters, digits, hyphens, underscores)."""
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "", tag.strip())
    return cleaned


# ── KV tools ──────────────────────────────────────────────────────────────────

@mcp.tool()
async def kv_set(key: str, value: str, label: str = "", tags: str = "", ttl_days: int = 90) -> str:
    """Store a key/value fact — instant lookup, no embeddings.
    Use for discrete facts with a known name: credentials, config, settings, names.

    Parameters:
    - key (required): Unique identifier. Use slugs like 'prod-db-url', 'user-timezone'.
      Saving with an existing key overwrites the previous value.
    - value (required): The value to store — any string (URL, password, number, JSON, etc).
    - label: Short human-readable description (shown in lists). Example: 'Production DB connection string'.
    - tags: Comma-separated labels for grouping. Example: 'db,production'.
    - ttl_days: OMIT this parameter in most cases — default is 90 days and TTL resets on
      every read so popular facts never expire. Only set explicitly when needed:
      ttl_days=365 for long-lived facts, ttl_days=7 for temporary context.
      Do NOT pass ttl_days=0 unless the fact must be permanent (no expiry ever).

    Examples: kv_set('openai-api-key', 'sk-...', label='OpenAI API key', tags='secrets,ai')
              kv_set('user-language', 'Russian', label='User preferred language', ttl_days=365)
    """
    r = _redis()
    try:
        redis_key = f"{KV_PREFIX}{key}"
        safe_tags = ",".join(_sanitize_tag(t) for t in tags.split(",") if _sanitize_tag(t)) if tags else ""
        mapping = {
            b"value":     value.encode(),
            b"tags":      safe_tags.encode(),
            b"timestamp": str(int(time.time())).encode(),
            b"ttl_days":  str(ttl_days).encode(),
        }
        if label: mapping[b"label"] = label.encode()
        await r.hset(redis_key, mapping=mapping)
        if ttl_days > 0:
            await r.expire(redis_key, ttl_days * 86400)
    finally:
        await r.aclose()

    ttl_info = f"ttl={ttl_days}d (resets on read)" if ttl_days > 0 else "no expiry"
    desc = f" ({label})" if label else ""
    return f"Stored kv[{key}]{desc} = {value[:80]}" + (f"  tags=[{safe_tags}]" if safe_tags else "") + f"  {ttl_info}"


@mcp.tool()
async def kv_get(key: str) -> str:
    """Retrieve a value by its exact key — O(1), instant, always consistent.
    Automatically refreshes the TTL on read, so frequently accessed facts never expire.

    Parameters:
    - key (required): The exact key used when calling kv_set.
      Example: kv_get('prod-db-url') → 'postgresql://...'
    """
    r = _redis()
    try:
        redis_key = f"{KV_PREFIX}{key}"
        data = await r.hgetall(redis_key)
        if not data:
            return f"Not found: '{key}'"
        # Refresh TTL on read
        ttl_days = int(_decode(data.get(b"ttl_days", b"90")) or 90)
        if ttl_days > 0:
            await r.expire(redis_key, ttl_days * 86400)
        ttl_left = await r.ttl(redis_key)
    finally:
        await r.aclose()

    value = _decode(data.get(b"value", b""))
    label = _decode(data.get(b"label", b""))
    tags  = _decode(data.get(b"tags",  b""))
    ts    = _fmt_ts(data.get(b"timestamp", b"0"))
    desc = f" ({label})" if label else ""
    result = f"kv[{key}]{desc} = {value}\nsaved: {ts}  ttl: {_fmt_ttl(ttl_left)} remaining"
    if tags:
        result += f"  tags=[{tags}]"
    return result


@mcp.tool()
async def kv_delete(key: str) -> str:
    """Delete a key/value entry by its exact key.

    Parameters:
    - key (required): The exact key to delete. Cannot be undone.
    """
    r = _redis()
    try:
        deleted = await r.delete(f"{KV_PREFIX}{key}")
    finally:
        await r.aclose()
    return f"Deleted kv[{key}]" if deleted else f"Not found: '{key}'"


@mcp.tool()
async def kv_list(tag: str = "", pattern: str = "") -> str:
    """List stored key/value entries with their TTL.

    Parameters:
    - tag: Filter by tag (e.g. tag='secrets').
    - pattern: Glob pattern for key names (e.g. pattern='prod-*').
    """
    r = _redis()
    try:
        glob = f"{KV_PREFIX}{pattern}*" if pattern else f"{KV_PREFIX}*"
        keys = [k async for k in r.scan_iter(glob, count=200)]

        results = []
        for k in sorted(keys):
            data = await r.hgetall(k)
            ttl_left = await r.ttl(k)
            name  = _decode(k).replace(KV_PREFIX, "")
            value = _decode(data.get(b"value", b""))
            label = _decode(data.get(b"label", b""))
            tags_ = _decode(data.get(b"tags",  b""))
            ts    = _fmt_ts(data.get(b"timestamp", b"0"))
            if tag and tag not in tags_.split(","):
                continue
            desc = f" ({label})" if label else ""
            line = f"[{ts} | ttl:{_fmt_ttl(ttl_left)}] {name}{desc} = {value[:60]}"
            if tags_:
                line += f"  [{tags_}]"
            results.append(line)
    finally:
        await r.aclose()

    return "\n".join(results) if results else "No key/value entries found."


# ── Semantic Memory tools ─────────────────────────────────────────────────────

@mcp.tool()
async def mem_save(text: str, label: str = "", code: str = "", tags: str = "", ttl_days: int = 90) -> str:
    """Save a fact to semantic memory with a vector embedding for similarity search.
    Use for knowledge that needs to be found by meaning: decisions, patterns, context, docs.

    Parameters:
    - text (required): Full human-readable description. Written as a complete sentence.
      Example: "We use JWT with 24h expiry. Refresh tokens stored in Redis with 30d TTL."
    - label: Short human-readable description (shown in lists and search results).
      Example: "JWT refresh token strategy". Keep under 60 chars.
    - code: Code snippet or structured data associated with this fact.
    - tags: Comma-separated labels for pre-filtering. Example: "auth,jwt,backend".
    - ttl_days: OMIT this parameter in most cases — default is 90 days and TTL resets on
      every search hit so popular facts never expire. Only set explicitly when needed:
      ttl_days=365 for long-lived facts, ttl_days=7 for temporary context.
      Do NOT pass ttl_days=0 unless the fact must be permanent (no expiry ever).

    Returns the memory ID (use mem_delete to remove it).
    """
    embed_input = f"{text}\n{code}" if code else text
    vector_bytes = _encode(await _embed(embed_input))
    mid = str(uuid.uuid4())

    r = _redis()
    try:
        await _ensure_index(r)
        redis_key = f"{MEM_PREFIX}{mid}"
        mapping = {
            b"text":      text.encode(),
            b"vector":    vector_bytes,
            b"timestamp": str(int(time.time())).encode(),
            b"ttl_days":  str(ttl_days).encode(),
        }
        safe_tags = ",".join(_sanitize_tag(t) for t in tags.split(",") if _sanitize_tag(t)) if tags else ""
        if label:     mapping[b"label"] = label.encode()
        if code:      mapping[b"code"]  = code.encode()
        if safe_tags: mapping[b"tags"]  = safe_tags.encode()
        await r.hset(redis_key, mapping=mapping)
        if ttl_days > 0:
            await r.expire(redis_key, ttl_days * 86400)
    finally:
        await r.aclose()

    display = f"'{label}'" if label else f"'{text[:60]}'"
    parts = [f"label={display}"]
    if code:      parts.append(f"code='{code[:30]}'")
    if safe_tags: parts.append(f"tags=[{safe_tags}]")
    ttl_info = f"ttl={ttl_days}d (resets on hit)" if ttl_days > 0 else "no expiry"
    return f"Saved mem[{mid[:8]}] {', '.join(parts)}  {ttl_info}"


@mcp.tool()
async def mem_search(query: str, tags: str = "", top_k: int = 5) -> str:
    """Search semantic memory by meaning — finds relevant facts even without exact word matches.
    Automatically refreshes TTL for every result, so popular memories never expire.

    Parameters:
    - query (required): Natural language question or topic.
    - tags: Comma-separated tag pre-filter. Example: tags="auth,backend".
    - top_k: Number of results (default 5).

    Call at the start of conversations to load relevant context.
    Results show similarity %, TTL remaining, tags, and memory ID.
    """
    vector_bytes = _encode(await _embed(query))

    if tags:
        tag_filter = "|".join(_sanitize_tag(t) for t in tags.split(",") if _sanitize_tag(t))
        ft_query = f"(@tags:{{{tag_filter}}})=>[KNN {top_k} @vector $vec AS score]"
    else:
        ft_query = f"*=>[KNN {top_k} @vector $vec AS score]"

    r = _redis()
    try:
        await _ensure_index(r)
        raw = await r.execute_command(
            "FT.SEARCH", INDEX, ft_query,
            "PARAMS", "2", "vec", vector_bytes,
            "RETURN", "7", "label", "text", "code", "tags", "timestamp", "score", "ttl_days",
            "SORTBY", "score",
            "DIALECT", "2",
        )

        if raw[0] == 0:
            return "No memories found."

        results = []
        items = raw[1:]
        for i in range(0, len(items), 2):
            redis_key = _decode(items[i])
            mid = redis_key.replace(MEM_PREFIX, "")
            fields = items[i + 1]
            fd = {}
            for j in range(0, len(fields), 2):
                fd[_decode(fields[j])] = _decode(fields[j + 1])

            # Refresh TTL on hit
            ttl_days = int(fd.get("ttl_days", "90") or 90)
            if ttl_days > 0:
                await r.expire(redis_key, ttl_days * 86400)
            ttl_left = await r.ttl(redis_key)

            sim  = round((1 - float(fd.get("score", 1.0))) * 100, 1)
            dt   = _fmt_ts(fd.get("timestamp", 0))
            label = fd.get("label") or fd.get("text", "")[:60]
            head = f"[{sim}% | {dt} | ttl:{_fmt_ttl(ttl_left)}] {label}  ID:{mid[:8]}"
            if fd.get("tags"): head += f"  tags=[{fd['tags']}]"
            body = fd.get("text", "")
            if fd.get("code"): body += f"\n```\n{fd['code']}\n```"
            results.append(f"{head}\n{body}")
    finally:
        await r.aclose()

    return "\n\n---\n".join(results)


@mcp.tool()
async def mem_list(limit: int = 20, tag: str = "") -> str:
    """Browse semantic memories sorted by recency with TTL info.

    Parameters:
    - limit: Maximum number of results (default 20).
    - tag: Filter by a single tag. Example: tag='auth'.
    """
    r = _redis()
    try:
        await _ensure_index(r)
        if tag:
            safe_tag = _sanitize_tag(tag)
            raw = await r.execute_command(
                "FT.SEARCH", INDEX, f"@tags:{{{safe_tag}}}",
                "RETURN", "5", "label", "text", "tags", "timestamp", "ttl_days",
                "LIMIT", "0", str(limit),
                "SORTBY", "timestamp", "DESC",
            )
            results = []
            items = raw[1:]
            for i in range(0, len(items), 2):
                redis_key = _decode(items[i])
                mid = redis_key.replace(MEM_PREFIX, "")
                fields = items[i + 1]
                fd = {_decode(fields[j]): _decode(fields[j+1]) for j in range(0, len(fields), 2)}
                ttl_left = await r.ttl(redis_key)
                dt = _fmt_ts(fd.get("timestamp", 0))
                label = fd.get("label") or fd.get("text", "")[:60]
                line = f"[{dt} | ttl:{_fmt_ttl(ttl_left)}] {label}  ID:{mid[:8]}"
                if fd.get("tags"): line += f"  [{fd['tags']}]"
                line += f"\n{fd.get('text','')[:100]}"
                results.append(line)
        else:
            keys = [k async for k in r.scan_iter(f"{MEM_PREFIX}*", count=100)][:limit]
            results = []
            for k in keys:
                data = await r.hgetall(k)
                if b"vector" not in data:
                    continue
                mid   = _decode(k).replace(MEM_PREFIX, "")
                label_ = _decode(data.get(b"label", b""))
                text  = _decode(data.get(b"text",  b""))
                tags_ = _decode(data.get(b"tags",  b""))
                ttl_left = await r.ttl(k)
                dt    = _fmt_ts(data.get(b"timestamp", b"0"))
                label = label_ or text[:60]
                line  = f"[{dt} | ttl:{_fmt_ttl(ttl_left)}] {label}  ID:{mid[:8]}"
                if tags_: line += f"  [{tags_}]"
                line += f"\n{text[:100]}"
                results.append(line)
    finally:
        await r.aclose()

    return "\n\n".join(results) if results else "No semantic memories found."


@mcp.tool()
async def mem_delete(memory_id: str) -> str:
    """Permanently delete a semantic memory by its ID.

    Parameters:
    - memory_id (required): The full UUID from mem_save or mem_search results.
    """
    r = _redis()
    try:
        deleted = await r.delete(f"{MEM_PREFIX}{memory_id}")
    finally:
        await r.aclose()
    return f"Deleted mem[{memory_id}]" if deleted else f"Not found: '{memory_id}'"


# ── Unified search ────────────────────────────────────────────────────────────

@mcp.tool()
async def search(query: str, tags: str = "", top_k: int = 5) -> str:
    """Search ALL memory at once — both key-value and semantic.
    Use this as the default search tool. Combines results from both stores.

    Parameters:
    - query (required): Natural language question, topic, or key name.
    - tags: Comma-separated tag pre-filter.
    - top_k: Max semantic results (default 5). All matching kv entries are always included.

    Returns kv matches (by key/value substring) + semantic matches (by meaning), clearly separated.
    """
    parts = []

    # 1. Search kv by substring in key and value
    r = _redis()
    try:
        kv_results = []
        q_lower = query.lower()
        async for k in r.scan_iter(f"{KV_PREFIX}*", count=200):
            data = await r.hgetall(k)
            name  = _decode(k).replace(KV_PREFIX, "")
            value = _decode(data.get(b"value", b""))
            label = _decode(data.get(b"label", b""))
            tags_ = _decode(data.get(b"tags",  b""))
            if tags:
                filter_tags = {_sanitize_tag(t) for t in tags.split(",") if _sanitize_tag(t)}
                entry_tags = set(tags_.split(",")) if tags_ else set()
                if not filter_tags & entry_tags:
                    continue
            if q_lower in name.lower() or q_lower in value.lower() or q_lower in label.lower():
                ttl_left = await r.ttl(k)
                ttl_days = int(_decode(data.get(b"ttl_days", b"90")) or 90)
                if ttl_days > 0:
                    await r.expire(k, ttl_days * 86400)
                dt = _fmt_ts(data.get(b"timestamp", b"0"))
                desc = f" ({label})" if label else ""
                line = f"[{dt} | ttl:{_fmt_ttl(ttl_left)}] {name}{desc} = {value[:80]}"
                if tags_: line += f"  [{tags_}]"
                kv_results.append(line)
    finally:
        await r.aclose()

    if kv_results:
        parts.append("── Key-Value matches ──\n" + "\n".join(kv_results))

    # 2. Semantic search
    mem_result = await mem_search(query=query, tags=tags, top_k=top_k)
    if mem_result and mem_result != "No memories found.":
        parts.append("── Semantic matches ──\n" + mem_result)

    if not parts:
        return "Nothing found in any memory store."

    return "\n\n".join(parts)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
