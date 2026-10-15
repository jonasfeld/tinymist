## Why

Editing a document in an LSP client makes the tinymist server's resident memory grow with the number of edits, not with the size of the document. In a measured session on a 37 KB document, semantic-token and completion requests sent after every edit grew the server from about 0.5 GB to 1.6 GB in 60 edits and kept climbing (about 1.7 MB per edit); a long live session reached roughly 10 GB.

Semantic tokens and completion run the dependency graph discovery for every revision. That discovery walks the import sites of every reachable file, including files of immutable `@preview` packages, and for each non-literal import source runs a full tracing compilation. Every trace fills the compiler's memoization cache, so memory grows with each edit even though package files never change.

## What Changes

- Keep dependency discovery results for files of immutable packages (every namespace except `@local`) in the global analysis caches, so they are computed once per server lifetime instead of once per revision.
- Clear that cache together with the other global analysis caches.
- Add a repeatable benchmark (`scripts/mem-edit-bench.py`) that replays per-edit editor requests and reports resident memory and the number of retained document copies, so regressions are measurable.
- Limit glibc malloc to one arena at startup on Linux (separate, earlier change); the benchmark is used to decide whether it stays.

## Capabilities

### New Capabilities
- `bounded-editing-memory`: server memory during repeated edits scales with document and project size, not with the number of edits.

### Modified Capabilities

## Impact

- `crates/tinymist-query/src/analysis/pdg.rs`
- `crates/tinymist-query/src/analysis/global.rs`
- `scripts/mem-edit-bench.py`
- `crates/tinymist-cli/src/main.rs` (allocator arena limit)
