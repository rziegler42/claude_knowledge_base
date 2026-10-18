# 0003: Standalone stores, coordinated by the project template

Status: Accepted (2026-10-18, approved by the owner)
Date: 2026-10-18

## Context

ADR 0001 made this repository a generator that creates independent knowledge-base projects
and can also layer the kit onto an existing project with `--add-to`. It shaped the kit as a
template module (`module.json`, `files/`, `slots/`, `base/`) so a template that loads remote
modules could use it unchanged.

The template took the opposite direction. Its approved specification
(`claude_project_template/docs/specs/external-modules.md`, 2026-10-18) is implemented
(its plans 0006 to 0008) and recorded in its accepted ADR 0003. The template registers or
names a standalone project, verifies it read-only, and injects slot fragments into a project.
It never copies files from a store, never runs anything in it, and requires the store to ship
a `template-module/` descriptor. Its contract for this repository says the generator drops
`--add-to`, only creates stores, ships the descriptor, prints a registration hint, and needs
no knowledge of the template's code.

Layering therefore has two owners today, and the add-to path duplicates in this repository
what the template now does with less risk: marker parsing, managed blocks, fenced-code and
nesting rules, and a preflight on the host project's directories. That machinery is most of
the installer's attack surface.

## Decision

1. A **store** is a standalone knowledge-base project. This repository only creates stores.
   There is no `--add-to`, no layering onto an existing project, and no marker or managed
   block handling here.
2. Every store ships `template-module/` in the template's descriptor format
   (`module.json` and `slots/<slot>.md`), so the template can register it and insert
   guidance into a project. This repository follows the template's `module_format`
   deliberately, not automatically. The descriptor is the only coupling, and this repository
   neither reads nor depends on the template's code, registry, or manifest.
3. After creating a store, the installer prints one hint line that tells the owner how to
   register the store with the template. It runs nothing and has no flag for it. The template
   registers a store under its directory name and accepts only `[a-z0-9][a-z0-9_-]*`, while
   project names here are wider, so the line adds a suggested `--name` when the directory
   name would be refused.
4. The kit becomes one tree copied into a new project. The base/files split and the
   per-slot fragments go away; the starter-owned set gains `template-module/`.
5. Upgrade of a store (roadmap candidate 5) stays. It covers starter-owned files only, and
   the manifest no longer records blocks.
6. Decisions 3 to 5 of ADR 0001 stand unchanged: one project holds many domains with shared,
   untracked sources and a tracked catalog; process documents are not shipped; copyright is
   guidance only.
7. The trust model of ADR 0002 stands for creation: the owner's command line is intent,
   reads are hardened, writes stay inside the target through a temporary sibling and a rename,
   git runs only in the starter checkout and the new directory. Its provisions for `--add-to`
   and for untrusted existing projects lapse with that mode; `--upgrade` still treats the
   store as untrusted data.

## Alternatives considered

- **Keep `--add-to` beside the descriptor.** Rejected: two ways to inject guidance, with this
  repository carrying the harder one and the template carrying the safer one.
- **Let the template copy files from a store.** Rejected by the template's own
  specification: fragments only.
- **Register the store from the installer.** Rejected: it needs the template's location and
  registry format, which the generator must not know.
- **Change nothing and let the template adapt.** Rejected: the template's specification is
  approved and the owner chose that direction.

## Consequences

- The installer shrinks: the walk of an untrusted existing project, marker and block parsing,
  `--skip-unsafe-entries`, the "already installed" status, and the host-file preflight are
  removed along with their tests.
- A store's root `README.md`, `AGENTS.md`, `docs/README.md`, and `.gitignore` are written once
  at creation and belong to the project afterwards. Upgrades no longer refresh guidance text
  in them; the starter-owned `docs/kb/` copies carry the versioned procedure instead.
- A store that is also meant to be used from another project depends on the template's
  descriptor format. A `module_format` change in the template needs a deliberate change here.
- The fragment text lives in a tool-neutral descriptor that the template inserts into other
  projects. It is untrusted data on the template's side, and the template verifies it.
- Already created stores (none are known outside tests) would lack `template-module/`; a
  later upgrade adds it as a starter-owned file.

## Verification

Acceptance criteria in `docs/specs/installer.md` (revision of 2026-10-18), delivered by the
plan in `docs/plans/next.md`. None is implemented yet.

## Related files and decisions

- Supersedes ADR 0001. ADR 0002 stays in force as described in decision 7; the
  owner decides whether to record a dated note on it.
- `docs/specs/installer.md`
- `claude_project_template/docs/specs/external-modules.md` and its ADR 0003 (external module
  mechanism)
