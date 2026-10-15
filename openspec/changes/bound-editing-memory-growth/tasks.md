## 1. Fix repeated discovery

- [x] 1.1 Cache dependency discovery for files of immutable (non-`@local`) packages in `AnalysisGlobalCaches` and clear it in `Analysis::clear_cache`.
- [x] 1.2 Confirm with the replay benchmark that semantic-token and completion memory plateau.

## 2. Measurement

- [x] 2.1 Add `scripts/mem-edit-bench.py` (edit replay, editor-request replay, resident memory, document-copy census, peak RSS).
- [ ] 2.2 Decide with the replay benchmark whether the single-arena malloc limit in `tinymist-cli` is still needed and add a latency check if it stays.

## 3. Validate

- [x] 3.1 `cargo test -p tinymist-query`.
- [ ] 3.2 `cargo test --workspace -- --skip=e2e` and a final fmt/clippy pass on the touched crates.
