# 0005: Store upgrade

Status: Completed
Created: 2026-10-18
Completed: 2026-10-18

## Goal

Add `install.py --upgrade --dir <store>`, which brings a store's starter-owned files up to date with the
starter without touching the store's own content. It replaces unedited files, adds missing ones, skips and
reports the owner's edits, applies a declared schema migration chain, and records what it did in the manifest.
It meets every criterion tagged `[C5]` in `docs/specs/installer.md`, with fixture tests.

## Scope

- The `--upgrade` mode of `install.py`, with `--dir` and `--dry-run`, and the usage rules that keep it apart
  from creation.
- Reading and validating a store's `.kb-manifest`, deriving the owned set from the kit, and classifying every
  owned file against the table in the specification.
- The `kb_schema` check and the `migrations.json` operations `add`, `replace`, and `remove`.
- Staged writes, the rename order (`kb.json` second to last, the manifest last), idempotence, and recovery of
  an interrupted upgrade.
- Tests for criteria 13 to 18, and the documentation that names the command.

## Non-goals

- Merging a store's edits to starter-owned files: they are skipped and reported (a specification non-goal).
- Touching content: `domains/<name>/`, `catalog/`, `sources/`, `text/`, `playbook/`, and the four root files
  (`README.md`, `AGENTS.md`, `docs/README.md`, `.gitignore`) are never read for modification or written.
- Running git in a store, committing, or pushing. The upgrade leaves its changes in the working tree.
- A first real schema change: the migration chain is empty at schema 1, so the operations are exercised only
  by fixture kits.
- Refreshing a store's registration with the project template, or the template's recorded digest.
- Upgrading a store made by the earlier layering design (blocks in the root files): its `blocks` manifest key
  is ignored and dropped, and its root files are left as they are.
- Public release work (candidate 6) and Claude skills (candidate 8).

## Assumptions and constraints

- Roadmap candidate 5, after candidates 1 to 4 (done). The specification
  (`docs/specs/installer.md`, Approved 2026-10-18) is the requirement; criteria 13 to 18 are `[C5]`. The
  starter-owned set is `kb.json`, `tools/`, `docs/kb/`, `domains/_skeleton/`, and `template-module/`; the
  verbatim set (no name substitution) is `tools/`, `docs/kb/`, and `template-module/`.
- Verified by reading: `install.py` creates stores only and has no `--upgrade`; the manifest holds `schema`,
  `kb_schema`, `name`, `kit_version`, `starter_commit`, `starter_dirty`, and a `files` map of SHA-256 values
  for the owned files; `load_kit` already validates `migrations.json` (a contiguous chain from schema 1, ops
  limited to starter-owned paths) and `resolve_target` already refuses a symlinked directory and any target
  equal to or inside the starter; `write_file` writes through a temporary sibling and a rename and refuses a
  symlinked or non-directory component.
- Standard library and git only (git only in the starter checkout, as now, for the manifest's
  `starter_commit` and `starter_dirty`); no new dependency. The installer relies on POSIX file semantics.
- Trust model (ADR 0002 with the 2026-10-18 note): the store, its files, symlinks, special files, and its
  manifest are untrusted data. Git never runs in the store. Writes stay inside the store.
- The owned set is derived from the kit, never from the manifest. A manifest key outside the owned prefixes is
  ignored and reported, so a forged manifest cannot make the upgrade replace content.
- Choices made in this draft that the owner may overrule:
  - Exit status: 0 when the upgrade completes, even if edited files or conflicts were skipped (they are
    listed); 1 only for a refusal or an error; 2 for usage. A summary says how many were skipped.
  - A symlink, special file, or over-size file at an owned path, or a symlinked ancestor of one, refuses the
    whole run before any write; there is no partial upgrade.
  - `--dir` is required with `--upgrade`; `--name`, `--git-name`, `--git-email`, and
    `--use-global-git-identity` are usage errors with it.
  - A store whose `kb.json` schema and manifest `kb_schema` disagree is refused, with the message pointing at
    `docs/kb/installer.md`; the owner fixes it by hand.
  - A recorded file that is no longer in the kit is reported and kept; the migration `remove` operation is
    the only way the installer ever deletes a store file, and only for a regular file whose checksum matches
    its record.

