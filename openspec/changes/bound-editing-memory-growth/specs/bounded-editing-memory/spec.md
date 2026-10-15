## ADDED Requirements

### Requirement: Editing memory does not grow with the number of edits
Tinymist SHALL keep resident memory during repeated edits of a document bounded by the size of the document and its dependencies, and MUST NOT retain per-edit state that grows with the number of edits.

#### Scenario: Semantic tokens after every edit reach a plateau
- **WHEN** a client edits a document and requests semantic tokens (full or delta) after every edit
- **THEN** resident memory reaches a plateau after the first few dozen edits
- **AND** further edits do not grow resident memory by more than a negligible amount per edit

#### Scenario: Completion after every edit reaches a plateau
- **WHEN** a client edits a document and requests completion at the cursor after every edit
- **THEN** resident memory reaches a plateau after the first few dozen edits
- **AND** the number of retained copies of the document text stays bounded

### Requirement: Immutable package files are analyzed once
Tinymist SHALL NOT repeat dependency discovery, including tracing compilations, for files of immutable packages on every revision.

#### Scenario: Package file is rediscovered only once
- **WHEN** the analysis walks the import sites of a file that belongs to a package outside the `local` namespace
- **THEN** its discovery result is reused for all later revisions until the analysis caches are cleared
- **AND** files of `@local` packages and user files are still rediscovered when they change
