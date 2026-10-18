# Next plan

Status: Approved (2026-10-18, by the owner; approval of the plan is not an instruction to start)
Created: 2026-10-18

## Goal

Make this repository create standalone stores only. Remove `--add-to` and the slot and marker
machinery, and ship a `template-module/` descriptor in every store so
`claude_project_template` can register the store and insert its guidance into a project. The
installer prints a registration hint and runs nothing.

## Scope

- Accept ADR 0003 and the revised `docs/specs/installer.md` (owner approval), mark ADR 0001
  superseded, and update the roadmap.
- Reshape the kit: `kit.json` replaces `module.json`; `base/` and `slots/` fold into plain
  `files/`; add `template-module/`.
- Remove `--add-to`, `--skip-unsafe-entries`, marker and block handling, exit status 3, and
  `blocks` in the manifest from `install.py`; add the registration hint.
- Replace the tests that covered the removed behavior, and add tests for the criteria tagged
  `[C2a]` in the revised spec.
- Update `docs/development.md`, the `docs/kb/installer.md` copy, and the kit's own guidance
  files.

## Non-goals

- Anything in `claude_project_template`: its `--register`, `--with`, and `--add`, its manifest,
  and its verification belong to its own plans.
- Upgrade (`--upgrade`, roadmap candidate 5). Only the spec text for it is revised.
- The source pipeline, domain tools, and public-release work (candidates 3, 4, and 6).
- Migrating existing projects that received the layer through `--add-to`. None are known
  outside the tests.
- Pushing, or any change to the remote.

## Assumptions and constraints

- Owner direction (2026-10-18): stores are standalone and need no way to inject a new store
  into an existing project; the template's approved `external-modules.md` governs how the
  template uses a store.
- The template has implemented the mechanism (its plans 0006 to 0008, ADR 0003 Accepted
  2026-10-18). The descriptor rules in this plan were checked against its specification and its
  store validator. The test suite restates the rules and does not import or run anything from the
  template. The by-hand end-to-end check in Increment D runs the template's installer against
  scratch paths only.
- The template registers a store under its directory name and accepts only
  `[a-z0-9][a-z0-9_-]*`, while project names here are wider, so the registration hint adds a
  suggested `--name` when needed.
- This plan is roadmap candidate 2a, and the template's `external-modules` candidate 4.
- Accepted ADRs are not edited beyond status lines and dated notes. ADR 0003 supersedes ADR 0001
  (its status line changes in Increment A). ADR 0002 stays in force for creation and upgrade, with
  a dated note about `--add-to`.
- The commit of 15dfbb1 and the archive 0001 are history and are not rewritten.
- Choices made in this draft that the owner may overrule: the kit metadata file is `kit.json`
  (so `module.json` means only the template descriptor); the descriptor ships one fragment,
  `agents-guidance`, and omits the optional descriptor `hint`; the four root files are
  project-owned from creation; the new criteria are tagged `[C2a]`; the hint suggests `--name`
  for a directory name the template would refuse.
- Owner decisions so far (2026-10-18): ADR 0003 is Accepted, ADR 0002 has a dated note about
  `--add-to`, the revised installer spec is Approved, and this plan is Approved. Implementation
  starts only when the owner says so.

## Graphify