## Graphify

Graphify: skipped — no graph exists in this checkout. The scope is enumerated by the approved installer
specification and by direct reading of `install.py`, the kit's `migrations.json`, and the tests that create
stores. The change is confined to `install.py` and its tests, plus documentation.

## Completion criteria

- Every `[C5]` criterion (13 to 18) in `docs/specs/installer.md` has a passing test.
- A store made by the installer, then aged (one tool edited, one removed, one recorded checksum altered), is
  upgraded from a changed copy of the starter: the unedited file is replaced, the missing one added, the edited
  one skipped and reported, the content checksum is identical before and after, `check_kb.py
  --require-sources` passes, and a second run does nothing.
- A security review of the manifest handling and the file walk finds nothing open.
- `KB_PDF_PYTHON=<external interpreter> python3 -I -B -m unittest discover -s tests` and `git diff --check`
  pass, and `kit/` and `tests/` contain no `__pycache__`.

## Increments

### Increment A — Reading a store and planning the upgrade

Dependencies: None
Affected areas: `install.py`, `tests/test_upgrade_plan.py`

1. Write the failing tests first.
   - Usage: `--upgrade` needs `--dir`, rejects a positional target and the creation-only options, and
     `--dry-run` is accepted.
   - The store: a symlinked directory, the starter itself or a path inside it (including a case variant),
     a path with a `.git` component, a missing or non-directory path, and a missing manifest are refused.
   - The manifest: not an object, over the size cap, an unknown `schema`, a bad `name`, a checksum that is not
     64 lowercase hex digits, a path that escapes the store or names `.git` in any case, duplicate keys, and a
     non-string value are refused or reported as the specification says; a key outside the owned prefixes is
     ignored and listed; `blocks` and unknown top-level keys are tolerated.
   - The table: one test per row (replace, nothing, skip, skip-and-record, adopt, conflict, add, report),
     with names substituted using the manifest's `name`.
   - Hardening: a symlink, a FIFO, or an over-size file at an owned path, or a symlinked ancestor of one,
     refuses the run and writes nothing; a hostile `.git` in the store (configured helpers) causes no program
     to run; project content and the four root files are never read.
2. Implement the mode in `install.py`: a parser that separates creation from upgrade, store resolution with
   `resolve_target(create=False)`, hardened manifest reading and validation, owned-set derivation from the kit,
   and a read-only planner that classifies each owned file by an `lstat` and a bounded read.
3. Print the plan for `--dry-run` (one line per path with its action) and write nothing.
4. Run the new tests and the full suite.

Completion: `--upgrade --dry-run` prints a correct plan for every row of the table, refusals write nothing,
and existing creation tests are unchanged.

### Increment B — Schema check and migration operations

Dependencies: Increment A
Affected areas: `install.py`, `tests/test_upgrade_migrations.py`

1. Write the failing tests first, with fixture kits that carry a two-step chain using `add`, `replace`, and
   `remove`: a store schema lower than the kit's with no contiguous chain refuses before any write and points
   at `docs/kb/`; a higher schema refuses; disagreeing `kb.json` and manifest schemas refuse; the chain is
   applied whole in order; an edited or unexpected file where an op acts is a conflict that refuses the run
   before any write, lists the path, and leaves `kb_schema` unchanged; `add` is complete when the path already
   equals the source; `replace` is complete when the file already equals the source; `remove` deletes only a
   regular file whose checksum matches its record and nothing else, and is complete when the path is absent;
   the manifest ends with the written checksums and without the removed key.
2. Implement the schema check and the operation engine as a planner that computes the final state in memory
   (the files to write and delete and the manifest content), so conflicts are found before the first write.
3. Show migration actions in `--dry-run`.
4. Run the new tests and the full suite.

