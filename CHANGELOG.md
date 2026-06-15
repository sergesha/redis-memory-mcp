# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1](https://github.com/sergesha/redis-memory-mcp/compare/v0.2.0...v0.2.1) (2026-06-15)


### Bug Fixes

* **start:** map host.docker.internal for Linux Docker Engine ([ce86d0b](https://github.com/sergesha/redis-memory-mcp/commit/ce86d0b513b3ac25d5766cd6be5ea28df0d48dc6))

## [0.2.0](https://github.com/sergesha/redis-memory-mcp/compare/v0.1.1...v0.2.0) (2026-06-13)


### Features

* **start:** install pinned release tags instead of raw main ([cc0ba70](https://github.com/sergesha/redis-memory-mcp/commit/cc0ba703d8d53999dcaa2815521a741c53fef93b))
* **start:** install pinned release tags instead of raw main ([fb50cd7](https://github.com/sergesha/redis-memory-mcp/commit/fb50cd7e0cc71db07c97e169515d9e5c16ff2336))


### Bug Fixes

* RESP3 FT.SEARCH parsing + tag escaping; adopt release-please ([3434916](https://github.com/sergesha/redis-memory-mcp/commit/3434916bbe7bac9498aa62970acfde9fed1f0db1))
* **start:** address PR [#2](https://github.com/sergesha/redis-memory-mcp/issues/2) review (stale comment, image tag, curl timeouts) ([18aa742](https://github.com/sergesha/redis-memory-mcp/commit/18aa742747a91764cf9cf77a8668715030f1df9c))
* **start:** address PR [#2](https://github.com/sergesha/redis-memory-mcp/issues/2) review comments ([e0e1c3f](https://github.com/sergesha/redis-memory-mcp/commit/e0e1c3f6c83dc40420f1b457d7b4a008797ba5cd))
* **start:** harden image tag and bound source download time ([80de337](https://github.com/sergesha/redis-memory-mcp/commit/80de3375fe2339cecb4cdf0a79dd4f0ac372fa4d))

## [0.1.1] - 2026-06-13

### Fixed
- `mem_search` and `mem_list` now parse RESP3 `FT.SEARCH` map replies (as returned by
  redis-py 8), fixing the `Error executing tool mem_search: 0` (`KeyError(0)`) that broke
  semantic search on every query. Legacy RESP2 flat-list replies are still supported.
- Tag values are now backslash-escaped inside `@tags:{...}` filters, fixing the
  `Syntax error … near …` RediSearch parse failure on tags containing hyphens
  (e.g. `a2a-secure-messaging`).

### Changed
- Pinned the `redis` dependency to `>=5.0.0,<9` so a future major release (with another
  RESP/behaviour change) cannot silently break the server again.

## [0.1.0]

### Added
- Initial release: semantic memory (`mem_*`) and key/value (`kv_*`) MCP tools backed by
  Redis Stack (HNSW vector search) and TEI embeddings, with TTL-based auto-expiry.
