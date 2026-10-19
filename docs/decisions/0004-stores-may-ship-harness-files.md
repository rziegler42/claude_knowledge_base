# 0004: A store may ship harness files, starting with the consuming skill

Status: Accepted (2026-10-19, approved by the owner)
Date: 2026-10-19

## Context

ADR 0003 made a store a standalone project whose `template-module/` descriptor carries slot
fragments only, and kept the fragment text tool-neutral because the template treated an external
module as never harness-specific. The template has since decided otherwise for one place: its ADR 0004
and `module_format` 3 let a registered store ship `template-module/harness/<harness>/` files, which
install into a project's own harness directory only after the owner approves the store's digest.

The skill that reads a store from another project, `knowledge-base`, lives today in the owner's global
configuration (that repository's ADR 0008 keeps it there because the starter was tool-neutral). Every
project that uses a store therefore depends on a developer's machine to know how to read it safely,
and the skill can drift from the store's own format.

## Decision

1. A store ships one harness unit, `skills/knowledge-base/SKILL.md` under `harness/claude/`, in a
   `module_format` 3 descriptor. It is starter-owned and verbatim like the rest of `template-module/`.
2. This amends ADR 0003 decision 2 for `harness/` only. The fragments, `kb.json`, the tools and the
   store's documents stay tool-neutral; the one harness-specific file is the skill, and it is
   data-bound: read-only, defers to the store's own `docs/kb/`, and restates the safety rules.
3. `knowledge-base-authoring` is not shipped. It runs the installer and a store's tools, so it stays a
   personal skill.
4. The kit's tests restate the template's rules for a store's harness tree, as they restate the
   descriptor rules, so the starter still neither imports nor reads the template.
5. The skill is instructions a project's harness loads automatically. The owner's digest approval is the
   control, and the skill adds no permission.

## Alternatives considered

- **Keep the skill global.** Rejected: a project could not carry the way to read its own stores, and
  the skill would keep drifting from the store format.
- **Ship it in every format and harness.** Rejected: the template's table has one harness, `claude`.
- **Ship the authoring skill too.** Rejected: it runs code from the store's tree and the installer, a
  larger risk than a read-only consumer, and it needs the starter checkout path.
- **A new store schema.** Rejected: nothing in `kb.json` changes.

## Consequences

- Moving to format 3 means an upgrade changes a store's digest, a template checkout older than the one
  that added format 3 cannot register the store, and the owner approves a store before a project with
  a harness can use it.
- Stores of different ages ship different skill bytes. Registered together, the template installs the
  first and reports the second as a conflict, so stores should be upgraded together.
- The skill overlaps the global one of the same name until that is removed.
- ADR 0003 stays `Accepted`; only its decision 2 is amended, for `harness/`.

## Verification

Delivered by `docs/plans/0008-ship-the-knowledge-base-skill-with-the-store.md`. The
criteria are in `docs/specs/installer.md`, "The harness tree".

Accepted by the owner on 2026-10-19, on this evidence: the plan was reviewed for one Codex round, which
converged; it was implemented in commits `33272ef`, `33c0291` and `7357cfe`; the full suite passed with
757 tests; and, against the template at `470ba85` in scratch directories, registration listed the skill
and its digest, installation was refused before approval and succeeded after it, identical skills
installed once, a differing skill was reported as a conflict and skipped, and an edit after approval
was refused. Two adversarial reviews found no Critical or High finding; the Medium finding (a
project manifest could point the skill at any local directory) and the Low findings were fixed.
Open at acceptance: the global `knowledge-base` skill and that repository's ADR 0008 remain until its
cleanup, so the two skills overlap; the template does not reject bidi or zero-width characters.

## Related files and decisions

- ADR 0003 (decision 2 amended for `harness/`).
- `docs/specs/installer.md`, "The template descriptor" and "The harness tree".
- In `claude_project_template`: ADR 0004 and `docs/specs/module-harness-files.md`.