Completion: criteria 16 passes in the planning half, and a fixture chain produces the specified final state.

### Increment C — Applying, idempotence, and recovery

Dependencies: Increment B
Affected areas: `install.py`, `tests/test_upgrade_apply.py`

1. Write the failing tests first.
   - A fixture upgrade replaces unedited files, adds missing ones, adopts equal unrecorded ones, skips edited
     ones, and leaves a checksum of `domains/<name>/`, `catalog/`, `sources/`, `text/`, `playbook/`, and the
     four root files identical before and after; the only change to a store-root marker is replacing `kb.json`.
   - A second run reports nothing to do and writes nothing (criterion 14).
   - The upgrade runs no git command against the store and prints the review reminder (criterion 17).
   - A simulated failure between renames, including immediately after a migration `replace` or `remove`, is
     completed by rerunning, and the result equals an uninterrupted upgrade (criterion 18); a hidden temporary
     file left by a killed run is ignored and never replaced.
   - The manifest is renamed last, `kb.json` second to last, and `starter_commit`, `starter_dirty`, and
     `kit_version` are refreshed.
2. Implement the apply phase: write every new file to a hidden temporary sibling, validate, then rename in
   order (owned files, `kb.json`, the manifest), carrying executable bits; delete only for validated `remove`
   operations; print a summary (replaced, added, adopted, skipped, conflicts, reported, deleted) and the
   reminder to review with `git diff` and `git status`.
3. Run the new tests and the full suite.

Completion: criteria 13, 14, 15, 17, and 18 pass.

### Increment D — Documents, review, and the real-store check

Dependencies: Increments A to C
Affected areas: `docs/development.md`, `docs/architecture.md`, `docs/specs/installer.md` (only if a
decision above changes it), `kit/files/docs/kb/installer.md` (regenerated if the specification changes)

1. Update `docs/development.md` (the upgrade command) and `docs/architecture.md` (the upgrade flow and what
   it never touches); amend the specification and regenerate its kit copy only if the owner changes one of
   the choices above.
2. Security verification. The tests are the repository-executable evidence: named hostile-manifest tests
   (path traversal and `.git` in any case in keys, forged checksums aimed at making the upgrade replace content,
   huge or deeply nested JSON, duplicate keys, a name that breaks substitution), hostile-store tests (a
   symlinked owned directory such as `tools/`, a FIFO at an owned path, case-variant names, a hostile `.git`
   with configured helpers, a store inside the starter), and interruption tests. In addition, run the owner's
   personal `security-review` skill with the `security-reviewer` agent (neither is part of this repository;
   both are owner-provided tooling). If either is unavailable, record that in the Result and substitute a
   written checklist of the same cases with the result of each. Add a regression test that fails first for each
   finding.
3. Real-store check: create a store with the installer; age it (edit one tool, delete another, alter a
   recorded checksum, add a project file in each content directory); copy the starter to a scratch directory,
   change a kit tool there, and run the copy's `install.py --upgrade --dir <store> --dry-run` and then
   without `--dry-run`; confirm the outcome, that the content checksum is unchanged, that
   `check_kb.py --require-sources` passes, and that a second run does nothing.
4. Run the full suite with `KB_PDF_PYTHON` set, and `git diff --check`.

Completion: documents match the built mode, the review has nothing open, the real-store check passes, and the
full suite passes with no test skipped.

## Verification

- `KB_PDF_PYTHON=<external interpreter> python3 -I -B -m unittest discover -s tests`: the new `[C5]` tests plus
  the existing suite; report the number skipped, which must be zero.
- `python3 -I -B -m unittest discover -s tests` without the variable: the PDF tests skip and everything else,
  including every upgrade test, passes.
- `git diff --check`, and `git status` shows no `__pycache__` under `kit/` or `tests/`.
- The real-store check in Increment D.

## Risks and sensitive actions

- The first code in the installer that rewrites files in an existing project and, for a `remove` operation,
  deletes one. Rewrites are limited to starter-owned paths derived from the kit and to files that match their
  record; edits are skipped; a deletion needs a regular file with an exact checksum match and comes only from a
  validated kit chain, which is empty today and exercised only by fixtures.
