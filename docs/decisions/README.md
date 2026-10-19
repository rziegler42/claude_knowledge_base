# Architecture decisions

Record durable design choices here as Architecture Decision Records (ADRs).
ADRs explain why a decision was made; current architecture documents describe
the resulting system.

## Status and lifecycle

- **Proposed** — under review; not yet a project decision.
- **Accepted** — explicitly approved design decision. Implementation may
  follow in a separate plan.
- **Rejected** — considered but explicitly not adopted.
- **Superseded** — replaced by a newer ADR, which links back to this record.

Do not rewrite an accepted ADR to change a decision. Create a new ADR that
supersedes it. Record implementation evidence in the ADR's verification section
and in the associated implementation plan.

## Naming and format

- Use the next unused four-digit number: `0001-short-title.md`.
- Do not reuse, renumber, or fill gaps in ADR numbers.
- Keep each ADR concise: context, decision, alternatives, consequences,
  verification, and related files and decisions.

```markdown
# NNNN: Decision title

Status: Proposed | Accepted | Rejected | Superseded by ADR NNNN
Date: YYYY-MM-DD

## Context
## Decision
## Alternatives considered
## Consequences
## Verification
## Related files and decisions
```

## Index

List every ADR, including rejected and superseded records.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-generator-with-independent-projects.md) | A generator that creates independent knowledge-base projects | Superseded by ADR 0003 |
| [0002](0002-installer-trust-model.md) | Installer trust model | Accepted |
| [0003](0003-standalone-stores-coordinated-by-the-template.md) | Standalone stores, coordinated by the project template | Accepted |
| [0004](0004-stores-may-ship-harness-files.md) | A store may ship harness files, starting with the consuming skill | Accepted |
