# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