- The store is untrusted input: its manifest, file names, symlinks, special files, and `.git`. The mitigations
  are in the assumptions; git never runs there.
- A crash during the rename phase leaves some files replaced and others not. The staging order and
  idempotence make a rerun complete it; the interruption tests prove it.
- No dependency is installed. No commit, push, or deletion happens without explicit owner approval.

## Review

Codex plan review (2026-10-18, `gpt-5.6-luna`, effort low): converged in 2 of 3 rounds. Round 1 returned one
major finding, that `docs/architecture.md` does not exist; it does (tracked since commit `10d0cbc`, last
changed in `bc13211`, and already describing the installer and the lifecycle tools), so the finding was
rejected with that evidence and the plan is unchanged. Round 2 found nothing. The owner approved the plan on
2026-10-18.

## Deferred work

- A first real schema change and its migration operations.
- Merging the owner's edits to starter-owned files.
- Telling the project template that a registered store's descriptor changed.
- Public release readiness (candidate 6) and Claude skills (candidate 8).

## Result

Implemented 2026-10-18 in commit `d12e3f1` (plan approved in `459a297`). `install.py --upgrade --dir <store> [--dry-run]` with the planner
(`read_manifest`, `read_owned`, `classify`, `Stage`, `plan_upgrade`), the schema check and migration
operations, and the staged apply (`apply_upgrade`: owned files, deletions, `kb.json`, manifest last).

- Tests: 81 new tests in `tests/test_upgrade_plan.py`, `test_upgrade_migrations.py`, `test_upgrade_apply.py`
  (helpers in `tests/stores.py`). Each increment's tests were observed failing before the code. Of the four
  review regression tests, three were observed failing first; one passed on its first run. Full suite with
  `KB_PDF_PYTHON` set: 741 tests, none skipped (741 run, 128 skipped without it).
- Real-store check: a store aged by hand (one tool edited, one deleted, one recorded checksum altered, a
  domain and note files in content directories) was upgraded from a changed scratch copy of the starter. The
  dry run and the real run gave the same plan (1 replace, 1 add, 1 record, 1 skip); content was byte-identical;
  `check_kb.py --require-sources` reported 0 errors; a second run wrote nothing (it still lists the owner's
  edited file as skipped); no temp files remained.
- Security review (`security-reviewer`, experiments on scratch copies): no Critical or High findings. Fixed
  with regression tests: Medium, an edited `kb.json` let the manifest `kb_schema` advance while the marker did
  not (now a conflict that refuses before any write); Low, `--dir ""` acted on the current directory (now
  refused); Low, a failed staging left empty new directories (now removed); Low, a migration `replace` whose
  source differs from its path while the kit also ships that path broke an interrupted rerun (the kit is now
  refused at load). The fixes did not get a second independent bypass attempt.
- Accepted residuals: the delete of a `remove` target uses a path that can follow a parent symlink swapped in
  after the final verification by a concurrent local attacker (the window ADR 0002 accepts; `remove` is unused
  at schema 1); a SIGKILL during apply can leave `.kbtmp-*` files (ignored by reruns); replaced files keep their
  mode; a rewritten manifest drops ignored and unknown keys; `store_schema` accepts duplicate JSON keys in the
  store's `kb.json` (last wins, as for any JSON reader).
- Interpretations: exit 0 when edited files were skipped; whole-run refusal on any unsafe owned path.

## Codex plan review

- Plan: docs/plans/next.md (key a190a044ba679d12)
- Rounds used: 2 of 3
- Round 1: model gpt-5.6-luna, effort low, 1 finding(s) (1 blocker or major)
- Round 2: model gpt-5.6-luna, effort low, 0 finding(s)
- Outcome: converged
- Decisions: 0 applied, 1 rejected
  - R1-F1 [major] rejected: claimed docs/architecture.md was absent; it exists and is tracked.
