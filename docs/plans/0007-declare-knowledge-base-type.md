# 0007: Declare the knowledge-base type to the project template

Status: Completed
Completed: 2026-10-18
Created: 2026-10-18

## Goal

Every store declares itself to the project template as a `knowledge-base`, so a project's
`.template-manifest` records, for each knowledge base applied to it, its type, where the store
lives, and where its router and format specification are. A skill reads one file to find them.

## Scope

- The descriptor `kit/files/template-module/module.json` moves to `module_format` 2 and adds
  `type: "knowledge-base"` and `data: {"router": "playbook/README.md", "spec":
  "docs/kb/knowledge-base-format.md"}`. Both `data` values are paths relative to the store root;
  a consumer resolves them against the `store` value the template records.
- The kit's restated descriptor rules (`descriptor_problems` in `tests/test_kit.py`) accept
  formats 1 and 2, allow `type` and `data` only in format 2, and apply the template's bounds
  (type: lowercase name of at most 64 characters; data: plain JSON, at most 4 levels, 256 values and
  4096 bytes, short printable strings).
- A test pins that the descriptor's `data.router` and `data.spec` equal `kb.json`'s `router` and
  `spec`, so the two cannot drift.
- An upgrade test: a store created with the format 1 descriptor is brought to format 2 by
  `--upgrade` as an ordinary owned-file replacement, and an edited descriptor is skipped and
  listed, as for any owned file.
- Documentation: the source specification `docs/specs/installer.md` (the descriptor section and
  acceptance criterion C2a, which still say "exactly the keys `module_format` and
  `description`", `1` today), with `kit/files/docs/kb/installer.md` kept identical to it apart
  from the roadmap and decision links the kit copy drops (the existing copy rule, checked by
  `tests/test_kit.py`); the README's note on registering a store; and the fact that an
  installer from before format 2 refuses the descriptor.

## Non-goals

- `paths`. The template defines it as project-relative, and a store lives outside the project, so
  the template's own `store` value is the location. Declaring `paths` would be wrong.
- A `hint` key, a new fragment, or any change to the fragment text.
- A `kb.json` schema change, a migration, or a change to `--upgrade` itself. The descriptor is
  already an owned, verbatim file.
- Reading or writing a project's `.template-manifest`, or any knowledge of the template's code or
  registry. The store only declares; the template records.
- The consuming skill (owned by the global-config project) and the roadmap.
- Changing existing stores. They stay at format 1 until upgraded.

## Assumptions and constraints

- Verified in the template at `6d4d3e8`: `module_format` 2 allows optional `type`, `paths` and
  `data`; the template records `module_info[name] = {store, type, paths, data}` for every
  external module, with `store` as `../name` for a sibling and an absolute path otherwise; a
  full `--update` rewrites entries; format 1 rejects these keys; an older installer refuses a
  manifest that has external entries.
- `data` is untrusted input to the template and is bounded by it. The kit must stay inside those
  bounds, and the test restates them because the starter has no dependency on the template.
- A store registered before this change keeps its recorded digest and format-1 entry until the
  owner upgrades the store and runs the template's `--update` for the project.
- Compatibility cost, accepted: a template checkout older than `1b91d55` cannot register an
  upgraded store. The README says so.
- No decision is open. My calls: carry `router` and `spec` in `data` (they are the two facts a
  skill needs, they never change within a kit schema), and leave out the kit schema number, which
  would go stale in the template's record when a store is upgraded but the project is not
  updated.

Graphify: skipped — the affected files are enumerated above (one descriptor, one test helper,
one spec section, the README).

## Completion criteria

A freshly created store ships a format 2 descriptor that the restated rules accept; a format 1
store is upgraded to it; the descriptor and `kb.json` agree; the full suite passes; and, when a
template checkout is available, `--register` accepts a created store and a scratch project
created with it records `module_info` with `type`, `store` and `data`.

## Increments

### Increment A — Declare the type in the descriptor

Dependencies: None
Affected areas: `kit/files/template-module/module.json`, `tests/test_kit.py`,
`tests/test_upgrade_apply.py` (or `test_upgrade_plan.py`), `kit/kit.json` if the repository's
convention bumps the kit version for a shipped-file change

1. Write failing tests: the format 2 rules (accepted and refused cases for `type`, `data`,
   format 1 with the new keys, bool or other formats); the descriptor matches `kb.json`; a format 1
   store is upgraded to the new descriptor; an edited descriptor is skipped.
2. Change `module.json` and the restated rules; rerun the suite.

Completion: new tests fail first, then pass; the existing suite is unchanged.

### Increment B — Document the contract

Dependencies: Increment A
Affected areas: `docs/specs/installer.md`, `kit/files/docs/kb/installer.md`, `README.md`

1. Update the descriptor section and criterion C2a in the specification, copy the change into
   the kit copy, and update the README registration note.
2. Run the documentation tests (links, tool and option names, personal data) and the kit test
   that compares the two copies after the link filtering.

Completion: documents match behavior; suite green.

## Verification

the documented full-suite command from `docs/development.md` (`KB_PDF_PYTHON=<venv>/bin/python`
when a PDF environment exists, otherwise without it, which skips the PDF tests),
`git diff --check`, and a manual run in a scratch directory using the real template installer:
create a store, `--register` it, create a project with it, and read `module_info` from the
project's manifest. The scratch work happens outside both repositories.

## Risks and sensitive actions

- The template's `module_info` is derived from what the template reads at install time; a wrong
  `data` value would be recorded in every project. The `kb.json` equality test guards it.
- The manual check writes a registry file under the user's config directory unless `--registry`
  points at a scratch file; I will use `--registry`.
- No push, no change to the template repository, no change to existing projects.

## Deferred work

- Per-store `paths` if the template ever allows store-relative roles.
- A discovery note or skill guidance on reading `module_info` (global-config owner).

## Result

Implemented 2026-10-18 in commit `20ec80b` (plan approved in `db1ab06`). The descriptor
`template-module/module.json` is now `module_format` 2 with `type: "knowledge-base"` and
`data: {router, spec}`, equal to `kb.json`. `tests/test_kit.py` restates the template's rules for
formats 1 and 2 (including the bounds on `type` and `data`, and the refusal of `paths`), pins the
`kb.json` equality, and covers upgrading a format 1 store and skipping an edited descriptor.
`docs/specs/installer.md` (the descriptor section and criterion C2a), its kit copy, and the
README registration note were updated.

Verification: the full suite passes with the PDF environment (751 tests, none skipped);
`git diff --check` is clean. With the real template installer (template `6d4d3e8`) and a scratch
registry, a created store registered, and a project created with it recorded
`module_info.my_kb = {store: "../my_kb", type: "knowledge-base", data: {router, spec}}`.

Not exercised: the template's `--update` on an existing project, a template older than `1b91d55`
(it refuses format 2, as documented), and an absolute `store` path. The rule tests failed first;
the two upgrade tests passed immediately, because the descriptor is an ordinary owned file.

## Codex plan review

- Plan: docs/plans/next.md (key 083e00940d2002fa)
- Rounds used: 2 of 3
- Round 1: model gpt-5.6-luna, effort low, 1 finding(s) (1 blocker or major), 74032 input and 1023 output tokens
- Round 2: model gpt-5.6-luna, effort low, 2 finding(s) (0 blocker or major), 92671 input and 1358 output tokens
- Outcome: converged (no blocker or major finding in the last round)
- Decisions: 3 applied, 0 rejected