Graphify: skipped — no graph exists in this checkout, and the affected files are enumerated by
direct inspection (the installer's function list, the kit tree, and the test files named below).
The impact is confined to this repository.

## Completion criteria

- ADR 0003 is Accepted, ADR 0001 is `Superseded by ADR 0003`, and the revised installer spec is
  Approved.
- `python3 -I install.py --help` lists no `--add-to` or `--skip-unsafe-entries`; either option
  exits 2.
- A store created into a scratch directory contains `template-module/` byte-identical to the kit,
  passes `tools/check_kb.py`, has no marker or block text, and the run prints the kit hint and one
  registration line with the store's absolute real path.
- Every `[C2]` and `[C2a]` criterion in the revised spec except criterion 19 has a passing
  automated test, and criterion 19 (the by-hand end-to-end check) is completed and recorded in
  the Result.
- `python3 -I -B -m unittest discover -s tests` and `git diff --check` pass.

## Increments

### Increment A — Record the decisions

Dependencies: Owner approval of this plan (given 2026-10-18), ADR 0003, and the spec revision (both done)
Affected areas: `docs/decisions/0003-standalone-stores-coordinated-by-the-template.md`,
`docs/decisions/0001-generator-with-independent-projects.md`, `docs/decisions/README.md`,
`docs/specs/installer.md`, `docs/roadmaps/knowledge-base-starter.md`

1. Set ADR 0003 to Accepted with the approval date, and update its index row.
2. Change only ADR 0001's status line to `Superseded by ADR 0003` and its index row.
3. ADR 0002's dated note about the lapsed `--add-to` provisions is already written
   (2026-10-18, owner request); confirm it is committed with this increment.
4. The installer spec was set to Approved (2026-10-18) and ADR 0003 to Accepted before this
   increment; confirm both are committed with it.
5. The roadmap already holds candidate 2a, the revised candidate 5, and the superseded
   candidate 7 (drafted 2026-10-18). Mark candidate 2a in progress when the plan is approved.
6. Verification: `git diff --check`, and a search for `add-to` across `docs/` that lists only
   historical or superseded references.

Completion: the ADR index, ADR statuses, spec status, and roadmap agree, and no living document
describes `--add-to` as current.

### Increment B — Reshape the kit and the descriptor

Dependencies: Increment A
Affected areas: `kit/`, `tests/test_kit.py`, `tests/test_repo.py`, `tests/helpers.py`

1. Write the failing tests first: the kit has `kit.json`, `migrations.json`, and `files/` only;
   `template-module/` satisfies the descriptor rules in the spec (exact keys, lengths, slot name,
   size, encoding, no marker or `BEGIN`/`END` line, only the two allowed placeholders, the router
   and `[U]` and data-not-instructions guidance); the four root files hold the merged guidance,
   copyright note, docs index, and ignore rules with no markers.
2. Create `kit/kit.json` (`kit_version`, `hint`) and remove `kit/module.json`.
3. Move `kit/base/*` into `kit/files/`, merge each `kit/slots/*` fragment into its host file, and
   remove `kit/base/` and `kit/slots/`.
4. Add `kit/files/template-module/module.json` and
   `kit/files/template-module/slots/agents-guidance.md`, using the two template placeholders and
   saying the path is specific to one checkout.
5. Run the new kit tests until they pass.

Completion: the kit tests pass and `find kit -type f` shows the layout in the spec.

### Increment C — Remove layering from the installer and add the hint

Dependencies: Increment B
Affected areas: `install.py`, `tests/test_install_create.py`, `tests/test_install_hardening.py`,
`tests/test_security_regressions.py`, `tests/projects.py`, `tests/test_install_addto.py` (deleted)

1. Write the failing tests first: `--add-to` and `--skip-unsafe-entries` exit 2; no exit 3; the
   created store has `template-module/` verbatim, a manifest without `blocks` that lists
   `template-module/` files; the registration line is printed once after a real creation with the
   real path shell-quoted, ends with `--name <suggestion>` for a directory name such as `My KB`,
   `my.kb`, or `###` and has no suffix for `my_kb`, and is absent with `--dry-run` and after a
   refused run.
2. Remove `run_add_to`, `walk_content`, `unsafe_reason`, `scan_markers`, `apply_fragment`,
   `decorate`, `undecorate`, the marker and fence patterns, `SLOT_HOSTS`, `CONTENT_DIRS`,
   `EXIT_ALREADY_INSTALLED`, the module validation (`validate_module`) in favor of `kit.json`
   validation, and the block planning in `plan_hosts` and `build_manifest`.
3. Load the kit from `kit.json`, add `template-module/` to `OWNED_PREFIXES`, and make
   `template-module/` verbatim next to `docs/kb/` and `tools/`.
4. Print the kit hint and then the registration line after a successful non-dry-run creation.
5. Delete `tests/test_install_addto.py`; remove or rewrite in the other test files only the cases
   that exercised `--add-to`, markers, or skipped entries, and keep every case that exercises
   creation, name and path handling, reads, writes, and git isolation. List each removed test
   name and the reason in the plan's Result.
6. Run the focused suites after each step, then the full suite.

Completion: the full suite passes, `install.py` has no references to markers or `--add-to`, and a
search of the repository's code for those terms finds only the tests that assert they are gone.

### Increment D — Documents, copies, and review

Dependencies: Increment C
Affected areas: `docs/development.md`, `docs/specs/README.md`, `docs/architecture.md`,
`kit/files/docs/kb/installer.md`, `tests/test_kit.py`, `kit/files/README.md`,
`kit/files/AGENTS.md`

1. Update the drift test to strip lines that link to `../roadmaps/` or `../decisions/`, then
   regenerate the `docs/kb/installer.md` copy from the spec by that rule.
2. Update `docs/development.md` (remove `--add-to` from the run command) and the kit's README text
   if it still mentions layering.
3. Replace the template examples in `docs/specs/README.md` with an index of the four
   specifications (title, status, one line each), keeping its guidance on what a spec contains.
4. Fill `docs/architecture.md` with a short factual page for the built system: the components
   (`install.py`, `kit/`, `tests/`, `docs/`), the creation flow and the manifest, the external
   interfaces (the installer's options and exit statuses, the `template-module/` descriptor, the
   registration line), and the constraints (standard library only, hardened reads and writes, no
   dependency on the template). Link ADRs 0002 and 0003 and the installer spec instead of
   restating them, and remove the template's comment prompts. Describe only what exists after
   Increment C.
5. Security review of the changed surface, using the owner's `security-review` skill (a personal
   Claude skill, not a repository command; it is not documented in `docs/development.md`). Its
   evidence is a written finding list with the experiments run, recorded in the Result. Scope:
   the registration line (quoting, control characters in a path), verbatim copying of
   `template-module/`, the manifest without blocks, and a search for dead references to removed
   validation (`grep` over `install.py`, `kit/`, and `tests/`). Add a regression test that fails
   first for any finding before fixing it.
