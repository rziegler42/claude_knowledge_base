# Specifications

This directory holds durable, repository-owned requirements and behavioral
specifications. Specifications describe the intended outcome and acceptance
criteria; implementation sequencing belongs in `../plans/`, and durable design
choices belong in `../decisions/`.

## Index

| Specification | Status | Covers |
|---|---|---|
| [installer](installer.md) | Approved | Creating a standalone store, its `template-module/` descriptor, the manifest, and upgrade |
| [knowledge-base-format](knowledge-base-format.md) | Approved | Layout, catalog records, entries, claim tags, and the checker |
| [source-pipeline](source-pipeline.md) | Approved | Saving, scanning, converting, and quarantining sources |
| [domain-lifecycle](domain-lifecycle.md) | Approved | Creating, filling, and expanding a domain |

The four specifications are also shipped, as copies, in `kit/files/docs/kb/`; a test asserts that
each copy equals its source apart from links to roadmaps and decisions. Edit the source here and
regenerate the copy, never the reverse.

## Writing a specification

Use concise, descriptive lowercase kebab-case filenames. Each specification should
identify its scope, non-goals, assumptions, relevant constraints or interfaces,
acceptance criteria, and links to governing ADRs or external requirements. Update
it when the intended behavior changes; do not use it as a chronological work log.
