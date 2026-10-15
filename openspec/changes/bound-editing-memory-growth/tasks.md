## 1. Fix repeated discovery

- [x] 1.1 Cache dependency discovery for files of immutable (non-`@local`) packages in `AnalysisGlobalCaches` and clear it in `Analysis::clear_cache`.
- [x] 1.2 Confirm by replaying per-edit semantic-token and completion requests that memory plateaus.

## 2. Validate

- [x] 2.1 `cargo test -p tinymist-query`.
- [ ] 2.2 `cargo test --workspace -- --skip=e2e` and a final fmt/clippy pass on the touched crates.