6. Manual smoke: create a store in a scratch directory, run its `tools/check_kb.py`, and read its
   `template-module/` files.
7. End-to-end check (spec criterion 19), with the owner's approval of each template command: run
   the template's `install.py --register <store> --registry <scratch file>` and `--list`
   against the created store, then create a scratch project with `--with <name>` and read the
   resulting `AGENTS.md` block. Repeat once with a store directory named `My KB` to confirm the
   suggested `--name` is accepted. All paths are scratch directories; nothing is written in either
   repository or in the user's real registry. Record the commands and outcomes in the Result.
8. Run the full checks and `git diff --check`.

Completion: the drift test passes with the regenerated copy, `docs/specs/README.md` and
`docs/architecture.md` describe the built system with no template placeholder text, the review
finds nothing open, the end-to-end check succeeded, and the full suite and `git diff --check`
pass.

## Verification

- `python3 -I -B -m unittest discover -s tests`: proves creation, the kit layout, the descriptor
  rules, the hint, the removed options, hardening, and the check tool.
- `git diff --check`: whitespace.
- Manual smoke of `python3 -I install.py <scratch> --git-name N --git-email id@users.noreply.github.com`
  followed by `python3 -I <scratch>/tools/check_kb.py`.
- `git status` shows no `__pycache__`; remove any with `claude-workflow remove` after owner
  approval.

## Risks and sensitive actions

- Deleting tests and installer code. Everything is tracked, and the removals are listed in the
  Result. No file outside the repository is touched.
- The descriptor shape comes from a specification whose implementation does not exist yet; a
  template change could require a later kit change. The `module_format` field and the test that
  restates the rules make that visible.
- No commit, push, or deletion happens without explicit owner approval.

## Review

Codex plan review (2026-10-18, `gpt-5.6-luna`, effort low): converged in 2 of 3 rounds.
Round 1 returned two major findings, both applied: the completion criterion now exempts the
by-hand criterion 19 from "has an automated test", and the security review step names the
owner's `security-review` skill and its evidence. Round 2 found nothing. The plan stays
Proposed until the owner approves it.

## Deferred work

- A test that runs the template's installer. The end-to-end check stays manual so this repository
  has no dependency on the template.
- Upgrade (candidate 5), the source pipeline (candidate 3), domain tools (candidate 4), and release
  readiness (candidate 6).
- A refresh of installed template modules when a store changes (the template's own deferred work).

## Result

<!-- Complete this only after verification. Archive the plan according to
README.md, then reset this file to the empty template. -->
