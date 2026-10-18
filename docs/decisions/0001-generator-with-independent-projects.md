# 0001: A generator that creates independent knowledge-base projects

Status: Superseded by ADR 0003
Date: 2026-10-17

## Context

This repository generalizes the sibling `game_theory` project into something others can
use to build knowledge bases of their own. The owner decided it is public, MIT-licensed,
and carries no subject matter. It must work with `claude_project_template` without
depending on it, and one project should hold many domains. Sources are large, may be
copyrighted, and are untrusted, while a record of what each source is should survive a
fresh clone.

## Decision

1. This repository is a **generator**, not a knowledge base: `install.py`, a `kit/`, tests,
   and its own docs. A standalone installer creates each knowledge-base project as an
   independent repository (fresh `git init`, explicit local identity, no remote, no
   commits, a `.kb-manifest` for upgrades), and can instead layer the kit onto an existing
   project with `--add-to`.
2. The kit has the project template's module format (`module.json`, `files/`, `slots/`,
   `base/`) so a template that loads remote modules can use it unchanged. The installer
   does not depend on the template, and the template checks the starter, not the reverse.
3. One project holds many domains under `domains/`. Saved sources and converted text are
   shared, flat, keyed by a unique stem, and untracked by default. A tracked
   `catalog/<stem>.md` record per source holds its facts once.
4. Process documents (plans, roadmaps, ADRs) are not shipped to projects.
5. Copyright and licensing is guidance in the generated README, not enforcement.

The requirements are in the four specifications in `docs/specs/`.

## Alternatives considered

- **Clone and edit this repository as the knowledge base.** Rejected: mixes the tooling
  with one person's content, and upstream changes would conflict with it.
- **Separate repositories for tools and content, per domain.** Rejected: duplicated
  sources, and no single place to enforce the format.
- **A template repository only.** Rejected: no upgrade path and no layering onto existing
  projects.
- **Per-domain sources and text.** Rejected: duplicates files and facts when domains share
  a source.
- **Enforcing copyright limits in tools.** Rejected: the applicable rules depend on the
  user's jurisdiction.

## Consequences

- Upgrades depend on the manifest and on the split between starter-owned and project-owned
  paths. Edited starter-owned files are skipped and reported, never merged.
- The kit's module shape follows the template's current format by deliberate change, not
  automatically.
- A fresh clone of a project has no sources or converted text and rebuilds them from the
  catalog.

## Verification

Each requirement has acceptance criteria in the specifications, tagged with the roadmap
candidate that delivers it. None is implemented yet.

## Related files and decisions

- `docs/specs/installer.md`, `docs/specs/knowledge-base-format.md`
- `docs/roadmaps/knowledge-base-starter.md`
- ADR 0002 (installer trust model)
