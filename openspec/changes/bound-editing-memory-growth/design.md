## Context

A heap census of a live server that had grown to about 10 GB showed 150-230 resident copies of the 37 KB document text, so roughly 200 old revisions were still reachable. A request-level replay of an editor (didChange followed by semantic tokens, completion, document colors, symbols and highlights) isolated two request types: semantic tokens and completion. Disabling `typst::trace` brought tokens back to the baseline of about 0.5 GB, which proved the trace as the cause.

A backtrace at the trace call site showed 198 of 220 traces coming from `SharedContext::discover_dependencies` in `analysis/pdg.rs`, through `walk_dependency_sites` and `analyze_import`. All traced nodes were inside `@preview` package files (cetz, fletcher, simple-plot): about 17 traces per edit. The remaining traces came from `check_import` in the expression stage.

## Goals / Non-Goals

**Goals:**
- Resident memory stops growing with the number of edits for tokens and completion.
- No change to what the dependency graph contains for user files and `@local` packages.

**Non-Goals:**
- Removing the trace for dynamic import sources in user files, or the remaining `check_import` traces.
- Lowering the constant memory of a project (the plateau is about 0.3-0.5 GB above the no-trace case).
- Reworking how memoization entries are evicted by the compiler.

## Decisions

- Cache keyed by `FileId` in `AnalysisGlobalCaches`, only for files whose root is a package outside the `local` namespace. Package files are immutable for a given version, so their import structure cannot change while the server runs. User files and `@local` packages change and are never cached.
- Cache the whole discovery value, including `has_unresolved`. Non-literal sites are always marked unresolved, and per the existing comment in `discover_dependencies` the full expression pass can still add authoritative late edges through `record_dependency`. This was not tested against a degraded first discovery.
- Rejected: calling `comemo::evict` after each trace and dropping superseded token requests. Together they reduced growth but did not remove it (966 MB at 300 edits, still about 1.2 MB per edit), and an eviction call ages every cached entry, so it risks evicting the main compiler's results early.

## Risks / Trade-offs

- A package whose import source depends on the main document's evaluation would keep its first discovery result until the server restarts. This is not expected for published packages.
- The cache holds one small entry per analyzed package file.
